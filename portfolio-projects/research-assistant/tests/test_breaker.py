"""AgentOps L03 测试：手写熔断器 + 诚实降级协议。

测试原则（对齐 conftest.py）：
    - 不调用真实 LLM / 不联网（mock 搜索函数）
    - 开关默认关 → 现状行为不变
    - 熔断器三态状态机 + 结构化降级协议
"""
from __future__ import annotations

import asyncio

import pytest

from research_assistant import config
from research_assistant.breaker import (
    CircuitBreaker, CircuitState, get_breaker, reset_breakers,
    all_breakers_summary, call_with_breaker,
)


@pytest.fixture(autouse=True)
def _restore_breaker_flags():
    """本文件测试会改 config.settings 的 L03 开关，逐测试还原默认（防泄漏）。"""
    _defaults = {
        "enable_circuit_breaker": False,
        "breaker_fail_threshold": 3,
        "breaker_cooldown": 30.0,
        "search_retry": 0,
        "search_timeout": 15,
    }
    saved = {k: config.settings.__dict__.get(k) for k in _defaults}
    reset_breakers()
    yield
    for k, v in _defaults.items():
        config.settings.__dict__[k] = v
    reset_breakers()


# ── CircuitBreaker 三态状态机 ───────────────────────────────

def test_breaker_starts_closed():
    b = CircuitBreaker(name="t", fail_threshold=3, cooldown=30)
    assert b.state == CircuitState.CLOSED
    assert b.allow() is True


def test_breaker_opens_after_threshold():
    """连续 fail_threshold 次失败 → 打开。"""
    b = CircuitBreaker(name="t", fail_threshold=3, cooldown=30)
    b.record_failure()
    b.record_failure()
    assert b.state == CircuitState.CLOSED  # 还没到 3
    b.record_failure()
    assert b.state == CircuitState.OPEN
    assert b.allow() is False  # 打开后快速失败


def test_breaker_success_resets_count():
    """成功清零失败计数（治抖动：偶发失败不累积）。"""
    b = CircuitBreaker(name="t", fail_threshold=3, cooldown=30)
    b.record_failure()
    b.record_failure()
    b.record_success()  # 成功清零
    b.record_failure()
    b.record_failure()
    assert b.state == CircuitState.CLOSED  # 只累积了 2 次，没到 3


def test_breaker_half_open_after_cooldown():
    """打开后冷却结束 → 半开（放一个试探）。"""
    b = CircuitBreaker(name="t", fail_threshold=1, cooldown=0.0)  # cooldown=0 立即半开
    b.record_failure()
    assert b.state == CircuitState.OPEN
    # cooldown=0，下次 allow 应转 half_open
    import time
    time.sleep(0.01)
    assert b.allow() is True
    assert b.state == CircuitState.HALF_OPEN


def test_breaker_half_open_success_closes():
    """半开试探成功 → 关闭。"""
    b = CircuitBreaker(name="t", fail_threshold=1, cooldown=0.0)
    b.record_failure()
    import time
    time.sleep(0.01)
    b.allow()  # 转 half_open
    b.record_success()
    assert b.state == CircuitState.CLOSED


def test_breaker_half_open_failure_reopens():
    """半开试探失败 → 重新打开。"""
    b = CircuitBreaker(name="t", fail_threshold=1, cooldown=0.0)
    b.record_failure()
    import time
    time.sleep(0.01)
    b.allow()  # 转 half_open
    b.record_failure()
    assert b.state == CircuitState.OPEN


def test_breaker_fast_failures_counted():
    """熔断打开时的快速失败被单独计数（给 run summary 用）。"""
    b = CircuitBreaker(name="t", fail_threshold=1, cooldown=30)
    b.record_failure()  # 打开
    b.allow()  # 快速失败
    b.allow()  # 快速失败
    assert b.total_fast_failures == 2


# ── 注册表隔离 ──────────────────────────────────────────────

def test_breakers_isolated_by_name():
    """不同 name 的熔断器互相隔离。"""
    reset_breakers()
    b1 = get_breaker("web_search")
    b2 = get_breaker("browser")
    b1.record_failure()
    b1.record_failure()
    b1.record_failure()
    assert b1.state == CircuitState.OPEN
    assert b2.state == CircuitState.CLOSED  # browser 不受影响


def test_all_breakers_summary():
    reset_breakers()
    b = get_breaker("web_search", fail_threshold=1)
    b.record_failure()
    summary = all_breakers_summary()
    assert len(summary) == 1
    assert summary[0]["name"] == "web_search"
    assert summary[0]["state"] == "open"


# ── call_with_breaker：结构化降级协议 ──────────────────────

@pytest.mark.asyncio
async def test_call_with_breaker_ok():
    b = CircuitBreaker(name="t", fail_threshold=3, cooldown=30)

    async def good_fn():
        return "结果"

    result = await call_with_breaker(b, good_fn)
    assert result["status"] == "ok"
    assert result["content"] == "结果"


@pytest.mark.asyncio
async def test_call_with_breaker_failed():
    b = CircuitBreaker(name="t", fail_threshold=3, cooldown=30)

    async def bad_fn():
        raise ConnectionError("连接重置")

    result = await call_with_breaker(b, bad_fn)
    assert result["status"] == "failed"
    assert "ConnectionError" in result["reason"]
    assert b.state == CircuitState.CLOSED  # 1 次还没到阈值


@pytest.mark.asyncio
async def test_call_with_breaker_degraded_when_open():
    """熔断打开 → 快速失败返回 degraded（不等超时）。"""
    b = CircuitBreaker(name="t", fail_threshold=1, cooldown=30)

    async def bad_fn():
        raise ConnectionError("挂了")

    # 第一次失败 → 打开
    await call_with_breaker(b, bad_fn)
    assert b.state == CircuitState.OPEN
    # 第二次：熔断打开，快速失败（不调 bad_fn）
    import time
    t0 = time.monotonic()
    result = await call_with_breaker(b, bad_fn)
    elapsed = time.monotonic() - t0
    assert result["status"] == "degraded"
    assert "熔断器打开" in result["reason"]
    assert elapsed < 0.1  # 快速失败，没等超时


# ── web_search_structured：诚实降级协议 ────────────────────

@pytest.mark.asyncio
async def test_web_search_structured_ok(monkeypatch):
    """enable_circuit_breaker=False 时，结构化包装返回 ok。"""
    config.settings.__dict__["enable_circuit_breaker"] = False
    from research_assistant import tools

    async def fake_wait_for(*a, **kw):
        return "搜索结果"

    # mock _ddgs_search（web_search_structured 内部走 to_thread + wait_for）
    monkeypatch.setattr(tools, "_ddgs_search", lambda q, n: "搜索结果")

    from research_assistant.tools import web_search_structured
    result = await web_search_structured("测试")
    assert result["status"] == "ok"
    assert result["content"] == "搜索结果"


@pytest.mark.asyncio
async def test_web_search_structured_degraded_on_timeout(monkeypatch):
    """超时 → degraded（不是字符串混进材料）。"""
    config.settings.__dict__["enable_circuit_breaker"] = False
    config.settings.__dict__["search_timeout"] = 1
    from research_assistant import tools
    import asyncio

    def slow_search(q, n):
        import time
        time.sleep(2)  # 超过 timeout=1
        return "不该到这里"

    monkeypatch.setattr(tools, "_ddgs_search", slow_search)

    from research_assistant.tools import web_search_structured
    result = await web_search_structured("测试")
    assert result["status"] == "degraded"
    assert "超时" in result["reason"]
    assert result["content"] == ""  # 关键：content 空，不污染材料


@pytest.mark.asyncio
async def test_web_search_structured_with_breaker_fast_fail(monkeypatch):
    """enable_circuit_breaker=True + 连续失败 → 熔断打开 → 快速失败 degraded。"""
    config.settings.__dict__["enable_circuit_breaker"] = True
    config.settings.__dict__["breaker_fail_threshold"] = 2
    config.settings.__dict__["breaker_cooldown"] = 30.0
    config.settings.__dict__["search_timeout"] = 1
    reset_breakers()
    from research_assistant import tools

    def always_fail(q, n):
        raise ConnectionError("挂了")

    monkeypatch.setattr(tools, "_ddgs_search", always_fail)

    from research_assistant.tools import web_search_structured
    # 前两次失败（达到阈值 2 → 打开）
    await web_search_structured("q1")
    await web_search_structured("q2")
    # 第三次：熔断打开，快速失败
    import time
    t0 = time.monotonic()
    result = await web_search_structured("q3")
    elapsed = time.monotonic() - t0
    assert result["status"] == "degraded"
    assert "熔断器打开" in result["reason"]
    assert elapsed < 0.5  # 快速失败
