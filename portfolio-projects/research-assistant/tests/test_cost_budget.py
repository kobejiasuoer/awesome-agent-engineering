"""AgentOps L02 测试：轨迹级成本预算。

测试原则（对齐 conftest.py）：
    - 不调用真实 LLM（用 FakeLLM，其响应无 usage_metadata → 走估算路径）
    - 开关默认关 → 现状行为不变
    - 开了 enable_cost_budget → 软预算降级 / 硬预算诚实收尾
"""
from __future__ import annotations

import pytest

from research_assistant import config
from research_assistant.cost_budget import (
    extract_usage, NodeCostTracker, record_call, reset_tracker, get_tracker,
    token_delta, _decide_cost_mode, should_truncate_for_cost, pick_model_for_mode,
)


class _FakeResp:
    """模拟 LLM 响应（带或不带 usage_metadata）。"""
    def __init__(self, content="hi", usage=None):
        self.content = content
        self.usage_metadata = usage


# ── extract_usage：取真实 token 或估算 ──────────────────────

def test_extract_usage_from_metadata():
    """有 usage_metadata → 取真实 token。"""
    resp = _FakeResp("hi", usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150})
    u = extract_usage(resp)
    assert u["total_tokens"] == 150
    assert u["estimated"] is False


def test_extract_usage_estimated_when_no_metadata():
    """无 usage_metadata → 按字符/4 估算，标 estimated=True。"""
    resp = _FakeResp("abcdefgh", usage=None)  # 8 字符 → 2 token
    u = extract_usage(resp)
    assert u["total_tokens"] == 2
    assert u["estimated"] is True


def test_extract_usage_estimated_at_least_1():
    """空内容 → 至少 1 token（避免除零）。"""
    resp = _FakeResp("", usage=None)
    u = extract_usage(resp)
    assert u["total_tokens"] >= 1
    assert u["estimated"] is True


# ── NodeCostTracker：分节点累计 ─────────────────────────────

def test_tracker_accumulates_by_node():
    t = NodeCostTracker()
    t.add("writer", {"total_tokens": 100, "estimated": False})
    t.add("writer", {"total_tokens": 50, "estimated": False})
    t.add("reviewer", {"total_tokens": 30, "estimated": False})
    assert t.total() == 180
    assert t.by_node["writer"]["total_tokens"] == 150
    assert t.by_node["writer"]["calls"] == 2


def test_tracker_report_sorts_by_cost():
    """报表应按 token 降序（吞金兽在前）。"""
    t = NodeCostTracker()
    t.add("reviewer", {"total_tokens": 30, "estimated": False})
    t.add("writer", {"total_tokens": 200, "estimated": False})
    report = t.report()
    # writer (200) 应排在 reviewer (30) 前面
    assert report.index("writer") < report.index("reviewer")


def test_tracker_report_shows_estimated_tag():
    t = NodeCostTracker()
    t.add("writer", {"total_tokens": 100, "estimated": True})
    assert "估算" in t.report()


# ── reset_tracker / record_call：模块级单例 ─────────────────

def test_reset_tracker_clears():
    reset_tracker()
    record_call("x", _FakeResp("hello", usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}))
    assert get_tracker().total() == 2
    reset_tracker()
    assert get_tracker().total() == 0


# ── _decide_cost_mode：软/硬预算判断 ────────────────────────

def test_cost_mode_normal_when_disabled():
    config.settings.__dict__["enable_cost_budget"] = False
    config.settings.__dict__["max_budget_tokens"] = 100
    assert _decide_cost_mode(99999) == "normal"


def test_cost_mode_normal_within_budget():
    config.settings.__dict__["enable_cost_budget"] = True
    config.settings.__dict__["max_budget_tokens"] = 1000
    assert _decide_cost_mode(500) == "normal"


def test_cost_mode_frugal_at_80_percent():
    """软预算 80% → frugal（降级 flash）。"""
    config.settings.__dict__["enable_cost_budget"] = True
    config.settings.__dict__["max_budget_tokens"] = 1000
    assert _decide_cost_mode(800) == "frugal"
    assert _decide_cost_mode(850) == "frugal"


def test_cost_mode_over_budget_at_100_percent():
    """硬预算 100% → over_budget。"""
    config.settings.__dict__["enable_cost_budget"] = True
    config.settings.__dict__["max_budget_tokens"] = 1000
    assert _decide_cost_mode(1000) == "over_budget"
    assert _decide_cost_mode(1500) == "over_budget"


# ── token_delta：返回增量 + mode ────────────────────────────

def test_token_delta_returns_increment_not_total():
    """token_delta 返回本次调用的增量（非累计），让 reducer 累加。"""
    reset_tracker()
    config.settings.__dict__["enable_cost_budget"] = False
    d1 = token_delta("writer", _FakeResp("hi", usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}))
    d2 = token_delta("writer", _FakeResp("hi", usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}))
    # 每次 delta 是 15（本次调用），不是累计
    assert d1["token_usage"] == 15
    assert d2["token_usage"] == 15


# ── should_truncate_for_cost：硬预算诚实收尾 ────────────────

def test_should_truncate_cost_off():
    config.settings.__dict__["enable_cost_budget"] = False
    config.settings.__dict__["max_budget_tokens"] = 100
    t, r = should_truncate_for_cost({"token_usage": 9999})
    assert t is False


def test_should_truncate_cost_exceeded():
    config.settings.__dict__["enable_cost_budget"] = True
    config.settings.__dict__["max_budget_tokens"] = 100
    t, r = should_truncate_for_cost({"token_usage": 150})
    assert t is True
    assert "成本预算" in r


def test_should_truncate_cost_within_budget():
    config.settings.__dict__["enable_cost_budget"] = True
    config.settings.__dict__["max_budget_tokens"] = 1000
    t, r = should_truncate_for_cost({"token_usage": 500})
    assert t is False


# ── pick_model_for_mode：节俭模式降级 ──────────────────────

def test_pick_model_normal():
    assert pick_model_for_mode("glm-4", "glm-4-flash", "normal") == "glm-4"


def test_pick_model_frugal_downgrades():
    assert pick_model_for_mode("glm-4", "glm-4-flash", "frugal") == "glm-4-flash"
    assert pick_model_for_mode("glm-4", "glm-4-flash", "over_budget") == "glm-4-flash"
