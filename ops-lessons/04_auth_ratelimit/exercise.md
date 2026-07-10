# Lesson 04 练习

> 改 `code.py` 里的代码，运行 `python code.py` 观察变化。本课依赖 fastapi（kb-qa 已装）。

---

## 练习 1：体验限流窗口的「滑动」行为

现在限流是 3 次/60 秒。改成更小的窗口验证「滑动」语义：

```python
limiter = SlidingWindowLimiter(max_requests=2, window_seconds=2)  # 2 秒 2 次
```

在 main 里：连打 3 次 → 第 3 次应 429；**等 2 秒**后再打一次 → 应该 200（窗口滑过去了）。

```python
import time
# ... 连打 2 次 200，第 3 次 429
time.sleep(2.1)  # 等窗口过期
r = client.post("/api/ask", json={"q": "t"}, headers=headers)
print(r.status_code)  # 应该又变 200
```

**思考**：如果是「固定窗口」，等 2 秒后不一定立刻恢复（要等到窗口整点重置）。滑动窗口是「随时过期随时恢复」，这就是它更平滑的原因——**不存在边界突发**。

---

## 练习 2：实现令牌桶限流器（对比滑动窗口）

滑动窗口的兄弟算法是「令牌桶」。实现一个对比：

```python
class TokenBucket:
    def __init__(self, capacity, refill_per_sec):
        self.capacity = capacity      # 桶容量（允许突发）
        self.refill = refill_per_sec  # 匀速回填
        self.tokens = capacity
        self.last = time.monotonic()

    def allow(self, key):
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.refill)
        self.last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False
```

**思考**：令牌桶和滑动窗口最大的区别是**允许突发**——桶满时一次性可以打 capacity 次（滑动窗口严格按上限）。哪种更适合 LLM 接口？通常是滑动窗口（严格控成本），但令牌桶适合「允许偶尔突发、平均受限」的场景。**选型看业务**。

---

## 练习 3：换成按 IP 限流（不依赖鉴权）

把限流维度从「按 key」改成「按 IP」：

```python
def rate_limit_by_ip(request: Request):
    client_ip = request.client.host  # 拿调用方 IP
    if not limiter.allow(client_ip):
        raise HTTPException(429, "请求过快")
```

**思考**：按 IP 限流的坑是什么？——**NAT/代理后大量用户共享一个 IP**。公司内网所有人都表现为同一个出口 IP，按 IP 限会误伤正常用户。所以 kb-qa 选「按 key」：每个调用方独立配额，精确且不误伤。但没鉴权的接口（health）想限流就只能按 IP。

---

## 练习 4：用 slowapi 替换自实现（生产对照）

理解了原理，看生产库 `slowapi` 怎么做（一行装饰器）：

```bash
pip install slowapi -i https://pypi.tuna.tsinghua.edu.cn/simple
```

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)  # slowapi 默认按 IP

@app.post("/api/ask")
@limiter.limit("3/minute")
async def ask(request: Request):  # slowapi 要求参数有 request
    ...
```

**思考**：slowapi 内部也是滑动窗口/令牌桶，只是封装好了。本课自实现是为了让你看清算法——**懂原理后用库，库就成了工具而非黑盒**。生产用 slowapi 的好处是它支持 Redis 后端（多实例共享限流计数），单机版限流器在多副本部署时计数是各自独立的（每个副本一份配额）。

---

## ✅ 完成本课后，你应该能回答

1. 为什么 LLM 接口裸奔比普通 CRUD 接口更危险？（每次调用都花钱）
2. API Key vs JWT，kb-qa 为什么选前者？多 key 管理有什么好处？
3. 固定窗口限流有什么缺陷？滑动窗口怎么解决的？
4. 为什么按 key 限流比按 IP 更适合 kb-qa？
5. 为什么用 FastAPI 依赖注入而不是装饰器做鉴权？（提示：复用/文档/测试 override）
6. 401 和 429 分别是什么意思？为什么必须用标准 HTTP 码而非私有 code？
7. （落地）kb-qa 的哪些接口加了鉴权限流，哪些保持公开？为什么 health 要公开？
