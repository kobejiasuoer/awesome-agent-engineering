# Lesson 04 · 练习

## 练习 1（设计实验）：预算多大才保得住事实

长途任务的 20 条关键事实里，8 条埋在开头 450 字内、12 条在 60% 深度后。扫 `tool_result_max_tokens` 找「事实存活 vs 窗口占用」的取舍点：

```python
from eval_agent.long_haul import DOC_IDS, KEY_FACTS, LongHaulSource
from research_assistant.tool_shaping import shape_result
from research_assistant.context_ledger import FakeTokenizer

tk = FakeTokenizer()
src = LongHaulSource()
for budget in (60, 120, 300, 600, 1200, 2400):
    shaped = {d: shape_result(src.doc(d).content, max_tokens=budget) for d in DOC_IDS}
    alive = sum(1 for f in KEY_FACTS if f.probe in shaped[f.doc_id])
    total = sum(tk.count(t) for t in shaped.values())
    print(budget, "→ 事实存活:", alive, "/20，30源合计:", f"{total:,} tok")
```

1. 画出预算-存活曲线（预期形状：60/120 档只剩 8 条 early；600 档 late 大批回归；最后两条「钉子户」到 2400 才活）。用埋点契约解释三段：early 在前 450 字（≈113 tok，任何档都活）；普通源的 late 在 62% 深度（870–1740 字，600 档=2400 字够到）；F05/F19 埋在超长文档 60% 深度（≈7000 字）——**均匀预算对付不了长尾文档**，这正是分页/检索式按需深读的用武之地。
2. 结合 8k 窗口：预算 600 时 30 源合计约 15k token（只省 1/3），仍要 2 个窗口——由此说明整形解决的是「单条肥」，解决不了「条数多」；后者靠什么（L02/L05/L06）？
3. 「截断保开头」和 L00 硬截断的区别只剩标记——那这一课的价值到底在哪？（提示：标记+分页把「丢了」变成「暂时没读」；练习 2 的检索式返回把「保开头」变成「保命中」。）

## 练习 2（设计实验）：第四板斧——检索式返回

三板斧都按**位置**保留。实现第四板斧 `grep_result(text, query, context_chars=100)`：按**命中**保留——返回 query 关键词所在的片段（前后各 context_chars 字），每段带 `[第 X–Y 字]` 位置标记，末尾带总计标记（命中 N 处/原文 M 字）。

1. 用它处理 S17（3,400 tok），query=「向量时钟」——对比截断板斧：谁保住了 F19（埋在 60% 深度）？窗口各花多少？
2. 检索式返回的静默失误模式是什么（提示：query 没写对=命中 0 处）？你的实现该返回空串还是显式的「0 命中标记」？用「省略必须显式」的铁律论证。
3. 什么时候检索式优于分页式？给两个真实场景（提示：找特定数字 vs 通读理解）。

## 练习 3（改写）：把烂错误改成可行动错误

用 `shape_error` 的三段式（现象/细节/建议）改写以下三个真实风格的烂返回值，并说明每个原版会让 agent 做出什么错误决策：

1. `Exception: [Errno 11001] getaddrinfo failed`（DNS 解析失败，站点可能拼错或墙了）
2. `{"error": {"code": 429, "message": "Too Many Requests"}}`（限流，Retry-After: 30）
3. 长达 2000 字的 HTML 错误页（Cloudflare 5 秒盾，内容全是样式代码）

第 3 个最阴险：它不是异常而是「成功返回」的垃圾——你的 researcher 会把它当检索材料。给 `shape_result` 之前加一道「垃圾检测」该查什么特征？

## 练习 4（思考）：给 MCP 工具定返回值规范

假设你在给团队的 MCP server 定《工具返回值规范》。基于本课写出五条硬性条款（每条一句话+一个反例），至少覆盖：省略显式性、分页契约、错误三段式、结论在前、体积上限。然后回答：这份规范和「给人用的 REST API 设计指南」重合度有多高？哪一条是 agent 特有的（人类用户不需要）？
