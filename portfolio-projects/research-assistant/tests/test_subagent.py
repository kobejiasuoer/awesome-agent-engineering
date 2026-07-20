"""子代理隔离测试（Harness 课程 L05）。

锁死四类契约：
    1. 回传结论不回传过程：结果只含结论/指针/诊断数字，原文不外溢
    2. 失败结构化回传：溢出/异常 → ok=False + 可读原因（非堆栈非空结论）
    3. 子窗口物理预算：独立 enforce 账本；记录先于死亡（尸检数字回传）
    4. 长途跑法：主窗峰值坍缩（5,272→~700）；失败线三超长源显式失败；
       整形组合线完赛但深埋事实丢失有声明——两种诚实，各自成立
"""
from __future__ import annotations

import json

import pytest

from research_assistant.config import settings
from research_assistant.context_ledger import FakeTokenizer
from research_assistant.subagent import SubagentRunner


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setitem(settings.__dict__, "enable_subagent_isolation", False)
    monkeypatch.setitem(settings.__dict__, "subagent_window_tokens", 4000)
    yield


def _simple_worker(subject, payload, ledger):
    ledger.measure("sub-study", system="研读指令", tool_results=payload)
    return f"[{subject}] 结论：要点一；要点二", (subject,)


# ── 契约 1：结论回传，过程不外溢 ─────────────────────────────
def test_ok_result_shape_and_no_leak():
    runner = SubagentRunner(_simple_worker, window_tokens=4000,
                            tokenizer=FakeTokenizer())
    payload = "满窗口的原文材料。" * 500
    r = runner.run("S01", payload)
    assert r.ok and r.subject == "S01" and r.refs == ("S01",)
    assert r.window_peak > 0 and r.tokens_billed > 0
    dumped = json.dumps(r.__dict__, ensure_ascii=False)
    assert "满窗口的原文材料" not in dumped        # 过程（原文）不在回传物里


def test_brief_is_the_only_mainline_payload():
    runner = SubagentRunner(_simple_worker, window_tokens=4000)
    r = runner.run("S02", "材料")
    assert r.brief() == "[S02] 结论：要点一；要点二"


# ── 契约 2：失败结构化回传 ───────────────────────────────────
def test_overflow_becomes_structured_failure():
    """子窗口越限：死自己，外面收 ok=False + 预算说明（不是异常不是空）。"""
    runner = SubagentRunner(_simple_worker, window_tokens=200,
                            tokenizer=FakeTokenizer())
    r = runner.run("S17", "超长材料" * 1000)          # ≈1000 tok > 200
    assert not r.ok
    assert "子窗口越限" in r.error and "200" in r.error
    assert "Traceback" not in r.error


def test_generic_exception_contained():
    """worker 内任意异常都不外溢——隔离边界是绝对的。"""
    def bad_worker(subject, payload, ledger):
        raise ValueError("worker 内部炸了")

    r = SubagentRunner(bad_worker, window_tokens=1000).run("S03", "x")
    assert not r.ok and r.error.startswith("ValueError")


def test_failed_is_not_empty_conclusion():
    """红线：失败 ≠ 空结论——brief() 显式声明，主窗口能区分「没内容」和「没干成」。"""
    runner = SubagentRunner(_simple_worker, window_tokens=100,
                            tokenizer=FakeTokenizer())
    r = runner.run("S05", "长" * 4000)
    assert not r.ok
    assert "⛔" in r.brief() and "不等于该源无内容" in r.brief()


# ── 契约 3：子窗口物理预算 ───────────────────────────────────
def test_records_before_death_diagnostics():
    """记录先于死亡：失败结果仍回传尝试时的窗口峰值（尸检数字）。"""
    runner = SubagentRunner(_simple_worker, window_tokens=300,
                            tokenizer=FakeTokenizer())
    r = runner.run("S28", "料" * 4000)                # 尝试 ≈1000 tok
    assert not r.ok and r.window_peak > 300           # 峰值=被拒的那次尝试


def test_window_tokens_defaults_from_settings(monkeypatch):
    monkeypatch.setitem(settings.__dict__, "subagent_window_tokens", 777)
    assert SubagentRunner(_simple_worker).window_tokens == 777


# ── 契约 4：长途跑法 ─────────────────────────────────────────
def test_isolated_longhaul_hero():
    """主角行：主窗峰值坍缩到 ~700（vs 压缩档 5,272），零压缩、零泄漏、20/20。"""
    from eval_agent.harness_runs import run_isolated_longhaul
    r = run_isolated_longhaul(sub_window_tokens=4000)
    assert r["completed_sources"] == 30 and r["failed_sources"] == []
    assert r["main_peak_tokens"] < 1000               # 注意力杠杆的核心数字
    assert r["sub_peak_tokens"] <= 4000
    assert r["presence_hits"] == 20 and r["contradiction_discoverable"]
    assert r["compactions"] == 0                      # 主窗低到不需要压缩
    assert not r["process_leaked"]                    # 原文未渗入主窗


def test_isolated_longhaul_failure_line():
    """失败线：子窗 1200 装不下三篇超长——结构化失败，主流程不陪葬。"""
    from eval_agent.harness_runs import run_isolated_longhaul
    r = run_isolated_longhaul(sub_window_tokens=1200)
    assert r["failed_sources"] == ["S05", "S17", "S28"]
    assert r["completed_sources"] == 27
    assert r["presence_hits"] == 18                   # 失败源的两条深埋事实同去
    assert set(r["missing_facts"]) == {"F05", "F19"}


def test_isolated_longhaul_shaped_composition():
    """机制组合（L04×L05）：子窗内先整形——完赛无失败，但深埋事实丢失有声明。"""
    from eval_agent.harness_runs import run_isolated_longhaul
    r = run_isolated_longhaul(sub_window_tokens=1200, shape_in_sub=True)
    assert r["completed_sources"] == 30 and r["failed_sources"] == []
    assert r["sub_peak_tokens"] <= 1200               # 整形让子窗真装下了
    assert r["presence_hits"] == 18                   # 代价：截断砍掉的深埋事实
    assert set(r["missing_facts"]) == {"F05", "F19"}


def test_isolated_longhaul_deterministic():
    from eval_agent.harness_runs import run_isolated_longhaul
    a = json.dumps(run_isolated_longhaul(sub_window_tokens=4000),
                   ensure_ascii=False, sort_keys=True)
    b = json.dumps(run_isolated_longhaul(sub_window_tokens=4000),
                   ensure_ascii=False, sort_keys=True)
    assert a == b
