# Lesson 08 练习 — AutoGen 对比

> 练习重点在"理解对话驱动范式"和"补全辩论模式坑"。

---

## 练习 1：对比两种 GroupChat（关键概念，5 分钟）

运行 `code.py` 的实验 1 和实验 2，对比：

1. RoundRobinGroupChat 里，发言顺序是固定的还是动态的？（提示：按 participants 列表顺序轮流）
2. SelectorGroupChat 里，谁决定下一个发言者？（提示：LLM 看对话历史选）
3. 这两种分别对应 LangGraph 的什么？（提示：RoundRobin=流水线，Selector=supervisor）

---

## 练习 2：理解终止条件（核心机制，5 分钟）

AutoGen 的 `termination_condition` 是可组合的。回答：

1. `TextMentionTermination("CONCLUDE")` 是什么意思？（提示：消息里出现 CONCLUDE 就停）
2. `MaxMessageTermination(6)` 是什么意思？（提示：达到 6 条消息就停）
3. 两个条件用 `|` 连接表示什么？（提示：满足任一即停，类似"或"逻辑）

**实验**：把 `MaxMessageTermination(6)` 改成 `MaxMessageTermission(10)`，看辩论会不会更长？

> 💡 这种"可组合的终止条件"是 AutoGen 的优雅设计——比手写 if 判断灵活得多。

---

## 练习 3：踩 model_info 白名单坑（实践，5 分钟）

这道题让你亲手踩坑。把 `create_model_client()` 里的 `model_info={...}` 整段注释掉：

```python
client = OpenAIChatCompletionClient(
    model="glm-4-flash",
    api_key=...,
    base_url=...,
    # model_info={...}  ← 注释掉这行
)
```

跑一下，看报什么错？

**预期**：`ValueError: model_info is required when model name is not a valid OpenAI model`

> ⚠️ 这是 AutoGen 接国产模型的头号拦路虎。踩过一次就记住了。验证后记得改回来。

---

## 练习 4：加一个"裁判"Agent（10 分钟）

在辩论模式里加第三个 Agent：**`judge`（裁判）**。在正方反方辩论几轮后，裁判总结双方观点并裁决。

设计：
- 用 `RoundRobinGroupChat`，participants = [proponent, opponent, judge]
- 裁判的 system_prompt：你看完正反方发言后，客观总结并给出裁决
- 终止条件：裁判发言后结束（提示：可以设 `MaxMessageTermination(7)`，第 7 条是裁判）

**观察**：三个 Agent 轮流发言时，顺序是怎样的？（正→反→裁→正→反→裁...）

---

## 练习 5：对比三框架实现"研究系统"（认知题，10 分钟）

同一个任务（查 RAG + 分析 + 写报告），三个框架各怎么写？填写对比：

| | LangGraph（你会的）| CrewAI（L07）| AutoGen（本课）|
|---|---|---|---|
| 组织方式 | ?（图）| ?（角色+编队）| ?（GroupChat）|
| 几行核心代码 | ? | ? | ? |
| 怎么控制流程 | ? | ? | ? |
| 你会选哪个？为什么？ | | | |

> 没有标准答案，重点是练"看到需求能选对框架"的判断力。

---

## 思考题（不写代码）

1. **AutoGen 的 GroupChat 和 L02 的 swarm 有什么本质区别？** 提示：swarm 是 handoff 交接（接力），GroupChat 是所有人看到所有对话（圆桌）。

2. **为什么 AutoGen 用异步（async/await）而 LangGraph/CrewAI 用同步？** 提示：AutoGen 设计目标是高并发（成百上千 Agent），异步擅长 I/O 密集场景。

3. **三个框架如果只能学一个，你选哪个？为什么？** 提示：看你的目标——生产系统选 LangGraph，快速验证选 CrewAI，对话/辩论选 AutoGen。架构师都要懂。

---

## 完成标志

- [ ] 理解 RoundRobin（轮流）vs Selector（LLM 选）两种 GroupChat
- [ ] 踩过 model_info 白名单坑（非 OpenAI 模型必须传）
- [ ] 知道 AutoGen 是异步架构（async/await）
- [ ] 补全了 Agent L08 exercise 的辩论模式坑 🎯
- [ ] 能说清三框架的范式差异和选型依据

下一课 [L09](../09_capstone/) 毕业项目——综合 L01-L08 全部技术，搭一个简历级多智能体研究系统。
