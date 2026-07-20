"""压缩器测试（Harness 课程 L02）。

锁死四类契约：
    1. 三步纪律：登记幂等、pinned 永不进摘要器、压缩后登记项 100% 在场
    2. 分层可压性：tool_result 先于 note、oldest-first、conclusion 永不丢
    3. 审计：每压一次一行记录，丢弃 item 可追溯，无痕压缩不存在
    4. 长途跑法：登记压缩=完赛且 20/20 在场（对照组不登记→关键事实蒸发）
"""
from __future__ import annotations

import json

import pytest

from research_assistant.compactor import (
    Compactor, PinnedFact, WindowItem, head_summarizer, make_llm_summarizer,
)
from research_assistant.config import settings
from research_assistant.context_ledger import FakeTokenizer


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setitem(settings.__dict__, "enable_compaction", False)
    monkeypatch.setitem(settings.__dict__, "window_limit_tokens", 8000)
    monkeypatch.setitem(settings.__dict__, "compact_threshold_pct", 0.60)
    monkeypatch.setitem(settings.__dict__, "compact_target_pct", 0.50)
    yield


def _mk(limit=1000, threshold=0.60, target=0.50, summarizer=None) -> Compactor:
    return Compactor(tokenizer=FakeTokenizer(), limit=limit, threshold_pct=threshold,
                     target_pct=target, summarizer=summarizer or head_summarizer)


# ── 登记与触发 ───────────────────────────────────────────────
def test_register_idempotent():
    """同 id 重复登记=更新（幂等），pinned 块按 id 排序稳定。"""
    c = _mk()
    c.register(PinnedFact("F02", "事实二"))
    c.register(PinnedFact("F01", "事实一"))
    c.register(PinnedFact("F01", "事实一修订"))
    assert len(c.pinned) == 2
    block = c.pinned_block()
    assert block.index("[F01]") < block.index("[F02]")
    assert "事实一修订" in block and "事实一" in block


def test_should_compact_threshold():
    """水位触发：≥ limit×threshold 才压（进警戒区就压，不等危险区）。"""
    c = _mk(limit=1000, threshold=0.60)
    assert not c.should_compact(599)
    assert c.should_compact(600)


def test_defaults_from_settings(monkeypatch):
    """构造参数缺省取 settings（config 是唯一调参点）。"""
    monkeypatch.setitem(settings.__dict__, "window_limit_tokens", 4321)
    monkeypatch.setitem(settings.__dict__, "compact_threshold_pct", 0.7)
    c = Compactor()
    assert c.limit == 4321 and c.threshold_pct == 0.7


# ── 分层可压性 ───────────────────────────────────────────────
def test_tool_results_dropped_first_oldest_first():
    """先压 tool_result 且 oldest-first；够了就不动 note。"""
    c = _mk(limit=1000, target=0.50)   # 目标 ≤500
    items = [
        WindowItem("S01", "tool_result", "a" * 1200),   # 300 tok（最老）
        WindowItem("n1", "note", "n" * 200),            # 50 tok
        WindowItem("S02", "tool_result", "b" * 1200),   # 300 tok
        WindowItem("n2", "note", "m" * 200),            # 50 tok
    ]
    new_items, rec = c.compact(items)
    assert rec.dropped_items == ("S01",)                 # 丢最老的一篇就够了
    kinds = [i.item_id for i in new_items]
    assert "n1" in kinds and "S02" in kinds


def test_notes_dropped_only_when_tool_results_exhausted():
    """tool_result 全丢仍超目标 → 才轮到 note（且同层内 oldest-first）。"""
    c = _mk(limit=400, target=0.25)    # 目标 ≤100
    items = [
        WindowItem("S01", "tool_result", "a" * 400),    # 100
        WindowItem("n1", "note", "n" * 400),            # 100
        WindowItem("n2", "note", "m" * 400),            # 100
    ]
    _, rec = c.compact(items)
    assert "S01" in rec.dropped_items and "n1" in rec.dropped_items
    assert "n2" not in rec.dropped_items


def test_conclusion_never_dropped():
    """结论层是资产不是缓存：无论多超标都不丢（宁可压不到目标）。"""
    c = _mk(limit=100, target=0.10)
    items = [WindowItem("c1", "conclusion", "x" * 4000)]
    new_items, rec = c.compact(items)
    assert rec.dropped_items == ()
    assert any(i.item_id == "c1" for i in new_items)


# ── 三步纪律 ─────────────────────────────────────────────────
def test_pinned_survives_and_never_enters_summarizer():
    """机械保证的两半：pinned 块永不进摘要器；压缩后登记项原文在场。"""
    seen: list[list[str]] = []

    def spy_summarizer(texts):
        seen.append(list(texts))
        return "（摘要）全丢"          # 恶意摘要器：什么都不保留

    c = _mk(limit=1000, target=0.30, summarizer=spy_summarizer)
    c.register(PinnedFact("F01", "关键事实：延迟下降 41%"))
    items = [WindowItem("S01", "tool_result", "正文……关键事实：延迟下降 41%……" + "x" * 2000)]
    new_items, rec = c.compact(items)
    window = "".join(i.text for i in new_items)
    assert "延迟下降 41%" in window                 # 恶意摘要器也丢不掉
    assert rec.pinned_verified
    assert all("🔒" not in t for batch in seen for t in batch)  # pinned 没进摘要器


def test_summarizer_receives_dropped_texts():
    """摘要器拿到的恰是被丢内容（判断交给模型的接口契约）。"""
    seen: list[str] = []

    def spy(texts):
        seen.extend(texts)
        return "S"

    c = _mk(limit=400, target=0.25, summarizer=spy)
    items = [WindowItem("S01", "tool_result", "AAAA" * 100),
             WindowItem("S02", "tool_result", "BBBB" * 10)]
    c.compact(items)
    assert any("AAAA" in t for t in seen)


def test_make_llm_summarizer():
    """生产摘要器把内容交 LLM（FakeLLM 关键词命中——只测接口不测语义）。"""
    class _FakeLLM:
        def invoke(self, prompt):
            class _M:
                content = "  LLM 摘要结果  "
            assert "档案员" in prompt and "材料" in prompt
            return _M()

    s = make_llm_summarizer(_FakeLLM())
    assert s(["a", "b"]) == "LLM 摘要结果"


# ── 审计 ─────────────────────────────────────────────────────
def test_audit_record_and_report():
    """审计行：seq 递增、before>after、丢弃 id 可追溯、报表可读。"""
    c = _mk(limit=1000, target=0.40)
    items = [WindowItem("S01", "tool_result", "a" * 2000),
             WindowItem("S02", "tool_result", "b" * 800)]
    _, r1 = c.compact(items)
    assert r1.seq == 1 and r1.before_tokens > r1.after_tokens
    assert "S01" in r1.dropped_items
    assert "压缩#1" in c.audit_report() and "S01" in c.audit_report()


def test_compact_noop_still_audited():
    """没东西可丢也要留痕（空丢弃清单——「查过没压」与「没查」可区分）。"""
    c = _mk(limit=10000)
    _, rec = c.compact([WindowItem("c", "conclusion", "x" * 40)])
    assert rec.dropped_items == () and len(c.records) == 1


# ── 长途跑法（L02 主角与对照）─────────────────────────────────
def test_compacted_longhaul_with_pins():
    """登记压缩完赛：30/30、峰值<8k、在场率 20/20、矛盾可发现、审计全验证。"""
    from eval_agent.harness_runs import run_compacted_longhaul
    r = run_compacted_longhaul(register_pins=True)
    assert r["completed_sources"] == 30 and r["died_at"] is None
    assert r["peak_window_tokens"] <= 8000
    assert r["presence_hits"] == 20
    assert r["contradiction_discoverable"]
    assert r["compactions"] >= 2 and r["pinned_verified_all"]


def test_compacted_longhaul_without_pins_loses_facts():
    """对照组：同样压缩、同样摘要，只是不登记——关键事实随原文蒸发。"""
    from eval_agent.harness_runs import run_compacted_longhaul
    r = run_compacted_longhaul(register_pins=False)
    assert r["completed_sources"] == 30
    assert r["presence_hits"] < 5              # 无契约=运气（实测 1/20）
    assert not r["contradiction_discoverable"]


def test_compacted_longhaul_deterministic():
    """双跑一致（收益矩阵确定性传统）。"""
    from eval_agent.harness_runs import run_compacted_longhaul
    a = json.dumps(run_compacted_longhaul(register_pins=True),
                   ensure_ascii=False, sort_keys=True)
    b = json.dumps(run_compacted_longhaul(register_pins=True),
                   ensure_ascii=False, sort_keys=True)
    assert a == b
