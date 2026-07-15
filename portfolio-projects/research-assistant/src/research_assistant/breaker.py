"""手写熔断器：治持续故障的快速失败（AgentOps L03）。

为什么自己写不引 pybreaker：
    熔断器就是一个三态状态机（closed/open/half-open）+ 几个计数器，几十行。
    写出来才懂每种故障形态该用什么策略（重试 vs 熔断），引重依赖把机制藏进黑盒。

熔断器 vs 重试的区别（本课方案对比的核心）：
    - 重试（治抖动）：偶发失败重试几次就好——网络抖一下、限流一下。
    - 熔断（治持续故障）：连续失败 N 次 → 打开熔断，快速失败不再等超时 →
      冷却后半开试探一次 → 成功则关闭，失败则继续开。
    - 雪崩放大器：无限重试遇到持续故障 = 每个请求都等满超时 × 重试次数 = 雪崩。
      熔断器就是阻断这个放大。

按工具实例隔离：每个 web_search / browser 实例一个独立熔断器（一个挂了不影响别的）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable

from .logging_config import get_logger

log = get_logger("breaker")


class CircuitState(str, Enum):
    CLOSED = "closed"      # 正常放行（失败计数）
    OPEN = "open"          # 熔断打开（快速失败，不等超时）
    HALF_OPEN = "half_open"  # 半开（冷却后放一个试探请求）


@dataclass
class CircuitBreaker:
    """单个工具实例的熔断器。

    状态机：
        closed ──连续 fail_threshold 次失败──→ open
        open ──冷却 cooldown 秒──→ half_open
        half_open ──试探成功──→ closed
        half_open ──试探失败──→ open（重新计时）

    不引锁（asyncio 单线程，协作式调度，无竞态）。
    """
    name: str = "default"
    fail_threshold: int = 3        # 连续失败几次打开
    cooldown: float = 30.0         # 打开后冷却多久才半开试探
    state: CircuitState = CircuitState.CLOSED
    _fail_count: int = 0
    _opened_at: float = 0.0        # 打开的时间戳
    # 统计（给 run summary 用，L07）
    total_calls: int = 0
    total_failures: int = 0
    total_fast_failures: int = 0   # 熔断打开时的快速失败次数

    def allow(self) -> bool:
        """是否放行调用（closed/half_open 放行，open 看冷却）。"""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            # 冷却期过了 → 半开（放一个试探）
            if time.monotonic() - self._opened_at >= self.cooldown:
                self.state = CircuitState.HALF_OPEN
                log.info(f"熔断器[{self.name}] open→half_open（冷却结束，试探一次）")
                return True
            # 还在冷却期 → 快速失败
            self.total_fast_failures += 1
            return False
        # half_open：只放一个试探（已经在 allow 时转 half_open 了）
        return True

    def record_success(self):
        """记录成功：half_open → closed，清计数。"""
        self.total_calls += 1
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            log.info(f"熔断器[{self.name}] half_open→closed（试探成功，恢复）")
        self._fail_count = 0

    def record_failure(self):
        """记录失败：累计，超阈值 → open。"""
        self.total_calls += 1
        self.total_failures += 1
        self._fail_count += 1
        if self.state == CircuitState.HALF_OPEN:
            # 半开试探失败 → 重新打开
            self._trip()
            log.warning(f"熔断器[{self.name}] half_open→open（试探失败，重新熔断）")
        elif self._fail_count >= self.fail_threshold:
            self._trip()
            log.warning(f"熔断器[{self.name}] closed→open（连续 {self._fail_count} 次失败）")

    def _trip(self):
        self.state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._fail_count = 0

    def summary(self) -> dict:
        return {
            "name": self.name, "state": self.state.value,
            "calls": self.total_calls, "failures": self.total_failures,
            "fast_failures": self.total_fast_failures,
        }


# ── 按工具实例隔离的注册表 ──────────────────────────────────
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str, fail_threshold: int = 3, cooldown: float = 30.0) -> CircuitBreaker:
    """获取/创建一个工具实例的熔断器（按 name 隔离）。"""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(
            name=name, fail_threshold=fail_threshold, cooldown=cooldown)
    return _breakers[name]


def all_breakers_summary() -> list[dict]:
    """所有熔断器状态汇总（给 run summary 用）。"""
    return [b.summary() for b in _breakers.values()]


def reset_breakers():
    """测试用：清空所有熔断器。"""
    _breakers.clear()


async def call_with_breaker(
    breaker: CircuitBreaker,
    fn: Callable[..., Awaitable],
    *args, **kwargs,
):
    """用熔断器包装一次 async 调用。

    返回结构化结果（L03 诚实降级协议）：
        {"status": "ok"|"degraded"|"failed", "content": ..., "reason": ...}
    - ok：调用成功
    - degraded：熔断打开快速失败 / 超时（不等的失败）
    - failed：调用本身抛错（等了的失败）
    """
    if not breaker.allow():
        return {"status": "degraded", "content": "",
                "reason": f"熔断器打开（连续失败≥{breaker.fail_threshold}），快速失败不等待"}
    try:
        result = await fn(*args, **kwargs)
        breaker.record_success()
        return {"status": "ok", "content": result, "reason": ""}
    except Exception as e:
        breaker.record_failure()
        return {"status": "failed", "content": "",
                "reason": f"{type(e).__name__}: {e}"}
