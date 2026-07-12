"""轨迹评估器测试（Frontier L08）。

测试不依赖真实 LLM（用规则降级模式 + mock LLM）。
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from research_assistant.trajectory_eval import TrajectoryEvaluator, MetricCard


@pytest.fixture
def evaluator():
    """无 LLM 的评估器（规则降级模式）。"""
    return TrajectoryEvaluator(llm=None)


# ── 基本评估 ──────────────────────────────────────────────────
def test_evaluate_empty_trace(evaluator):
    """空轨迹应返回默认指标卡。"""
    card = evaluator.evaluate([])
    assert card.total_steps == 0
    assert not card.success


def test_evaluate_basic_trace(evaluator):
    """基本轨迹应正确统计步数和节点。"""
    trace = [
        {"run": 1, "step": 1, "node": "split", "input": "主题", "output": "子问题"},
        {"run": 1, "step": 2, "node": "researcher", "input": "子题", "output": "发现"},
        {"run": 1, "step": 3, "node": "summarize", "input": "findings", "output": "摘要"},
        {"run": 1, "step": 4, "node": "writer", "input": "摘要", "output": "报告内容"},
        {"run": 1, "step": 5, "node": "reviewer", "input": "报告", "output": "pass"},
    ]
    card = evaluator.evaluate(trace, run_id="1")
    assert card.total_steps == 5
    assert card.node_count == 5
    assert card.success  # 最后有 writer/reviewer 且非空


# ── 循环检测 ──────────────────────────────────────────────────
def test_detect_loops(evaluator):
    """连续 3+ 次同节点且输出相似应检测为循环。"""
    trace = [
        {"run": 1, "step": 1, "node": "researcher", "input": "q", "output": "同样的发现"},
        {"run": 1, "step": 2, "node": "researcher", "input": "q", "output": "同样的发现"},
        {"run": 1, "step": 3, "node": "researcher", "input": "q", "output": "同样的发现"},
    ]
    card = evaluator.evaluate(trace, run_id="1")
    assert card.loops_detected >= 1
    assert "researcher" in card.loop_nodes


def test_no_loops_normal_trace(evaluator):
    """正常轨迹不应检测到循环。"""
    trace = [
        {"run": 1, "step": 1, "node": "split", "output": "子问题1"},
        {"run": 1, "step": 2, "node": "researcher", "output": "发现1"},
        {"run": 1, "step": 3, "node": "writer", "output": "报告"},
    ]
    card = evaluator.evaluate(trace, run_id="1")
    assert card.loops_detected == 0


# ── 机制检测 ──────────────────────────────────────────────────
def test_detect_memory_recall(evaluator):
    """轨迹含记忆命中信号应检测到记忆召回。"""
    trace = [
        {"run": 1, "step": 1, "node": "researcher", "input": "q", "output": "记忆命中：旧结论X"},
    ]
    card = evaluator.evaluate(trace, run_id="1")
    assert card.has_memory_recall


def test_detect_reflection(evaluator):
    """轨迹含反思信号应检测到反思。"""
    trace = [
        {"run": 1, "step": 1, "node": "reviewer", "output": "反思：搜索词太宽泛，下次加年份"},
    ]
    card = evaluator.evaluate(trace, run_id="1")
    assert card.has_reflection


def test_detect_conflict_correction(evaluator):
    """轨迹含冲突信号应检测到冲突修正。"""
    trace = [
        {"run": 1, "step": 1, "node": "reviewer", "output": "检测到冲突，触发re_research"},
    ]
    card = evaluator.evaluate(trace, run_id="1")
    assert card.has_conflict_correction


def test_detect_code_execution(evaluator):
    """轨迹含代码执行信号应检测到代码执行。"""
    trace = [
        {"run": 1, "step": 1, "node": "writer", "output": "代码计算结果：42\n附录：```python\nprint(42)\n```"},
    ]
    card = evaluator.evaluate(trace, run_id="1")
    assert card.has_code_execution


# ── 工具调用统计 ──────────────────────────────────────────────
def test_tool_call_stats(evaluator):
    """工具调用次数和成功率应正确统计。"""
    trace = [
        {"run": 1, "step": 1, "node": "researcher", "output": "正常发现"},
        {"run": 1, "step": 2, "node": "researcher", "output": "搜索失败"},
        {"run": 1, "step": 3, "node": "writer", "output": "报告"},
    ]
    card = evaluator.evaluate(trace, run_id="1")
    assert card.tool_calls == 2  # 2 个 researcher
    assert card.tool_success_rate == 0.5  # 1 成功 / 2 总


# ── 失败归因 ──────────────────────────────────────────────────
def test_failure_attribution_retrieval(evaluator):
    """researcher 失败应归因到检索。"""
    trace = [
        {"run": 1, "step": 1, "node": "researcher", "output": "搜索超时，失败"},
    ]
    card = evaluator.evaluate(trace, run_id="1")
    assert "检索" in card.failure_attribution


def test_failure_attribution_planning(evaluator):
    """split 失败应归因到规划。"""
    trace = [
        {"run": 1, "step": 1, "node": "split", "output": "拆解失败，错误"},
    ]
    card = evaluator.evaluate(trace, run_id="1")
    assert "规划" in card.failure_attribution


# ── 文件评估 ──────────────────────────────────────────────────
def test_evaluate_file(evaluator, tmp_path):
    """应能评估 jsonl 轨迹文件（按 run 分组）。"""
    trace_file = tmp_path / "trace.jsonl"
    records = [
        {"run": 1, "step": 1, "node": "split", "output": "子问题"},
        {"run": 1, "step": 2, "node": "writer", "output": "报告"},
        {"run": 2, "step": 1, "node": "split", "output": "子问题2"},
        {"run": 2, "step": 2, "node": "writer", "output": "报告2"},
    ]
    with open(trace_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    cards = evaluator.evaluate_file(str(trace_file))
    assert len(cards) == 2  # 2 个 run
    assert cards[0].run_id == "1"
    assert cards[1].run_id == "2"


def test_evaluate_file_nonexistent(evaluator):
    """不存在的文件应返回空列表。"""
    cards = evaluator.evaluate_file("nope.jsonl")
    assert cards == []


# ── LLM judge ─────────────────────────────────────────────────
def test_judge_success_with_llm():
    """有 LLM 时应用 LLM judge 判断成功。"""
    class MockLLM:
        def invoke(self, prompt):
            class R:
                content = "成功"
            return R()

    evaluator = TrajectoryEvaluator(llm=MockLLM())
    trace = [{"run": 1, "step": 1, "node": "writer", "output": "报告"}]
    card = evaluator.evaluate(trace, run_id="1")
    assert card.success


# ── 格式化 ────────────────────────────────────────────────────
def test_format_card(evaluator):
    """指标卡应能格式化成可读文本。"""
    card = MetricCard(run_id="test", success=True, total_steps=5, node_count=4)
    text = evaluator.format_card(card)
    assert "指标卡" in text
    assert "✅" in text  # success
    assert "5" in text   # steps
