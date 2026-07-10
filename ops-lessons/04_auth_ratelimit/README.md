# Lesson 04 — API 鉴权与限流：别让接口裸奔

> 本课目标：**给 kb-qa 的 FastAPI 服务加最基本的生产防护——鉴权（谁能调）和限流（调多快），把 `/api/upload`、`/api/ask` 从「公网裸奔」变成「有门禁有闸口」**。
>
> 学完你能回答面试官那句：**「你的接口直接暴露在公网，不怕被刷爆 token 账单吗？」**——裸奔的 LLM 接口 = 免费送给攻击者的提款机。

---

## 1. 裸奔的接口有多危险？

kb-qa 现在两个核心接口都没有任何防护：

| 接口 | 裸奔后果 | 严重程度 |
|---|---|---|
| `POST /api/upload` | 任何人能往你的服务器写文件 = **免费公网存储**，能塞满磁盘、传恶意文档 | 🔴 高 |
| `POST /api/ask` | 任何人能调你的 glm-4 = **刷爆你的 token 账单**，一天烧光额度 | 🔴 极高 |
| `GET /api/health` | 暴露内部信息（模型名、chunk 数） | 🟡 低（监控用，可公开） |

> 🎯 **核心认知**：LLM 接口和普通 CRUD 接口不一样——**每次调用都花钱**。一个没限流的 `/api/ask`，攻击者写个 `while True` 循环，几小时就能把你当月的智谱额度刷光。鉴权防「谁来调」，限流防「调多快」，两者缺一不可。

```
攻击者的视角（你的 /api/ask 裸奔时）：
   while True:
       requests.post("http://你的服务/api/ask", json={"question":"写一篇万字小说"})
   # → 每次 = glm-4 一次大调用 = 几分钱
   # → 一小时上万次 = 几百块
   # → 你的账单和额度，没了
```

---

## 2. 鉴权方案：API Key（Header）

主流的 API 鉴权两种：

| 方案 | 怎么传 | 适合 | 复杂度 |
|---|---|---|---|
| **API Key** | `Authorization: Bearer <key>` 或 `X-API-Key: <key>` | 服务间调用、内部系统 | 🟢 简单 |
| **JWT** | 登录换 token，token 带签名和过期 | 有用户体系的 C 端 | 🟠 复杂（要登录/刷新） |

kb-qa 是企业内部知识库（服务间/部门间调用），**没有用户登录体系**，所以选最简单够用的 **API Key**。

```http
POST /api/ask
Authorization: Bearer kb-secret-abc123      ← 没这个头 / 错了 → 401
{"question": "试用期多久"}
```

> 💡 为什么用 `Authorization: Bearer` 而不是自定义头？因为它是 HTTP 标准，所有网关/CDN/监控都认，而且「Bearer」语义清晰（持有此令牌者）。但内部系统用 `X-API-Key` 也完全 OK——选哪个看团队规范。

### 多 Key 管理

生产不会只有一个 key——不同调用方（前端、合作伙伴、内部脚本）各用一个，方便**单独吊销**和**按 key 限流**：

```
API_KEYS=kb-frontend-xxx, kb-partner-yyy, kb-script-zzz
# 前端泄露了？只吊销 kb-frontend-xxx，不影响别人
```

> 🎯 **每个调用方独立 key = 最小权限 + 可追溯 + 可吊销**。这是 IAM（身份访问管理）的基本原则。

---

## 3. 限流：防滥用的闸口

鉴权解决「谁能调」，但合法用户（或泄露的 key）也可能调太快。**限流（Rate Limiting）**给每个调用方设个「每分钟最多 N 次」的上限。

### 限流算法对比

| 算法 | 原理 | 特点 |
|---|---|---|
| **固定窗口** | 每分钟计数，到点清零 | 简单，但窗口边界会突发 2 倍流量 |
| **滑动窗口** | 记录每个请求的时间戳，算最近 60s 内的数量 | 平滑，内存稍多 |
| **令牌桶** | 桶里匀速生成令牌，请求消耗令牌 | 允许突发（桶满时一次性用完）|

```
固定窗口的边界问题：
   第 0:59 秒打了 100 次（满额），第 1:01 秒又打 100 次
   → 2 秒内 200 次！窗口边界处会突发

滑动窗口：
   任意时刻看「过去 60 秒」的请求数，没有边界突发
   → 更平滑，本课用这个
```

### 按 IP vs 按 Key 限流

| 维度 | 优点 | 缺点 |
|---|---|---|
| **按 Key** | 精确到调用方，泄露的 key 单独限 | 没 key 的请求没法限（但没 key 直接 401 了） |
| **按 IP** | 不需要鉴权也能限 | NAT/代理后大量用户共享一个 IP，误伤 |

> 💡 kb-qa 已有鉴权，所以**按 Key 限流**最合理：每个 key 一个独立配额。攻击者偷了一个 key，最多用这一个 key 的配额刷，不会拖垮全局。

---

## 4. 用 FastAPI 依赖注入实现（零新依赖）

FastAPI 的「依赖注入」（`Depends`）是加鉴权限流的最佳位置——**把校验逻辑写一次，多个路由复用**：

```python
from fastapi import Depends, HTTPException, Request

# 鉴权依赖：校验 API key
def require_api_key(request: Request):
    key = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if key not in settings.api_keys:
        raise HTTPException(401, "无效或缺失的 API Key")

# 限流依赖：按 key 限流
def rate_limit(request: Request):
    key = <当前key>
    if not limiter.allow(key):  # 滑动窗口判定
        raise HTTPException(429, "请求过快，请稍后再试")

# 路由上挂依赖
@app.post("/api/ask", dependencies=[Depends(require_api_key), Depends(rate_limit)])
async def ask(...): ...
```

> 🎯 **为什么用依赖注入而不是装饰器？** 因为 FastAPI 的依赖系统会自动：① 在 OpenAPI 文档里体现鉴权要求 ② 测试时可 override 依赖 ③ 多路由复用零重复。这是 FastAPI 比 Flask 优雅的地方。

### 状态码约定

| 码 | 含义 | 本课场景 |
|---|---|---|
| **200** | 正常 | key 对 + 没超限 |
| **401 Unauthorized** | 没鉴权 | 没 key / key 错 |
| **429 Too Many Requests** | 限流触发 | 调太快 |

> 这两个码是 HTTP 标准，所有监控/网关都认。**千万别自己发明「code: -1」这种私有错误码**——破坏可观测性。

---

## 5. 为什么本课自己实现限流器（而非用 slowapi）？

任务书提到 `slowapi`，但本课选择**自实现一个滑动窗口限流器**，原因：

1. **教学优先**：限流算法（滑动窗口）是面试高频题，自己写一遍才真懂；用库等于黑盒。
2. **零新依赖**：slowapi 引入额外依赖，而滑动窗口用标准库 + 一个字典就能实现，kb-qa 的依赖树更干净。
3. **生产可替换**：理解原理后，README 给出换 slowapi 的对照写法（一行装饰器），迁移无成本。

> 💡 这和 RAG 课程的「先手写 ReAct 循环再看框架」一个思路：**关键能力先手写理解，再用库提效**。自实现的限流器 ~30 行，看得见摸得着。

---

## 6. 本课代码会做什么

### `code.py`（教学，可独立跑）
- 用 FastAPI 写一个最小服务，挂上 `require_api_key` + `rate_limit` 两个依赖
- 演示三种状态：无 key → 401、错 key → 401、对 key 但超速 → 429、对 key 正常速 → 200
- 用 `TestClient` 在进程内验证，不需要起真实服务

### 落地到 kb-qa
- 新增 `src/kb_qa/auth.py`：`SlidingWindowLimiter`（滑动窗口）+ `require_api_key` + `rate_limit` 两个 FastAPI 依赖
- `config.py`：加 `api_keys`（逗号分隔）、`rate_limit_per_minute`、`auth_enabled`（开关，默认开但无 key 时降级为不校验，保证开箱即用）
- `api/main.py`：`/api/ask`、`/api/upload` 加鉴权+限流依赖；`/api/health`、`/api/feedback` 保持公开（health 是监控探针、feedback 是用户主动反馈不该拦）
- 前端 `index.html`：加 key 输入框，请求带上 `Authorization` 头
- `tests/test_auth.py`：测 401/429/200 三种情况（用 TestClient + 依赖 override 或真实 key）

---

## 7. 跑起来

### 教学代码（独立可跑）

```bash
cd ops-lessons/04_auth_ratelimit
python code.py
```

预期：用 TestClient 在进程内跑，打印 4 个场景的结果（401×2 / 429 / 200），演示鉴权和限流都生效。

### 落地验证（kb-qa）

```bash
cd portfolio-projects/knowledge-base-qa
# 1) 单测（全 mock，TestClient 打进程内服务）
python -m pytest tests/test_auth.py -q
# 2) 手动验证（先在 .env 配 API_KEYS=kb-test-123）
#    无 key → 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8001/api/ask \
  -H "Content-Type: application/json" -d '{"question":"test"}'   # → 401
#    有 key → 200
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8001/api/ask \
  -H "Authorization: Bearer kb-test-123" -H "Content-Type: application/json" \
  -d '{"question":"试用期多久"}'                                   # → 200
```

---

## 🎯 面试话术

> 「上传和问答接口都加了 API Key 鉴权和按 key 的滑动窗口限流：没 key 或错 key 返 401，超速返 429，都是标准 HTTP 码方便监控。选 API Key 是因为内部系统无用户登录体系；自实现滑动窗口是因为这是面试高频题、且零依赖——理解原理后随时能换 slowapi。这样即便某个 key 泄露，攻击者最多用这一个 key 的配额，不会刷爆全局账单。」

---

## 落地清单

| 文件 | 改动 | 如何验证 |
|---|---|---|
| `src/kb_qa/auth.py` | **新增**：`SlidingWindowLimiter` + `require_api_key` + `rate_limit` 依赖 | `python -c "from kb_qa.auth import require_api_key; print('ok')"` |
| `src/kb_qa/config.py` | 加 `api_keys`/`rate_limit_per_minute`/`auth_enabled` | `.env` 配 `API_KEYS=kb-test-123` |
| `api/main.py` | `/api/ask`、`/api/upload` 挂鉴权+限流依赖；health/feedback 公开 | 无 key 请求 → 401 |
| `static/index.html` | 加 API key 输入框，请求带 Authorization 头 | 前端填 key 后能问答 |
| `tests/test_auth.py` | **新增**：401/429/200 + health 公开（TestClient） | `pytest tests/test_auth.py -q` 全绿 |
| `.env.example` | 补 `API_KEYS`/`RATE_LIMIT_PER_MINUTE`/`AUTH_ENABLED` | — |

下一课 [Lesson 05 — Prompt 注入攻防](../05_prompt_injection/) 进入 LLM 特有的安全威胁。
