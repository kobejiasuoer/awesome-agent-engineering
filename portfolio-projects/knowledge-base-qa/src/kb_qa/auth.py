"""API 鉴权 + 限流：FastAPI 依赖实现（LLMOps L04）。

两道生产防线：
    require_api_key —— 校验 Authorization: Bearer <key>（401 防未授权）
    rate_limit      —— 按 key 滑动窗口限流（429 防刷爆）

设计：
    - 滑动窗口自实现（标准库 deque），零额外依赖，算法可见可教学
    - auth_enabled 开关：配了 API_KEYS 才启用鉴权；没配则跳过（开箱即用不锁死）
    - 限流按 key 隔离：每个调用方独立配额，单 key 泄露不影响全局
"""
from __future__ import annotations

import time
from collections import deque

from fastapi import HTTPException, Request

from .config import settings
from .observability import get_logger, log_event

_log = get_logger("kb_qa.auth")


# ════════════════════════════════════════════════════════════════
# 滑动窗口限流器
# ════════════════════════════════════════════════════════════════
class SlidingWindowLimiter:
    """每个 key 维护一个「最近 window 秒内的时间戳队列」。

    比固定窗口优：无边界突发，任意时刻看「最近 window 秒」的请求数都平滑。
    单机版：计数存内存。多副本部署应换 Redis 后端（计数跨实例共享）。
    """

    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, deque())
        cutoff = now - self.window
        # 清掉窗口外的过期时间戳
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) < self.max_requests:
            bucket.append(now)
            return True
        return False

    def reset(self) -> None:
        """清空计数（测试用）。"""
        self._buckets.clear()


# 进程级单例限流器：按 settings.rate_limit_per_minute 配置
_limiter: SlidingWindowLimiter | None = None


def get_limiter() -> SlidingWindowLimiter:
    global _limiter
    if _limiter is None:
        _limiter = SlidingWindowLimiter(
            max_requests=settings.rate_limit_per_minute,
            window_seconds=60,
        )
    return _limiter


# ════════════════════════════════════════════════════════════════
# 鉴权 + 限流依赖
# ════════════════════════════════════════════════════════════════
def _auth_enabled() -> bool:
    """鉴权是否启用：开关开 且 配了至少一个 key。

    没配 key 时跳过鉴权 → 保证开箱即用（本地开发不锁死）。
    生产部署务必配 API_KEYS，否则等于裸奔。
    """
    return settings.auth_enabled and len(settings.api_keys_set) > 0


def _extract_key(request: Request) -> str:
    """从 Authorization: Bearer <key> 或 X-API-Key 提取 key。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return request.headers.get("X-API-Key", "").strip()


def require_api_key(request: Request) -> str:
    """鉴权依赖：校验 API key。返回合法 key（供限流按 key 隔离）。

    - 未启用鉴权 → 直接返回空串（放行，开发模式）
    - 启用但没 key / key 错 → 401
    """
    if not _auth_enabled():
        return "anonymous"  # 开发模式放行
    key = _extract_key(request)
    if not key:
        raise HTTPException(401, "缺少 API Key（Authorization: Bearer <key>）")
    if key not in settings.api_keys_set:
        log_event(_log, "auth.rejected", level=30,  # WARNING
                  reason="invalid_key")
        raise HTTPException(401, "无效的 API Key")
    return key


def rate_limit(request: Request) -> str:
    """限流依赖：先鉴权（拿 key），再按 key 滑动窗口判定。

    依赖 require_api_key —— 先过鉴权才谈限流。
    未启用鉴权时按客户端 IP 限流（兜底，防完全裸奔）。
    """
    key = require_api_key(request)
    if key == "anonymous":
        # 开发模式：没鉴权时退化为按 IP 限流
        key = request.client.host if request.client else "unknown"
    limiter = get_limiter()
    if not limiter.allow(key):
        log_event(_log, "rate_limited", level=30, key=_masked(key))  # WARNING
        raise HTTPException(
            429,
            f"请求过快：每个 key 每分钟上限 {settings.rate_limit_per_minute} 次",
            headers={"Retry-After": "60"},
        )
    return key


def _masked(key: str) -> str:
    """日志里掩码 key，不全打（脱敏原则）。"""
    if len(key) <= 4:
        return "***"
    return "***" + key[-4:]
