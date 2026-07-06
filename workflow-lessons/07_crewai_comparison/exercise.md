# Lesson 07 练习 — CrewAI 对比

> 练习重点在"对比两种范式"和"理解 CrewAI 接国产模型的坑"。

---

## 练习 1：对比 sequential vs hierarchical（关键概念，5 分钟）

运行 `code.py` 的实验 1 和实验 2，回答：

1. sequential 模式下，Agent 是按什么顺序执行的？（提示：agents 列表顺序）
2. hierarchical 模式下，谁决定执行顺序？（提示：manager）
3. 这两种模式分别对应 LangGraph 的什么？（提示：sequential=流水线，hierarchical=supervisor）

> 这道题帮你建立"CrewAI 两种 process ↔ LangGraph 两种拓扑"的映射。

---

## 练习 2：对比代码量（核心认知，5 分钟）

打开 `code.py` 实验 3 的代码量对比，再打开 L01 的 `code.py`。数一下：

| 环节 | CrewAI（行数）| LangGraph L01（行数）|
|---|---|---|
| Agent 定义（2个）| ? | ? |
| 编排（Crew/supervisor）| ? | ? |
| 运行 | ? | ? |
| **总计** | ? | ? |

CrewAI 省了什么？LangGraph 多写的那些代码换来了什么灵活性？

---

## 练习 3：踩"接国产模型"的坑（实践，10 分钟）

这道题让你亲手踩坑，加深记忆。把 `create_llm()` 里的 model 改成不同写法，看会发生什么：

**尝试 1**：去掉 `openai/` 前缀
```python
llm = LLM(model="glm-4-flash", ...)  # 去掉 openai/
```
跑一下，看报什么错？（提示：litellm 不认识这个 model 名）

**尝试 2**：注释掉 `os.environ["CREWAI_TRACING_ENABLED"] = "false"`
跑一下，看是否弹交互提示卡住。

**尝试 3**：去掉 `base_url`
跑一下，看是否请求 OpenAI 官方导致认证失败。

> ⚠️ 踩完坑记得改回来。这些坑在 README 里有记录，亲手踩一次比看十遍记得牢。

---

## 练习 4：用 CrewAI sequential 实现手写 L08 的流水线（10 分钟）

手写 L08 是 planner→executor→reviewer 流水线。用 CrewAI 的 sequential 模式重写：

要求：
1. 3 个 Agent：规划者、执行者、审查者
2. 1 个 Task：给一个复合任务（如"查北京上海天气，比较，给穿衣建议"）
3. `process=Process.sequential`

**观察**：CrewAI 的 sequential 比手写 L08 的 for 循环简单多少？比 LangGraph 的串行图呢？

> 这道题帮你直观感受"声明式"的简洁——手写 L08 要写 run_multi_agent 的循环逻辑，CrewAI 一行 process=sequential 搞定。

---

## 练习 5：CrewAI 做不到的事（认知题，5 分钟）

CrewAI 的 sequential/hierarchical 是预设模式。回答：

1. CrewAI 能做 L03 的子图（把一个 Crew 嵌入另一个）吗？
2. CrewAI 能做 L04 的并行 map-reduce（3 个 worker 同时跑）吗？
3. CrewAI 能做 L05 的黑板模式（共享知识池）吗？

> 答案：都很难（或做不到）。这就是 CrewAI"简洁"的代价——它的 process 只有两种预设模式。你的流程如果超出这两种，就得用 LangGraph。这也是选型的核心依据。

---

## 思考题（不写代码）

1. **为什么 CrewAI 不用画图？** 提示：它预设了几种标准模式（sequential/hierarchical），框架自动编排。LangGraph 让你自由画图，因为流程可能不标准。

2. **CrewAI 的 expected_output 有什么用？** LangGraph 没有这个概念。提示：它给 LLM 一个"成功标准"，有助于输出质量和一致性。

3. **如果让你搭一个客服系统，用 CrewAI 还是 LangGraph？** 提示：客服流程相对标准（分诊→处理→回访），CrewAI 够用且更快。但如果有 VIP 分流、并行查询、HITL 审批——就得 LangGraph。

---

## 完成标志

- [ ] 能说清 CrewAI 和 LangGraph 的范式区别（声明式 vs 命令式）
- [ ] 知道 sequential=流水线，hierarchical=supervisor
- [ ] 踩过 CrewAI 接国产模型的 3 个坑（前缀/tracing/base_url）
- [ ] 理解 CrewAI 的简洁代价（只有两种预设模式，做不了子图/并行/黑板）
- [ ] 能根据场景选型（原型用 CrewAI，精细控制用 LangGraph）

下一课 [L08](../08_autogen_comparison/) 学 AutoGen——对话驱动的群聊编排，补全 Agent L08 的"辩论模式"坑。
