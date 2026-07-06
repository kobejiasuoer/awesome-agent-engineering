# Lesson 08 — AutoGen 对比：对话驱动的群聊编排

> **本课定位**：横向对比段的最后一课。AutoGen（微软出品）用「对话」作为一等公民——多 Agent 在一个 GroupChat 里像开会一样发言。本课还**补全 Agent L08 exercise 留的「辩论模式」坑**（手写课只给了骨架没实现）。
>
> **补全的手写课**：`agent-lessons/08_multi_agent` exercise 练习 3（辩论模式骨架）。
>
> **对比的前序课**：L01 supervisor、L02 swarm、L07 CrewAI。

---

## 一、AutoGen 的独特范式：对话驱动

LangGraph 用「图」组织 Agent，CrewAI 用「角色+任务」，AutoGen 用「**对话**」：

```
LangGraph：你画图（节点+边），Agent 沿边流转
CrewAI：你声明角色和任务，框架自动编排
AutoGen：你把 Agent 放进一个 GroupChat，它们像开会一样发言
```

### AutoGen 的核心概念

| 概念 | 对应其他框架 | 说明 |
|---|---|---|
| `AssistantAgent` | LangGraph 的 `create_agent` / CrewAI 的 `Agent` | 一个 AI 参与者 |
| `Team`（GroupChat）| LangGraph 的图 / CrewAI 的 `Crew` | 一组 Agent 的协作容器 |
| `termination_condition` | LangGraph 的 `END` / CrewAI 的 task 完成 | 什么时候停止对话 |
| `run(task=...)` | `graph.invoke()` / `crew.kickoff()` | 启动协作 |

### 两种 GroupChat

| 类型 | 对应 LangGraph | 行为 |
|---|---|---|
| `RoundRobinGroupChat` | 流水线（L04 串行 / 手写 L08）| **按顺序轮流**发言：A→B→A→B... |
| `SelectorGroupChat` | supervisor（L01）| **LLM 选**下一个发言者（看对话历史决定）|

---

## 二、补全 Agent L08 的辩论模式坑

### Agent L08 exercise 练习 3 留了什么？

打开 `agent-lessons/08_multi_agent/exercise.md`，练习 3 要求实现「辩论模式」——两个 Agent（正方/反方）就一个话题辩论。但手写课**只给了 prompt 骨架，没有成品**：

> "练习 3：实现辩论模式...提示：正方和反方各有 system prompt..."

手写实现辩论模式很麻烦：要管理轮次（正方→反方→正方...）、终止条件（辩了几轮？谁认输了？）、消息传递（怎么把对方的发言给下一个 Agent）。

### AutoGen 一行解决

```python
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination

team = RoundRobinGroupChat(
    participants=[proponent, opponent],  # 正方、反方
    termination_condition=(
        TextMentionTermination("CONCLUDE")   # 有人说 CONCLUDE 就停
        | MaxMessageTermination(6)           # 或达到 6 条消息（防无限辩论）
    ),
)
result = await team.run(task="辩题：AI 会取代程序员吗？")
```

`RoundRobinGroupChat` 自动管理轮次（正→反→正→反）、消息传递（每个 Agent 自动看到之前的对话）、终止条件。**手写要几十行的循环逻辑，AutoGen 一个类搞定**。

> 💡 `termination_condition` 用 `|` 组合多个条件——"满足任一即停"。这是 AutoGen 的优雅设计：终止条件是可组合的对象，不是硬编码的 if 判断。

---

## 三、教学金矿：AutoGen 的两个坑

### 坑 1：model_info 白名单（最大的坑）

AutoGen 的 `OpenAIChatCompletionClient` 内置了 **OpenAI 模型白名单**。非 OpenAI 模型（如 glm-4-flash）不在白名单里，**必须手传 `model_info`**，否则报错：

```python
# ❌ 报错：ValueError: model_info is required when model name is not a valid OpenAI model
client = OpenAIChatCompletionClient(model="glm-4-flash", api_key=..., base_url=...)

# ✅ 正确：手传 model_info
client = OpenAIChatCompletionClient(
    model="glm-4-flash",
    api_key=...,
    base_url="https://open.bigmodel.cn/api/paas/v4",
    model_info={                          # ⭐ 非 OpenAI 模型必须传
        "vision": False,
        "function_calling": True,         # 支不支持函数调用
        "json_output": True,              # 支不支持 JSON 输出
        "family": "unknown",
        "structured_output": True,
        "multiple_system_messages": True,
    },
)
```

**为什么有这个坑？** AutoGen 需要知道模型的能力（支不支持 function calling、JSON 输出等）来决定怎么调用它。OpenAI 模型它自动查表，非 OpenAI 模型它查不到——你得手动告诉它。

**三个框架接国产模型的对比**：

| 框架 | 接 GLM 的方式 | 难度 |
|---|---|---|
| LangGraph | `ChatZhipuAI(model=...)` 一行 | ★ 最简单 |
| CrewAI | `LLM(model='openai/glm-4')` + litellm + 关 tracing | ★★★ 中等 |
| AutoGen | `OpenAIChatCompletionClient` + **手传 model_info** | ★★★★ 最麻烦 |

### 坑 2：异步架构（async/await）

AutoGen 0.4+ 是**完全异步**的——所有调用都要 `await`：

```python
# AutoGen 是异步的
async def main():
    result = await team.run(task="...")    # ⭐ 要 await
    await model_client.close()              # ⭐ 要手动关闭 client

asyncio.run(main())  # 用 asyncio.run 启动
```

对比 LangGraph/CrewAI 的同步风格：

```python
# LangGraph/CrewAI 是同步的
result = graph.invoke(...)      # 直接调用
result = crew.kickoff()         # 直接调用
```

**为什么 AutoGen 用异步？** 它设计目标是高并发（同时跑成百上千个 Agent），异步能高效处理 I/O 等待。但对于简单场景，异步增加了心智负担（要理解 `async/await`、`asyncio.run`）。

---

## 四、AutoGen vs LangGraph swarm（L02）

AutoGen 的 GroupChat 和 L02 的 swarm 都涉及"多 Agent 协作"，但机制不同：

| | LangGraph swarm（L02）| AutoGen GroupChat |
|---|---|---|
| 怎么传递控制权 | handoff 工具（显式调用 transfer_to_xxx）| 轮转/LLM 选择（隐式）|
| Agent 看到什么 | handoff 时传递的上下文 | **整个对话历史**（群聊里所有人都看得到）|
| 谁控制流程 | Agent 自己决定（调 handoff 工具）| GroupChat 框架（RoundRobin 轮流 / Selector LLM 选）|
| 适合 | 固定流程（客服：分诊→退款→售后）| 自由对话（辩论、头脑风暴、讨论）|

> 💡 **直觉**：LangGraph swarm 像"接力赛"（交接棒），AutoGen GroupChat 像"圆桌会议"（大家围坐发言）。

---

## 五、三框架终极对比

学完 L07（CrewAI）+ L08（AutoGen），加上 L01-L06（LangGraph），你现在有三个框架的完整认知：

| | LangGraph | CrewAI | AutoGen |
|---|---|---|---|
| **范式** | 命令式（图）| 声明式（角色）| 对话式（群聊）|
| **灵活性** | ★★★★★ | ★★☆ | ★★★ |
| **代码量** | 多 | 少 | 中 |
| **接国产模型** | 最简单 | litellm 桥 | model_info 坑 |
| **同步/异步** | 同步 | 同步 | **异步** |
| **特色** | 子图/并行/HITL/流式 | expected_output/人设 | 辩论/群聊/终止条件组合 |
| **最适合** | 复杂生产系统 | 快速原型 | 多方对话/辩论 |

### 选型决策树

```
你的需求：
  ├── 需要精细控制（子图/并行/HITL/流式）？
  │     → LangGraph（唯一能做的）
  │
  ├── 需要快速搭原型（角色明确，2-3 个 Agent）？
  │     → CrewAI（声明式，最快）
  │
  └── 需要多 Agent 自由对话/辩论/讨论？
        → AutoGen（GroupChat 天生为此设计）
```

> 💡 三个框架**不冲突**，可以组合用：CrewAI 快速验证想法 → LangGraph 重写生产版 → AutoGen 做对话类功能。架构师的价值是知道每个工具的最佳用途。

---

## 六、本课代码

`code.py` 三个实验（注意是异步的 `async/await`）：

1. **实验 1（辩论模式）**：`RoundRobinGroupChat` 让正方/反方轮流辩论——补全 Agent L08 exercise 的坑
2. **实验 2（Selector 群聊）**：`SelectorGroupChat` 让 LLM 选发言者——对应 L01 supervisor
3. **实验 3（三框架对比）**：LangGraph/CrewAI/AutoGen 终极对比表 + 选型决策树

```bash
python workflow-lessons/08_autogen_comparison/code.py
```

---

## 七、小结 & 下节预告

**✅ 本课要点**：
- AutoGen 用「对话」组织：多 Agent 在 GroupChat 里发言
- `RoundRobinGroupChat`：轮流发言（辩论/流水线）
- `SelectorGroupChat`：LLM 选发言者（对应 supervisor）
- `termination_condition` 用 `|` 组合（TextMention + MaxMessage）
- model_info 白名单坑：非 OpenAI 模型必须手传
- 异步架构：`async/await`（和 LangGraph/CrewAI 同步不同）
- **补全了 Agent L08 exercise 的辩论模式坑** 🎯
- 三框架各有所长：LangGraph(精细)/CrewAI(简洁)/AutoGen(对话)

**🔜 下节预告（L09 — 毕业项目）**：
横向对比段完成！L09 是整个多智能体课程的**毕业项目**——综合 L01-L08 的拓扑/通信/调度，搭一个多智能体研究系统（supervisor + 并行 + 共享态 + 多模型），可写进简历的完整作品。

> ⚠️ **清醒认知**：AutoGen 的异步架构在简单场景下是负担（要写 async/await），但在高并发场景下是优势。而且它的 GroupChat 模式（所有人看到所有对话）在 Agent 多时会很费 token——每个人发言都包含完整历史。生产环境要注意控制对话长度和 Agent 数量。
