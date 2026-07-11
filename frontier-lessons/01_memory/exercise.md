# L01 练习

## 练习 1：对比「全存 vs 检索式」的记忆质量（设计实验类）

本课的 MemoryStore 用向量检索只调回相关记忆。对比方案是「把所有历史记忆全塞进 prompt」。设计实验验证检索式的优势：

1. **假设**：全存方案在记忆条数多时，检索质量下降（噪音淹没），且 token 成本线性增长。
2. **实验**：
   - 往 MemoryStore 写入 20 条记忆（5 个主题各 4 条，其中只有 2 条与查询相关）。
   - 方案 A（全存）：把 20 条全塞 prompt，让假 LLM 判断"哪些相关"。
   - 方案 B（检索式，本课）：recall(query, k=3)，只塞命中的 3 条。
   - 对比：① 相关记忆的召回率 ② 注入 prompt 的 token 数。
3. **预期**：召回率接近（假 embedding 可能都不完美），但 token 数 B 远小于 A。

**验收**：输出对比表，诚实标注假 embedding 下召回率可能不高（这是降级模式的已知局限）。

---

## 练习 2：实现「跨 thread 共享记忆」

本课的 MemoryStore 是单例，天然跨 thread——但 researcher 只在 `enable_memory=true` 时调它。验证跨会话共享：

1. 模拟两个不同 thread_id 的研究（主题不同），都开启记忆。
2. 第一个 thread 研究"MCP"，第二个 thread 研究"Agent 记忆"。
3. 然后开第三个 thread 研究"MCP 的协议设计"——它应该 recall 到第一个 thread 写入的 MCP 记忆。

**验收**：第三个 thread 的 recall 命中第一条 thread 的记忆（证明跨 thread 共享成立，这正是 Checkpointer 做不到的）。

<details>
<summary>提示</summary>

`get_memory_store()` 是模块级单例，不管 thread_id 是什么都返回同一个 `MemoryStore` 实例。所以只要 `remember` 和 `recall` 走同一个单例，跨 thread 就天然成立。验证时用两个不同的 `thread_id` 跑 `invoke`，然后手动调 `get_memory_store().recall()` 看命中。
</details>

---

## 练习 3：给 MemoryStore 加「记忆来源溯源」

现在的 EpisodicMemory 有 `source` 字段但没在 recall 时展示。改进：

1. recall 返回的记忆带上来源（哪次运行/哪个 thread 写入的）。
2. format_recall_for_prompt 里显示"（来自 run #1, 2 天前）"。
3. 思考：为什么来源溯源对研究助手重要？（提示：可信度——"这是我上次查的"vs"不知道哪来的"）

**验收**：prompt 里注入的记忆带来源和时间信息，面试能讲清"记忆溯源"的价值。
