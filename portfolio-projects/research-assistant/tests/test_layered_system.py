"""三层指令架构测试（Harness 课程 L08，扩展 frontier-L03 skill_loader）。

锁死四类契约：
    1. 三层组装：核心永在、索引层便宜常驻、按需层只装命中正文
    2. 计量：breakdown 三层 token 口径正确；索引 << 全部正文
    3. 同构组合：记忆索引（L03）与工作区指针（L06）进索引层
    4. 对照与反例：单体注入的膨胀账；description 写差=漏加载可复现
"""
from __future__ import annotations

import pytest

from research_assistant.config import settings
from research_assistant.context_ledger import FakeTokenizer
from research_assistant.skill_loader import (
    SkillLoader, build_layered_system, monolithic_system,
)

CORE = "你是深度研究员。红线：不得编造未在信源中出现的数字；省略必须显式。"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setitem(settings.__dict__, "enable_layered_system", False)
    monkeypatch.setitem(settings.__dict__, "enable_skills", False)
    yield


@pytest.fixture
def loader():
    """真 skills/ 目录的 loader（4 个 skill：2 个 frontier 旧 + 2 个本课新）。"""
    ld = SkillLoader()
    assert len(ld.list_skills()) >= 4
    return ld


# ── 三层组装 ─────────────────────────────────────────────────
def test_three_layers_present(loader):
    """命中场景：核心+索引+按需层俱全；按需层只有命中的技能全文。"""
    text, bd = build_layered_system(CORE, query="做一次跨源深度调研", loader=loader)
    assert CORE in text
    assert "可用技能 Skills" in text                      # 索引层（全部一行描述）
    assert "deep-research-protocol" in str(bd["matched_skills"])
    assert "逐字引用" in text                             # 命中技能的正文进按需层
    assert "速览纪律" not in text                          # 未命中技能的正文不进


def test_no_match_keeps_index_only(loader):
    """未命中：索引层仍在（可能有用挂在墙上），按需层为空（不付全文租金）。"""
    text, bd = build_layered_system(CORE, query="今天天气如何", loader=loader)
    assert "可用技能 Skills" in text
    assert bd["matched_skills"] == [] and bd["ondemand_tokens"] == 0
    assert "逐字引用" not in text


def test_no_loader_is_core_only():
    """enable_skills 关的语义：loader=None → 只有核心层（零介入）。"""
    text, bd = build_layered_system(CORE, query="深度调研", loader=None)
    assert text == CORE
    assert bd["index_tokens"] == 0 and bd["ondemand_tokens"] == 0


# ── 计量 ─────────────────────────────────────────────────────
def test_breakdown_accounting(loader):
    """三层计量口径：core/index/ondemand 各自独立、与文本一致。"""
    tk = FakeTokenizer()
    text, bd = build_layered_system(CORE, query="跨源深度调研", loader=loader,
                                    tokenizer=tk)
    assert bd["core_tokens"] == tk.count(CORE)
    assert bd["index_tokens"] > 0 and bd["ondemand_tokens"] > 0
    assert tk.count(text) >= bd["core_tokens"] + bd["index_tokens"]


def test_index_far_cheaper_than_all_bodies(loader):
    """索引经济学：全部技能的一行描述 << 全部技能正文（≥5 倍差）。"""
    tk = FakeTokenizer()
    _, bd = build_layered_system(CORE, query="", loader=loader, tokenizer=tk)
    _, mono_tokens = monolithic_system(CORE, loader, tokenizer=tk)
    all_bodies = mono_tokens - tk.count(CORE)
    assert bd["index_tokens"] * 5 < all_bodies


def test_monolithic_vs_layered_arithmetic(loader):
    """膨胀账：单体每次调用付全部正文；三层只付索引+命中——命中率<1 即省。"""
    tk = FakeTokenizer()
    _, mono = monolithic_system(CORE, loader, tokenizer=tk)
    text, bd = build_layered_system(CORE, query="跨源深度调研", loader=loader,
                                    tokenizer=tk)
    layered = tk.count(text)
    assert layered < mono                     # 单任务只命中部分技能 → 更便宜


# ── 同构组合（L03/L06 进索引层）─────────────────────────────
def test_memory_index_and_pointers_compose(loader):
    text, bd = build_layered_system(
        CORE, query="", loader=loader,
        memory_index="# 操作记忆索引\n- [report-style] 报告偏好",
        workspace_pointers="📁 [sources/S17.txt]（13,624 字）")
    assert "report-style" in text and "sources/S17.txt" in text
    assert bd["index_tokens"] > 0


# ── 反例：索引质量决定召回 ───────────────────────────────────
def test_bad_description_misses_loading(tmp_path):
    """漏加载可复现：description 写成抽象词，相关任务命不中——
    渐进披露的通用软肋（与 L03 记忆 triggers 同构）。"""
    bad = tmp_path / "skills" / "bad-skill"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_text(
        "---\nname: bad-skill\ndescription: 输出规范\n---\n\n# 内容",
        encoding="utf-8")
    good = tmp_path / "skills" / "good-skill"
    good.mkdir(parents=True)
    (good / "SKILL.md").write_text(
        "---\nname: good-skill\ndescription: 报告格式与结构要求\n---\n\n# 内容",
        encoding="utf-8")
    ld = SkillLoader(tmp_path / "skills")
    matched = ld.match_skills("写一份研究报告")
    assert "good-skill" in matched            # 具体描述命中
    assert "bad-skill" not in matched         # 抽象描述漏加载（反例复现）


def test_composition_deterministic(loader):
    a = build_layered_system(CORE, query="深度调研", loader=loader)
    b = build_layered_system(CORE, query="深度调研", loader=loader)
    assert a[0] == b[0] and a[1] == b[1]
