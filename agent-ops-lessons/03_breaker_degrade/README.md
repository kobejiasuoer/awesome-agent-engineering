# Lesson 03 — 超时、熔断与诚实降级

> 本课目标：**把「工具挂了」从静默污染变成显式降级**——现状 `web_search` 超时返回的「搜索超时」字符串混进材料被 LLM 当事实写进报告，这是不诚实的降级。本课引入结构化降级协议（ok/degraded/failed）+ 手写熔断器（治持续故障）+ 降级链（能力递减不中断），让故障不扩散。
>
> 学完你能回答面试官那句：**「你的 Agent 工具挂了会怎样？」**——答案是诚实降级：结构化标注 degraded 材料、报告里声明哪些子题检索失败，绝不让「搜索超时」字符串混进材料被当成事实；持续故障用手写熔断器快速失败，抖动才重试。

---

## 0. 起点：L00 基线里故障①②的裸奔结局

L00 的 `baseline_chaos.json` 记录故障①（慢工具）和故障②（坏工具）结局都是 `polluted`——**失败/垃圾字符串混进材料当事实**。这是本课的灵魂案例。

### 现状解剖：不诚实的降级

```python
# tools.py 现状
async def web_search(query, max_results=None):
    try:
        result = await asyncio.wait_for(...)
        return result
    except asyncio.TimeoutError:
        return f"搜索 '{query}' 超时（{settings.search_timeout}s）。可换关键词或稍后重试。"
    except Exception as e:
        return f"搜索 '{query}' 失败（{type(e).__name__}: {e}）。可换关键词重试。"
```

> 🎯 **核心认知（本课灵魂）**：超时返回的是一段**字符串**。这个字符串混进 `findings` 列表，被 summarize 当成「子题一的研究发现」，被 writer 写进报告。**下游毫无感知**——它不知道这是失败提示还是真实内容。报告里会出现「搜索 '子题一' 超时（15s）」被当成事实。这就是**不诚实的降级**：表面没崩（返回了东西），实质污染了输出。

```
现状故障链：
  web_search 超时 → 返回 "搜索超时" 字符串
       ↓
  researcher 把它当 finding 加入 findings
       ↓
  summarize 把 "搜索超时" 总结进摘要
       ↓
  writer 把 "搜索超时" 写进报告当事实 ☠️
```

---

## 1. 诚实降级协议：结构化结果

### 1.1 从字符串到结构化

```python
# tools.py L03 新增
async def web_search_structured(query, max_results=None) -> dict:
    """返回结构化结果：{"status": "ok"|"degraded"|"failed", "content": str, "reason": str}"""
    ...
    except asyncio.TimeoutError:
        return {"status": "degraded", "content": "", "reason": f"搜索超时（{timeout}s）"}
```

关键区别：degraded/failed 的 `content` 是**空字符串**，不是「搜索超时」提示。下游看 `status` 字段决定怎么用，而不是 parse 字符串猜「这是失败还是内容」。

### 1.2 researcher 上报失败，不产出被污染的 finding

```python
# nodes.py researcher（enable_circuit_breaker 时）
sr = await web_search_structured(subtopic)
if sr["status"] == "ok":
    web_raw = sr["content"]
else:
    web_raw = ""
    failed_subtopic = f"{subtopic}（{sr['reason']}）"  # 上报失败
    ...
if failed_subtopic is not None:
    return {"findings": [], "failed_subtopics": [failed_subtopic]}  # 不产出污染 finding
```

### 1.3 writer 在报告里如实声明

```python
# nodes.py writer
failed_subs = state.get("failed_subtopics", [])
if failed_subs:
    report += f"\n\n⚠️ **检索降级声明**：以下 {len(failed_subs)} 个子题检索失败，本报告未涵盖：\n{decl}"
```

> 💡 这就是「诚实降级」：报告里明写「3 个子题里有 1 个检索失败」，而不是把「搜索超时」偷偷混进正文。用户看到的是「这部分没查到」，不是「这部分查到了一个叫『搜索超时』的发现」。

---

## 2. 手写熔断器：治持续故障

### 2.1 为什么不直接重试

```
雪崩放大器：
  持续故障（搜索服务挂了）+ 无限重试
    = 每个请求都等满 超时(15s) × 重试次数(3) = 45s
    = 并行 3 个子题 × 45s = 135s 卡死
    = 持续故障期间所有请求堆积 → 雪崩

  熔断器：连续 N 次失败 → 打开 → 快速失败（不等超时）
    = 第 4 次起 0ms 返回 degraded
    = 阻断雪崩放大
```

### 2.2 三态状态机

```
         连续 fail_threshold 次失败
   ┌──────────────────────────────┐
   │                              ▼
 CLOSED ◄────试探成功──── HALF_OPEN ────冷却结束──── OPEN
 (放行)                      ▲                            │
   │                        │                    试探失败 │
   └──成功清零失败计数────────┘                            │
                              └──────────────────────────┘
                                 （重新计时，继续熔断）
```

- **CLOSED**：正常放行，记录失败计数；成功清零（治抖动：偶发失败不累积）。
- **OPEN**：快速失败（不调函数，直接返回 degraded），不等超时。
- **HALF_OPEN**：冷却后放一个试探请求；成功 → CLOSED，失败 → 重新 OPEN。

### 2.3 按工具实例隔离

每个工具（web_search / browser）一个独立熔断器（`get_breaker("web_search")`）。一个挂了不影响另一个——搜索挂了不意味着浏览器也挂了，不该连坐。

---

## 3. 降级链：能力递减不中断

```
browser（慢深贵，详情页取证）
   │ 失败/未启用
   ▼
web_search（快浅便宜，搜索摘要）
   │ 失败/超时
   ▼
跳过该子题 + 报告声明「检索失败」（不编造内容）
```

每一层失败都降级到更弱但更可靠的能力，最终兜底是「诚实声明失败」而非「编造内容」。现状 researcher 已经有这个雏形（search 没素材时用模型知识兜底并标注无来源），L03 把「失败」也纳入这个链——失败也是降级的一种，要诚实标注。

---

## 4. 方案对比：故障形态 × 策略

| 故障形态 | 策略 | 理由 |
|---|---|---|
| ① **偶发抖动**（网络闪断） | 重试 + 退避 | 重试几次就好，不该熔断（误杀正常请求） |
| ② **限流**（429） | 重试 + 退避 | 退避等限流窗口过去，重试大概率成功 |
| ③ **持续故障**（服务挂了） | **熔断** | 重试 = 雪崩放大器；要快速失败阻断堆积 |
| ④ **慢工具**（超时） | 超时 + 降级 | 不等它，标注 degraded 声明 |

> 🎯 **核心认知**：重试和熔断治的是**不同的病**。重试治抖动（偶发、自愈），熔断治持续故障（连续、不自愈）。用反了——重试治持续故障 = 雪崩，熔断治抖动 = 误杀。判断依据是「故障是不是自愈的」：会自己好的用重试，不会的用熔断。

| 方案 | 做法 | 取舍 |
|---|---|---|
| ① **无限重试** | 失败就一直重试 | ✅ 简单；🚫 雪崩放大器（持续故障下每个请求等满超时×重试） |
| ② **fail-fast** | 失败立即返回，不重试不熔断 | ✅ 快；🚫 脆（抖动也被当永久失败） |
| ③ **重试 + 退避** | 失败重试 N 次，每次间隔递增 | ✅ 治抖动；🚫 治不了持续故障（还是雪崩） |
| ④ **熔断**（本课主路线） | 连续 N 次失败 → 快速失败 → 冷却 → 半开试探 | ✅ 治持续故障、阻断雪崩；🚫 治不了抖动（要和重试叠加） |

**选 ④ + ③ 叠加**：熔断治持续故障，重试治抖动，两者叠加才是完整的故障处理。`web_search_structured` 里先重试（抖动），重试到熔断阈值就熔断（持续故障）。

> 💡 **紧还是松？**（自主-控制主线）：`fail_threshold` 设多少？太小（如 1）一点抖动就熔断（误杀正常请求）；太大（如 10）雪崩已经发生才熔断。判断依据是「故障的持续时间」——3 次失败通常意味着不是单次抖动。`cooldown` 设多少？太短频繁试探（浪费），太长恢复慢。30s 是常见的「故障可能已恢复」窗口。

---

## 5. 跑起来

### `code.py` 演示

```bash
cd portfolio-projects/research-assistant
python ../../agent-ops-lessons/03_breaker_degrade/code.py
```

演示三件事：
1. **熔断器状态机**：连续 3 次失败 → open → 半开试探成功 → closed。
2. **诚实降级 vs 字符串降级**：现状的「搜索超时」字符串混进 findings（污染），L03 的结构化降级 content 为空 + 上报 failed_subtopics（干净）。
3. **故障形态 × 策略判断表**：什么故障用什么策略。

---

## 6. 落地清单

| 文件 | 改动 | 如何验证 |
|---|---|---|
| `src/research_assistant/breaker.py` | **新增**：`CircuitBreaker` 三态状态机 + `get_breaker`（按实例隔离）+ `call_with_breaker`（结构化降级） | `pytest tests/test_breaker.py -q` |
| `src/research_assistant/tools.py` | **新增**：`web_search_structured`（结构化返回 + 熔断 + 重试）；`web_search` 保持不变（现状兼容） | 见下 |
| `src/research_assistant/state.py` | **新增**：`failed_subtopics`（reducer 累加，writer 声明用） | import 不报错 |
| `src/research_assistant/config.py` | **新增**：`enable_circuit_breaker`/`breaker_fail_threshold`/`breaker_cooldown`/`search_retry`（默认关/0） | 改 `.env` |
| `src/research_assistant/nodes.py` | researcher：`enable_circuit_breaker` 时走 `web_search_structured`，失败上报 `failed_subtopics`；writer：声明检索失败 | 见下 |
| `src/research_assistant/service.py` + `cli.py` | `_initial_state` 加 `failed_subtopics` | 跑 cli 不报错 |
| `tests/test_breaker.py` | **新增**：15 个测试（状态机/隔离/结构化降级/超时/熔断快速失败） | `pytest tests/test_breaker.py -q` |
| `tests/conftest.py` | autouse fixture 加 `reset_breakers()`（防跨测试泄漏） | 全套绿 |

### 验收

```bash
cd portfolio-projects/research-assistant

# 1. 全部测试绿（156 + 15 = 171）
python -m pytest -q
# 预期：171 passed

# 2. 开关关时行为 = 现状（web_search 字符串返回不变）
python -m pytest tests/test_tools.py tests/test_nodes.py -q
# 预期：全绿（web_search_structured 不影响 web_search）

# 3. 开熔断后超时返回 degraded（非字符串）
python -c "
import asyncio
from research_assistant import config
config.settings.__dict__['enable_circuit_breaker'] = False
config.settings.__dict__['search_timeout'] = 1
from research_assistant.tools import web_search_structured
from research_assistant import tools
import time
tools._ddgs_search = lambda q,n: (time.sleep(2), '不该到这')[1]
r = asyncio.run(web_search_structured('q'))
print(r['status'], r['content'] == '')
"
# 预期：degraded True（超时返回 degraded + content 空，不污染）
```

---

## 7. 本课在两条主线上的位置

- **爆炸半径主线**：把「故障扩散」的爆炸半径从**无界**（超时字符串污染整条链、持续故障雪崩）压到**有界**（结构化降级不污染 + 熔断快速失败阻断雪崩 + 降级链能力递减不中断）。
- **自主-控制主线**：熔断的「紧松」判断依据是「故障是不是自愈的」——会自愈的用重试（松），不自愈的用熔断（紧）。`fail_threshold` 太紧误杀抖动，太松雪崩已发生。

---

## 🎯 面试话术

> 「我的 Agent 工具故障处理原则是**诚实降级**：工具返回结构化结果 `{ok/degraded/failed, 原因, 内容}`，degraded 的 content 是空的——绝不让『搜索超时』字符串混进材料被 LLM 当成事实写进报告。报告里会如实声明『3 个子题有 1 个检索失败，本报告未涵盖』。
>
> 持续故障用手写熔断器——三态状态机：连续 3 次失败打开、快速失败不再等超时、冷却后半开试探。为什么不直接重试？因为重试遇到持续故障是雪崩放大器：每个请求等满超时 × 重试次数。熔断器就是阻断这个放大。
>
> 重试和熔断治的是不同的病：重试治抖动（偶发、自愈），熔断治持续故障（连续、不自愈）。我的 `web_search_structured` 里两者叠加——先重试挡抖动，到熔断阈值就快速失败挡持续故障。判断依据是『故障会不会自己好』。」
