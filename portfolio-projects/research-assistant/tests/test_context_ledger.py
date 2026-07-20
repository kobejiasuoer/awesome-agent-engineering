"""上下文账本测试（Harness 课程 L01）。

锁死四类契约：
    1. 可注入 tokenizer 与水位三区的算术（safe/caution/danger/over 边界）
    2. 账本行为：四桶拆解、记录先于死亡（enforce）、汇总占比
    3. 主链路集成：开关关=零介入（一条记录都不产生）；开=五节点记账，
       且 prompt 拼接逐字节不变（纯测量不拦截）
    4. eval 与主链路同一把尺子（long_haul 复用 context_ledger.FakeTokenizer）
"""
from __future__ import annotations

import pytest

from research_assistant import context_ledger as cl
from research_assistant.config import settings


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """每测隔离：账本清零 + 开关显式关（默认态）。"""
    cl._current_ledger = None
    monkeypatch.setitem(settings.__dict__, "enable_context_ledger", False)
    monkeypatch.setitem(settings.__dict__, "window_limit_tokens", 8000)
    yield
    cl._current_ledger = None


# ── 算术层 ───────────────────────────────────────────────────
def test_fake_tokenizer_canonical():
    """规范口径：len//4，空串保底 1（与 cost_budget 估算一致）。"""
    tk = cl.FakeTokenizer()
    assert tk.count("a" * 400) == 100
    assert tk.count("") == 1


def test_zone_boundaries():
    """水位三区边界：<60% safe / 60–85% caution / 85–100% danger / >100% over。"""
    assert cl.zone(4799, 8000) == "safe"
    assert cl.zone(4800, 8000) == "caution"      # 恰好 60%
    assert cl.zone(6799, 8000) == "caution"
    assert cl.zone(6800, 8000) == "danger"       # 恰好 85%
    assert cl.zone(8000, 8000) == "danger"       # 恰好 100% 还没越限
    assert cl.zone(8001, 8000) == "over"


def test_long_haul_shares_tokenizer():
    """eval 与主链路同一把尺子：long_haul 的 FakeTokenizer 就是 context_ledger 的。"""
    from eval_agent.long_haul import FakeTokenizer as EvalTk
    assert EvalTk is cl.FakeTokenizer


# ── 账本行为 ─────────────────────────────────────────────────
def test_measure_four_parts_and_records():
    """四桶拆解：各桶独立计数、total=和、记录追加有序。"""
    led = cl.WindowLedger(tokenizer=cl.FakeTokenizer(), limit=1000)
    rec = led.measure("researcher", system="s" * 40, task_state="t" * 80,
                      tool_results="r" * 400, history="h" * 120)
    assert rec.parts == {"system": 10, "task_state": 20,
                         "tool_results": 100, "history": 30}
    assert rec.total == 160 and rec.zone == "safe" and rec.call_no == 1
    rec2 = led.measure("writer", task_state="x" * 4)
    assert rec2.call_no == 2 and led.peak() == 160


def test_empty_parts_cost_zero():
    """空桶记 0（FakeTokenizer 的保底 1 只对非空文本生效）。"""
    led = cl.WindowLedger(limit=100)
    rec = led.measure("split", task_state="abcd")
    assert rec.parts["system"] == 0 and rec.parts["tool_results"] == 0
    assert rec.total == 1


def test_enforce_records_before_raise():
    """enforce 模式：越限抛 ContextOverflowError，但记录先于死亡（尸检要有数据）。"""
    led = cl.WindowLedger(limit=10, enforce=True)
    with pytest.raises(cl.ContextOverflowError):
        led.measure("naive", tool_results="x" * 4000)
    assert len(led.records) == 1 and led.records[0].over_limit


def test_measure_only_never_raises():
    """纯测量模式（主链路形态）：越限只记录不打断。"""
    led = cl.WindowLedger(limit=10, enforce=False)
    rec = led.measure("naive", tool_results="x" * 4000)
    assert rec.over_limit and rec.zone == "over"
    assert led.summary()["over_calls"] == 1


def test_summary_shares():
    """汇总占比：by_part 求和、share 归一、水位分布计数。"""
    led = cl.WindowLedger(limit=8000)
    led.measure("a", tool_results="r" * 2400)      # 600 tok
    led.measure("b", task_state="t" * 800)          # 200 tok
    s = led.summary()
    assert s["calls"] == 2 and s["peak"] == 600
    assert s["by_part"]["tool_results"] == 600 and s["by_part"]["task_state"] == 200
    assert s["share"]["tool_results"] == 0.75
    assert s["zone_counts"] == {"safe": 2}


def test_limit_defaults_to_settings(monkeypatch):
    """limit 缺省取 settings.window_limit_tokens（可注入覆盖）。"""
    monkeypatch.setitem(settings.__dict__, "window_limit_tokens", 123)
    assert cl.WindowLedger().limit == 123
    assert cl.WindowLedger(limit=456).limit == 456


# ── 主链路集成 ────────────────────────────────────────────────
async def _run_researcher(fake_llm_cls, monkeypatch, search_text: str):
    """跑一次 researcher 节点（mock 搜索，返回 findings）。"""
    from research_assistant import nodes

    async def fake_search(q):
        return search_text

    monkeypatch.setattr(nodes, "web_search", fake_search)
    llm = fake_llm_cls({"研究员": "mock 发现"})
    researcher = nodes.make_researcher(llm)
    return await researcher({"subtopic": "测试子题"})


def test_nodes_disabled_by_default(fake_llm, monkeypatch):
    """开关关（默认）：跑完节点，账本一条记录都没有（零介入）。"""
    import asyncio
    result = asyncio.run(_run_researcher(fake_llm, monkeypatch, "[资料] 内容" * 50))
    assert result["findings"]
    assert cl.get_ledger() is None


def test_nodes_enabled_records_researcher(fake_llm, monkeypatch):
    """开关开：researcher 记账且 tool_results 桶拿到检索材料的大头。"""
    import asyncio
    monkeypatch.setitem(settings.__dict__, "enable_context_ledger", True)
    cl.reset_ledger()
    asyncio.run(_run_researcher(fake_llm, monkeypatch, "[资料] 检索材料正文" * 100))
    led = cl.get_ledger()
    assert led is not None and len(led.records) == 1
    rec = led.records[0]
    assert rec.node == "researcher"
    assert rec.parts["tool_results"] > rec.parts["task_state"] > 0


def test_nodes_enabled_records_split_and_writer(fake_llm, monkeypatch):
    """split/writer/summarize/reviewer 同样入账（主链路五调用全覆盖）。"""
    monkeypatch.setitem(settings.__dict__, "enable_context_ledger", True)
    cl.reset_ledger()
    from research_assistant import nodes

    nodes.make_split(fake_llm({"研究规划师": "子题A\n子题B"}))({"topic": "T"})
    nodes.make_summarize(fake_llm({"综合分析师": "摘要"}))(
        {"findings": ["发现1", "发现2"]})
    nodes.make_writer(fake_llm({"撰写者": "报告正文"}))(
        {"research_summary": "S" * 40, "feedback": "", "truncated": False})
    nodes.make_reviewer(fake_llm({"审稿人": "合格"}))(
        {"report": "R" * 80, "rewrite_count": 0, "re_research_count": 0,
         "findings": []})
    led = cl.get_ledger()
    assert [r.node for r in led.records] == ["split", "summarize", "writer", "reviewer"]
    w = led.records[2]
    assert w.parts["history"] > 0            # summary 进 history 桶
    r = led.records[3]
    assert r.parts["history"] == 20          # 80 字符报告 → 20 token


def test_measure_call_disabled_returns_none():
    """守卫入口：开关关时 measure_call 返回 None 且不创建账本对象。"""
    assert cl.measure_call("x", task_state="abc") is None
    assert cl.get_ledger() is None
