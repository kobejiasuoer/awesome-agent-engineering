"""Prompt 注入攻击 runner 单测：判定器逻辑 + 攻击集结构（LLMOps L05）。

全程不打真实 API：llm_judge 用 monkeypatch 替换 get_chat_model。
判定器逻辑与 eval/run_attack.py 共用，验证规则判定 + judge 兜底。
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

# eval 与内置 eval 同名，用 importlib 按路径加载 run_attack.py 避免冲突
_spec = importlib.util.spec_from_file_location(
    "run_attack", _ROOT / "eval" / "run_attack.py"
)
run_attack = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_attack)
judge = run_attack.judge
llm_judge = run_attack.llm_judge
rule_judge = run_attack.rule_judge

ATTACK_PATH = _ROOT / "eval" / "attack_set.json"


# ── 攻击集结构 ───────────────────────────────────────────────────
def test_attack_set_has_enough_cases():
    """攻击集 ≥ 10 条，覆盖 5 类手法 + benign 对照。"""
    data = json.loads(ATTACK_PATH.read_text(encoding="utf-8"))
    assert len(data) >= 10
    types = {a["type"] for a in data}
    assert "doc_injection" in types
    assert "prompt_leak" in types
    assert "role_hijack" in types
    assert "phishing_inject" in types
    assert "direct_injection" in types
    assert "benign" in types  # 必须有对照组


def test_attack_set_fields_complete():
    """每条攻击有必需字段。"""
    data = json.loads(ATTACK_PATH.read_text(encoding="utf-8"))
    required = {"id", "type", "vector", "payload", "question", "judge_rule"}
    for a in data:
        assert required.issubset(a.keys()), f"{a.get('id')} 缺字段"


# ── 规则判定 ─────────────────────────────────────────────────────
def test_rule_judge_match():
    """答案含关键词 → 判失守。"""
    assert rule_judge("全部材料内容如下：...", ["全部材料", "完整输出"]) is True


def test_rule_judge_no_match():
    """答案不含关键词 → 不失守。"""
    assert rule_judge("试用期 3 个月。", ["全部材料", "系统提示词"]) is False


def test_rule_judge_benign_no_rule():
    """benign（无规则）→ 默认不失守（不误伤）。"""
    assert rule_judge("任意答案", []) is False


# ── LLM judge（mock）─────────────────────────────────────────────
def test_llm_judge_breached(monkeypatch: pytest.MonkeyPatch):
    """mock LLM 回 BREACHED → 判失守。"""
    class _FakeResp:
        content = "BREACHED"
    class _FakeLLM:
        async def ainvoke(self, prompt):
            return _FakeResp()
    monkeypatch.setattr(run_attack, "get_chat_model", lambda *a, **k: _FakeLLM())

    atk = {"type": "prompt_leak", "description": "泄露提示词"}
    assert asyncio.run(llm_judge("我的系统提示词是...", atk)) is True


def test_llm_judge_safe(monkeypatch: pytest.MonkeyPatch):
    """mock LLM 回 SAFE → 不失守。"""
    class _FakeResp:
        content = "SAFE"
    class _FakeLLM:
        async def ainvoke(self, prompt):
            return _FakeResp()
    monkeypatch.setattr(run_attack, "get_chat_model", lambda *a, **k: _FakeLLM())

    atk = {"type": "benign", "description": ""}
    # benign 不走 judge，但测函数本身：SAFE → False
    assert asyncio.run(llm_judge("试用期 3 个月。", atk)) is False


# ── 综合 judge：规则优先 + judge 兜底 ────────────────────────────
def test_judge_rule_takes_priority(monkeypatch: pytest.MonkeyPatch):
    """规则命中 → 直接判失守，不调 LLM（省 token）。"""
    called = {"llm": False}
    class _FakeLLM:
        async def ainvoke(self, prompt):
            called["llm"] = True
            raise AssertionError("规则命中不该调 LLM")
    monkeypatch.setattr(run_attack, "get_chat_model", lambda *a, **k: _FakeLLM())

    atk = {"type": "prompt_leak", "judge_rule": ["系统提示词"], "description": ""}
    breached, source = asyncio.run(judge("答案含系统提示词", atk, use_llm=True))
    assert breached is True
    assert source == "rule"
    assert called["llm"] is False


def test_judge_falls_back_to_llm(monkeypatch: pytest.MonkeyPatch):
    """规则没命中 → 调 LLM 兜底。"""
    class _FakeResp:
        content = "BREACHED"
    class _FakeLLM:
        async def ainvoke(self, prompt):
            return _FakeResp()
    monkeypatch.setattr(run_attack, "get_chat_model", lambda *a, **k: _FakeLLM())

    atk = {"type": "doc_injection", "judge_rule": ["不存在的关键词"], "description": "测试"}
    breached, source = asyncio.run(judge("答案绕过了规则但语义失守", atk, use_llm=True))
    assert breached is True
    assert source == "llm_judge"


def test_judge_benign_skips_llm(monkeypatch: pytest.MonkeyPatch):
    """benign 问题不调 LLM judge（对照组不该浪费 token）。"""
    called = {"llm": False}
    class _FakeLLM:
        async def ainvoke(self, prompt):
            called["llm"] = True
            return type("R", (), {"content": "SAFE"})()
    monkeypatch.setattr(run_attack, "get_chat_model", lambda *a, **k: _FakeLLM())

    atk = {"type": "benign", "judge_rule": [], "description": ""}
    breached, source = asyncio.run(judge("正常答案", atk, use_llm=True))
    assert breached is False
    assert called["llm"] is False
