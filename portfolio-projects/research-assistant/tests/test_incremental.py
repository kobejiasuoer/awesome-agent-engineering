"""Ambient L03 测试：增量研究回路。

测试原则（对齐 conftest.py）：
    - 不调真实 LLM：split/route 用 FakeLLM，run_incremental 的 invoke 用 monkeypatch 假体
    - ledger 用 tmp_path 隔离 + 单例重置
    - 开关关闭时行为 = 现状（核心不变式：split 照常 LLM 拆题）
"""
from __future__ import annotations

import asyncio

import pytest

from research_assistant import config, incremental
from research_assistant import task_ledger as tl_mod
from research_assistant.incremental import (
    build_incremental_focus, prior_conclusions, record_and_brief, run_incremental,
)
from research_assistant.nodes import make_split, route_to_researchers
from research_assistant.watcher import ChangeSet, WatchItem

from tests.conftest import FakeLLM


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """开关还原 + ledger 单例/库隔离。"""
    config.settings.__dict__["enable_incremental_run"] = False
    config.settings.__dict__["enable_ledger"] = False
    config.settings.__dict__["ledger_db_path"] = str(tmp_path / "ledger.db")
    monkeypatch.setattr(tl_mod, "_ledger", None)
    yield
    config.settings.__dict__["enable_incremental_run"] = False
    config.settings.__dict__["enable_ledger"] = False


def _cs(new=(), changed=(), ok=True, error="", first=False):
    return ChangeSet(source_id="s", scanned_at=0.0, ok=ok, error=error,
                     first_scan=first, new_items=list(new), changed_items=list(changed))


# ── 焦点构造 ─────────────────────────────────────────────────

def test_focus_from_new_and_changed_items():
    cs = _cs(new=[WatchItem("e", "框架Y补丁", "修复内存泄漏")],
             changed=[WatchItem("c", "框架X支持AGUI", "【更正】计划已中止")])
    focus = build_incremental_focus(cs)
    assert len(focus) == 2
    assert focus[0].startswith("【新增】框架Y补丁")
    assert focus[1].startswith("【内容变更】框架X支持AGUI")
    assert "更正" in focus[1]          # 变更条目显式要求对照旧结论


def test_focus_ignores_gone_items():
    cs = _cs()
    cs.gone_item_ids = ["item-x"]
    assert build_incremental_focus(cs) == []


# ── split 节点：焦点直用 vs 现状拆题（核心不变式）────────────

def test_split_uses_focus_when_enabled():
    config.settings.__dict__["enable_incremental_run"] = True
    llm = FakeLLM({}, default="子题A\n子题B\n子题C")
    split = make_split(llm)
    out = split({"topic": "主题", "incremental_focus": ["【新增】只研究这条"]})
    assert out["subtopics"] == ["【新增】只研究这条"]
    assert llm.call_count == 0          # 跳过 LLM 拆题（省一次调用）


def test_split_ignores_focus_when_disabled():
    """开关关 = 现状行为：即使有焦点也照常 LLM 拆题。"""
    llm = FakeLLM({}, default="子题A\n子题B")
    split = make_split(llm)
    out = split({"topic": "主题", "incremental_focus": ["【新增】焦点"]})
    assert llm.call_count == 1
    assert out["subtopics"] == ["子题A", "子题B"]


def test_split_falls_back_to_llm_when_no_focus():
    config.settings.__dict__["enable_incremental_run"] = True
    llm = FakeLLM({}, default="子题A\n子题B")
    split = make_split(llm)
    out = split({"topic": "主题", "incremental_focus": []})
    assert llm.call_count == 1          # 无焦点（如建仓前）→ 原路径


# ── prior_context 下发（Send 载荷）───────────────────────────

def test_route_carries_prior_context_in_send_payload():
    sends = route_to_researchers({
        "subtopics": ["a", "b"], "prior_context": "已知：X 支持 AGUI",
    })
    assert len(sends) == 2
    assert all(s.arg["prior_context"] == "已知：X 支持 AGUI" for s in sends)


def test_route_defaults_empty_prior_context():
    sends = route_to_researchers({"subtopics": ["a"]})
    assert sends[0].arg["prior_context"] == ""


# ── prior_conclusions（旧结论注入源）─────────────────────────

def test_prior_conclusions_empty_without_ledger():
    assert prior_conclusions("主题") == ""


def test_prior_conclusions_reads_done_tasks():
    config.settings.__dict__["enable_ledger"] = True
    ledger = tl_mod.get_ledger()
    t = ledger.add_task("主题", "框架X支持AGUI")
    ledger.update_status(t.id, "done", result="X 宣布全面支持 AGUI")
    ledger.add_task("主题", "未完成项")     # todo 状态不该出现
    hint = prior_conclusions("主题")
    assert "框架X支持AGUI" in hint and "X 宣布全面支持 AGUI" in hint
    assert "未完成项" not in hint


# ── run_incremental 三分支 ───────────────────────────────────

def _forbid_invoke(monkeypatch):
    async def _boom(*a, **kw):
        raise AssertionError("不该进研究图")
    monkeypatch.setattr("research_assistant.service.invoke", _boom)


def test_source_failed_branch_never_enters_graph(monkeypatch):
    _forbid_invoke(monkeypatch)
    out = asyncio.run(run_incremental("主题", _cs(ok=False, error="HTTP 503")))
    assert out["status"] == "source_failed"
    assert "没能看到" in out["brief"] and "不等于没有变化" in out["brief"]


def test_no_change_branch_never_enters_graph(monkeypatch):
    _forbid_invoke(monkeypatch)
    out = asyncio.run(run_incremental("主题", _cs()))
    assert out["status"] == "no_change"
    assert "确认无变化" in out["brief"]


def test_researched_branch_passes_focus_and_prior(monkeypatch):
    config.settings.__dict__["enable_incremental_run"] = True
    captured = {}

    async def fake_invoke(topic, thread_id, extra_state=None):
        captured.update(extra_state or {})
        return {"findings": ["【新增】框架Y补丁 的发现"], "report": "r"}

    monkeypatch.setattr("research_assistant.service.invoke", fake_invoke)
    cs = _cs(new=[WatchItem("e", "框架Y补丁", "修复内存泄漏")])
    out = asyncio.run(run_incremental("主题", cs, thread_id="t1"))
    assert out["status"] == "researched"
    assert captured["incremental_focus"] and "框架Y补丁" in captured["incremental_focus"][0]
    assert "prior_context" in captured
    assert out["thread_id"] == "t1"


# ── ledger 协作闭环：记进度 + ✏️ 修正标注 ────────────────────

def test_brief_without_ledger_degrades_gracefully():
    brief = record_and_brief("主题", _cs(new=[WatchItem("e", "E", "内容")]),
                             ["发现一"])
    assert "无账本模式" in brief and "🆕" in brief


def test_ledger_loop_first_run_then_incremental_with_correction():
    """闭环：建仓入账 → 次日变更 → 简报带 ✏️ 修正 + ➡️ 历史结论。"""
    config.settings.__dict__["enable_ledger"] = True

    # Day1 建仓：结论入账
    cs1 = _cs(new=[WatchItem("c", "框架X支持AGUI", "全面支持")], first=True)
    brief1 = record_and_brief("主题", cs1, ["【框架X支持AGUI】X 宣布全面支持"])
    assert "首次研究" in brief1

    # Day4 变更：新发现以「更正」开头（researcher 的 prior_instr 约定）
    cs2 = _cs(changed=[WatchItem("c", "框架X支持AGUI", "【更正】计划已中止")])
    brief2 = record_and_brief("主题", cs2, ["更正：框架X已撤回 AGUI 支持，转投 A2A"])
    assert "✏️" in brief2               # 矛盾被标为修正，不是静默覆盖
    assert "➡️" in brief2               # 历史结论仍在场
