"""鉴权 + 限流单测：401 / 429 / 200 + 公开端点（LLMOps L04）。

用 FastAPI TestClient 打进程内服务，不打真实 LLM。
通过 monkeypatch 配置 settings.api_keys 控制鉴权开关。
"""
from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kb_qa import auth
from kb_qa.auth import SlidingWindowLimiter, get_limiter


# ── 构造一个最小 app，复用 kb_qa.auth 的真实依赖 ──────────────────
def _make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.post("/api/ask", dependencies=[__import__("fastapi").Depends(auth.rate_limit)])
    async def ask():
        return {"answer": "ok"}

    @app.post("/api/upload", dependencies=[__import__("fastapi").Depends(auth.rate_limit)])
    async def upload():
        return {"ok": True}

    return app


VALID_KEY = "kb-test-valid-123"


@pytest.fixture
def app_with_auth(monkeypatch: pytest.MonkeyPatch):
    """配置一个合法 key 并启用鉴权；重置限流器单例。"""
    monkeypatch.setattr(auth.settings, "api_keys", VALID_KEY)
    monkeypatch.setattr(auth.settings, "auth_enabled", True)
    monkeypatch.setattr(auth.settings, "rate_limit_per_minute", 3)
    # 重置单例限流器（让新的 rate_limit_per_minute 生效）
    auth._limiter = None
    yield _make_app()
    auth._limiter = None


@pytest.fixture
def app_no_auth(monkeypatch: pytest.MonkeyPatch):
    """未配 key → 鉴权跳过（开箱即用模式）。"""
    monkeypatch.setattr(auth.settings, "api_keys", "")
    monkeypatch.setattr(auth.settings, "auth_enabled", True)
    monkeypatch.setattr(auth.settings, "rate_limit_per_minute", 100)
    auth._limiter = None
    yield _make_app()
    auth._limiter = None


# ── 鉴权：401 ─────────────────────────────────────────────────────
def test_no_key_returns_401(app_with_auth):
    """无 Authorization 头 → 401。"""
    client = TestClient(app_with_auth)
    r = client.post("/api/ask", json={"q": "x"})
    assert r.status_code == 401


def test_wrong_key_returns_401(app_with_auth):
    """错误 key → 401。"""
    client = TestClient(app_with_auth)
    r = client.post("/api/ask", json={"q": "x"},
                    headers={"Authorization": "Bearer wrong-key"})
    assert r.status_code == 401


def test_valid_key_returns_200(app_with_auth):
    """正确 key → 200。"""
    client = TestClient(app_with_auth)
    r = client.post("/api/ask", json={"q": "x"},
                    headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert r.status_code == 200


def test_x_api_key_header_also_works(app_with_auth):
    """X-API-Key 头也接受（兼容部分团队习惯）。"""
    client = TestClient(app_with_auth)
    r = client.post("/api/ask", json={"q": "x"},
                    headers={"X-API-Key": VALID_KEY})
    assert r.status_code == 200


# ── 限流：429 ─────────────────────────────────────────────────────
def test_rate_limit_returns_429_after_quota(app_with_auth):
    """超过每分钟上限 → 第 N+1 次 429。"""
    client = TestClient(app_with_auth)
    headers = {"Authorization": f"Bearer {VALID_KEY}"}
    codes = [client.post("/api/ask", json={"q": "x"}, headers=headers).status_code
             for _ in range(4)]  # 上限 3，第 4 次应被限
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_rate_limit_isolated_per_key(app_with_auth, monkeypatch: pytest.MonkeyPatch):
    """不同 key 独立配额（A 打满不影响 B）。"""
    monkeypatch.setattr(auth.settings, "api_keys", f"{VALID_KEY},kb-other-456")
    client = TestClient(app_with_auth)
    # key A 打满 3 次
    for _ in range(3):
        client.post("/api/ask", json={"q": "x"},
                    headers={"Authorization": f"Bearer {VALID_KEY}"})
    # key A 第 4 次 → 429
    r_a = client.post("/api/ask", json={"q": "x"},
                      headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert r_a.status_code == 429
    # key B 第 1 次 → 200（独立配额）
    r_b = client.post("/api/ask", json={"q": "x"},
                      headers={"Authorization": "Bearer kb-other-456"})
    assert r_b.status_code == 200


# ── 公开端点 ──────────────────────────────────────────────────────
def test_health_is_public(app_with_auth):
    """health 接口不挂鉴权（监控探针不该被挡）。"""
    client = TestClient(app_with_auth)
    r = client.get("/api/health")
    assert r.status_code == 200


# ── 开箱即用：未配 key 不锁死 ─────────────────────────────────────
def test_no_keys_configured_allows_all(app_no_auth):
    """没配 API_KEYS → 鉴权跳过，开发模式放行（但限流按 IP 仍生效）。"""
    client = TestClient(app_no_auth)
    r = client.post("/api/ask", json={"q": "x"})
    assert r.status_code == 200


# ── 限流器算法本身 ────────────────────────────────────────────────
def test_sliding_window_expires(monkeypatch: pytest.MonkeyPatch):
    """滑动窗口：窗口过期后恢复配额（无边界突发）。"""
    limiter = SlidingWindowLimiter(max_requests=2, window_seconds=1)
    assert limiter.allow("k") is True
    assert limiter.allow("k") is True
    assert limiter.allow("k") is False   # 满
    time.sleep(1.05)                       # 等窗口过期
    assert limiter.allow("k") is True      # 恢复


def test_api_keys_set_parsing():
    """config 把逗号分隔的 key 串解析成集合（O(1) 查询）。"""
    from kb_qa.config import Settings
    s = Settings(api_keys=" kb-a , kb-b ,  ")  # type: ignore[call-arg]
    assert s.api_keys_set == {"kb-a", "kb-b"}
