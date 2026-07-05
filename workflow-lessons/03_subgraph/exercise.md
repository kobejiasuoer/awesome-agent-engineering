# Lesson 03 练习 — 子图 Subgraph

> 练习重点在"理解子图的封装价值"和"State 对齐机制"。

---

## 练习 1：追踪子图的数据流（关键概念，5 分钟）

运行 `code.py` 的实验 1，回答：

1. 用户消息先进哪个节点？（提示：classify）
2. classify 写入了哪个字段？这个字段子图能读到吗？（提示：category，子图看不到）
3. 客服子图内部处理时，用的是哪个字段和父图对接？（提示：messages）
4. 子图处理完，父图怎么拿到结果？（提示：messages 自动回流）

> 这是理解 State 对齐的核心——子图和父图通过"共享字段"对接，各自有各自的"私有字段"。

---

## 练习 2：独立运行子图（验证封装价值，5 分钟）

子图既然是个编译好的图，它应该能**独立运行**（不依赖父图）。验证这一点：

在 `main()` 里加一段代码，直接 `invoke` 子图：

```python
# 直接独立运行子图（不经过父图）
service_subgraph = build_customer_service_subgraph(llm)
result = service_subgraph.invoke({"messages": [{"role": "user", "content": "退款订单999"}]})
print("子图独立运行结果：", result["messages"][-1].content)
```

**观察**：子图能独立跑吗？这说明什么？
（提示：子图是个自包含的系统，可以在不同父图里复用，也能单独测试/调试）

---

## 练习 3：加一个新子图——投诉处理（10 分钟）

参考客服子图的构建方式，加一个**投诉处理子图**（complaint_subgraph），内含两个 Agent：
- `complaint_receiver`（投诉受理员）：记录投诉，转给 `investigator`
- `investigator`（调查员）：调查投诉，给出处理意见

要求：
1. 用 `create_swarm` 构建（和客服子图一样，用 handoff 交接）
2. 在父图的 `classify` 里，把"投诉"类路由到这个新子图
3. 父图现在有两个子图节点：`customer_service` 和 `complaint_handler`

**观察**：加一个子图，父图改动大吗？这就是子图的**可扩展性**——加功能 = 加一个子图节点，不用动其他子图。

---

## 练习 4：对比子图 vs 平铺（认知题，5 分钟）

打开 `agent-lessons/08_multi_agent/code.py`（手写 L08）和本课的 `code.py`，对比：

| | 手写 L08（平铺）| 本课（子图）|
|---|---|---|
| Agent 组织方式 | 三个独立函数平铺 | ? |
| 能否独立运行一组 Agent | ? | ? |
| 能否复用到其他项目 | ? | ? |
| 加新功能的影响范围 | ?（改哪里？）| ?（改哪里？）|

把答案填进去，亲眼看子图在"封装/复用/可维护性"上的优势。

---

## 练习 5：把 framework-L09 嵌进来（进阶，15 分钟）

`framework-lessons/09_capstone/code.py` 里有一个 LangGraph 研究助手图（research → tools → report 三节点）。

挑战：把那个研究助手图**当作子图**，嵌入本课的父图。设计：
- 父图的 `classify`：如果用户要"研究某主题"，路由到研究助手子图
- 研究助手子图：处理研究请求（它有自己的 State：messages + topic + report）
- 需要处理 State 对齐：研究助手的 `topic`/`report` 字段怎么和父图对接？

> 提示：可能需要扩展父图的 State，加上 `topic` 和 `report` 字段。这道题考验你对 State 对齐的理解——当子图字段比父图多时怎么办。

---

## 思考题（不写代码）

1. **子图和微服务有什么相似之处？** 提示：封装、独立部署、通过接口（State）通信、可复用。

2. **什么时候不该用子图？** 提示：逻辑简单（1-2 步）、不会被复用、不需要独立测试时——子图会变成过度设计。

3. **子图的 State 和父图的 State 不一致会怎样？** 提示：共享字段必须类型+reducer一致；不共享的字段互不影响。

---

## 完成标志

- [ ] 理解子图 = 把编译好的图当节点（`add_node(name, compiled_graph)`）
- [ ] 能解释 State 对齐（父图 ⊇ 子图，子图只读写共享字段）
- [ ] 验证了子图能独立运行（封装 = 自包含）
- [ ] 理解条件路由 + 子图 = 按需启动子系统（省成本）
- [ ] 知道这是兑现 framework L07 预告的「子图」

下一课 [L04](../04_parallel_mapreduce/) 学并行 Map-Reduce——让多个子任务同时跑，兑现 Agent L08 的「并行」遗憾。
