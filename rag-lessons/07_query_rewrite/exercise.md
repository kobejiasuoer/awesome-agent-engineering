# Lesson 07 练习

> 改 `code.py` 里的代码，运行 `python lessons/07_query_rewrite/code.py` 观察变化。
> 本课会调用 embedding + chat API（成本很低，特别是用 glm-4-flash）。

---

## 练习 1：换一个"指代不明"的问题
把 `RAW_QUERY` 改成带指代词的问题：

```python
RAW_QUERY = "那个怎么弄？上次说的那个表。"
```

**观察**：直接检索几乎肯定召不准（"那个"指什么向量检索完全懵）。HyDE 和多查询展开能否改善？

**思考**：对于这种极端模糊的问题，query 改写能救到什么程度？什么情况下必须靠"多轮对话历史"？（提示：HyDE 和多查询能"猜测"，但如果完全没有上下文，它们也只能瞎猜——这引出了对话型 RAG 需要带历史消息的需求）

---

## 练习 2：对比 HyDE 的"假设答案质量"对结果的影响
在 `section_hyde` 里，把 `hyde_prompt` 改成两种极端：

**版本A（要求精确）**：
```python
hyde_prompt = f"请准确回答：{RAW_QUERY}"
```

**版本B（原版，要求像文档）**：
```python
hyde_prompt = f"写一段50字左右的公司制度陈述句，回答这个问题：{RAW_QUERY}"
```

对比两者的检索效果。

**思考**：HyDE 的精髓不是"答案准不准"，而是"格式像不像文档"。为什么格式像文档反而检索更准？（回顾 README：embedding 模型在文档语料上训练，更熟悉陈述性文本）

---

## 练习 3：增加子问题数量
把多查询展开从 3 个子问题改成 **5 个**：

```python
multi_prompt = (
    f"请把下面问题拆解成 5 个更具体的子问题...\n\n用户问题：{RAW_QUERY}"
)
# 同时修改 [:3] 为 [:5]
sub_queries = [q.strip() for q in sub_queries_text.split("\n") if q.strip()][:5]
```

**观察**：子问题更多，召回覆盖率有没有提升？延迟和成本呢？

**思考**：多查询展开是"子问题越多越好"吗？权衡点在哪？（提示：覆盖 vs 成本/延迟/噪声）

---

## 练习 4：组合拳——HyDE + 多查询 + Rerank
把第 6 课学的 Rerank 加进来：先用多查询展开 + RRF 召回 top-5，再 Rerank 到 top-3。

在 `section_multi_query` 末尾加：

```python
# 引入第6课的 rerank 思路
from lessons.lesson06_rerank import lightweight_rerank  # 或直接复制函数过来
candidates = [doc for _, doc, _ in merged]
# 用查询重新 rerank（这里用原始 query 或子问题拼接）
```

**思考**：Query 改写（问题侧）+ 混合检索/Rerank（文档侧）组合起来，是生产级 RAG 的完整检索优化栈。你能画一张完整的"优化后检索流程图"吗？

---

## ✅ 完成本课后，你应该能回答
1. 为什么不能直接拿用户原话去检索？举两个"烂 query"的例子。
2. HyDE 的核心思想是什么？为什么用"假设答案"检索反而更准？
3. 多查询展开解决什么问题？适合什么场景？
4. 查询路由是什么概念？什么问题该路由到 BM25、什么该路由到向量？
5. 检索质量的两个维度（文档侧/问题侧）分别用什么手段优化？
