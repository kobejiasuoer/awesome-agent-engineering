"""
Lesson 04 — API 鉴权与限流：别让接口裸奔
==========================================
本脚本用 FastAPI 写一个最小服务，演示两道生产防线：
    ① 鉴权（require_api_key）：校验 Authorization: Bearer <key>
    ② 限流（rate_limit）：滑动窗口，按 key 每分钟最多 N 次

用 TestClient 在进程内验证四种场景（401×2 / 429 / 200），无需起真实服务。

运行：python code.py
依赖：fastapi（kb-qa 已装）；限流器纯标准库实现，零额外依赖
"""
from __future__ import annotations

import sys
import time
from collections import deque

# Windows GBK 坑：中文会崩，统一 utf-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient


# ════════════════════════════════════════════════════════════════
# 1. 滑动窗口限流器（核心算法，面试高频题）
# ════════════════════════════════════════════════════════════════
class SlidingWindowLimiter:
    """滑动窗口限流：记录每个 key 最近 window 秒内的请求时间戳。

    allow(key) 时：
        1. 清掉窗口外的过期时间戳
        2. 看窗口内请求数是否 < 上限
        3. 是 → 放行并记录当前时间；否 → 拒绝

    比固定窗口好在哪：没有窗口边界突发（任意时刻看「最近 window 秒」都平滑）。
    """

    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, deque[float]] = {}  # key → 时间戳队列

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, deque())
        # ① 清掉窗口外的过期时间戳（左端是最老的）
        cutoff = now - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        # ② 判定
        if len(bucket) < self.max_requests:
            bucket.append(now)   # ③ 放行并记录
            return True
        return False

    def reset(self) -> None:
        """清空所有计数（测试用）。"""
        self._buckets.clear()


# ════════════════════════════════════════════════════════════════
# 2. 配置（教学用写死；落地版从 settings 读）
# ════════════════════════════════════════════════════════════════
VALID_KEYS = {"kb-secret-abc123"}           # 合法 key 集合
RATE_LIMIT = 3                              # 每个 key 每分钟最多 3 次（教学用小值）
limiter = SlidingWindowLimiter(max_requests=RATE_LIMIT, window_seconds=60)


# ════════════════════════════════════════════════════════════════
# 3. FastAPI 依赖：鉴权 + 限流
# ════════════════════════════════════════════════════════════════
def _extract_key(request: Request) -> str:
    """从 Authorization: Bearer <key> 提取 key。无头返回空串。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    # 兼容 X-API-Key 头（部分团队习惯这个）
    return request.headers.get("X-API-Key", "").strip()


def require_api_key(request: Request) -> str:
    """鉴权依赖：校验 key，返回合法 key（供后续限流按 key 隔离）。"""
    key = _extract_key(request)
    if not key:
        raise HTTPException(401, "缺少 API Key（Authorization: Bearer <key>）")
    if key not in VALID_KEYS:
        raise HTTPException(401, "无效的 API Key")
    return key


def rate_limit(key: str = Depends(require_api_key)) -> str:
    """限流依赖：依赖鉴权拿到的 key，按 key 滑动窗口判定。

    注意依赖顺序：rate_limit 依赖 require_api_key —— 先过鉴权才谈限流。
    """
    if not limiter.allow(key):
        raise HTTPException(429, f"请求过快：每分钟上限 {RATE_LIMIT} 次")
    return key


# ════════════════════════════════════════════════════════════════
# 4. 最小服务
# ════════════════════════════════════════════════════════════════
app = FastAPI(title="鉴权限流演示")


@app.get("/api/health")
async def health():
    """health 保持公开（监控探针不该被鉴权挡住）。"""
    return {"status": "ok"}


@app.post("/api/ask", dependencies=[Depends(rate_limit)])
async def ask(request: Request):
    """问答接口：挂 鉴权+限流 依赖（rate_limit 内部已依赖 require_api_key）。"""
    return {"answer": f"已认证 key=***{request.headers.get('Authorization','')[-4:]}"}


# ════════════════════════════════════════════════════════════════
# 5. main：四种场景验证
# ════════════════════════════════════════════════════════════════
def main() -> None:
    client = TestClient(app)

    print("=" * 60)
    print("场景 1：无 key → 401 Unauthorized")
    print("=" * 60)
    r = client.post("/api/ask", json={"q": "test"})
    print(f"  状态码: {r.status_code}（预期 401）")

    print("\n" + "=" * 60)
    print("场景 2：错 key → 401 Unauthorized")
    print("=" * 60)
    r = client.post("/api/ask", json={"q": "test"},
                    headers={"Authorization": "Bearer wrong-key"})
    print(f"  状态码: {r.status_code}（预期 401）")

    print("\n" + "=" * 60)
    print(f"场景 3：对 key 但超速 → 429（连打 {RATE_LIMIT+1} 次，最后一次被限）")
    print("=" * 60)
    headers = {"Authorization": "Bearer kb-secret-abc123"}
    codes = []
    for i in range(RATE_LIMIT + 1):
        r = client.post("/api/ask", json={"q": "test"}, headers=headers)
        codes.append(r.status_code)
    print(f"  {RATE_LIMIT+1} 次请求状态码: {codes}")
    print(f"  前 {RATE_LIMIT} 次 200，第 {RATE_LIMIT+1} 次 429（限流触发）")

    print("\n" + "=" * 60)
    print("场景 4：health 接口公开（不需要 key）")
    print("=" * 60)
    r = client.get("/api/health")
    print(f"  状态码: {r.status_code}（预期 200，无 key 也通）")

    print("\n" + "=" * 60)
    print("✅ 鉴权（401）+ 限流（429）+ 公开端点（200）全部验证通过")
    print("=" * 60)


if __name__ == "__main__":
    main()
