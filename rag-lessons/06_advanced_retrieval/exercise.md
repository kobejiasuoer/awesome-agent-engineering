# Lesson 06 练习

> 改 `code.py` 里的代码，运行 `python lessons/06_advanced_retrieval/code.py` 观察变化。
> 本课会调用 embedding API（不调 chat，成本很低）。

---

## 练习 1：换一个纯语义查询，看向量检索的优势
把 `QUERY` 改成一个**纯语义、不含编号**的查询：

```python
QUERY = "我想休个假放松一下，有什么政策？"
```

（正确答案应该是"年假"相关文档）

**观察**：这次向量检索应该比 BM25 表现好——因为它懂"休个假放松"≈"年假"。

**思考**：这印证了什么？不同类型的查询适合不同的检索方式，这也是为什么需要混合检索。

---

## 练习 2：调整 RRF 的 k 值
在 `rrf_fusion` 里把 `k` 从 60 改成 **1**，再改成 **200**。

```python
def rrf_fusion(vector_results, bm25_results, k=1):  # 或 k=200
```

**观察**：k 很小时，排名靠前的文档得分差距被拉大（更看排名）；k 很大时，所有文档得分趋于平均。

**思考**：k 控制的是"排名的区分度"。k=60 是经验值，你的数据上是不是别的 k 更好？（提示：通常不需要调，60 是很稳的默认值）

---

## 练习 3：实现加权融合（替代 RRF）
RRF 是按排名融合，另一种方法是按**原始分数加权**。在 `main()` 里加：

```python
def weighted_fusion(vec_results, bm25_results, alpha=0.5):
    """alpha 是向量检索的权重，1-alpha 是 BM25 的权重。"""
    # 先把两路分数各自归一化到 0~1（因为量纲不同）
    def normalize(results):
        scores = np.array([s for _, s in results])
        if scores.max() > scores.min():
            scores = (scores - scores.min()) / (scores.max() - scores.min())
        return {d: s for (d, _), s in zip(results, scores)}
    vec_norm = normalize(vec_results)
    bm25_norm = normalize(bm25_results)
    all_docs = set(vec_norm) | set(bm25_norm)
    fused = {d: alpha * vec_norm.get(d, 0) + (1 - alpha) * bm25_norm.get(d, 0) for d in all_docs}
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)
```

分别试 `alpha=0.3`（偏 BM25）、`alpha=0.7`（偏向量），看排名变化。

**思考**：加权融合和 RRF 各有什么优劣？（提示：加权需要归一化处理，RRF 不需要——这也是 RRF 流行的原因）

---

## 练习 4：理解召回率 vs 精确率
四种检索方式里，数一下"正确答案在 Top-K 里出现"的情况：

| 检索方式 | 正确答案在 Top-3 吗？ | 排第几？ |
|----------|----------------------|----------|
| 向量检索 | ？ | ？ |
| BM25 | ？ | ？ |
| 混合检索 | ？ | ？ |
| Rerank | ？ | ？ |

**思考**：
- "召回率"= 正确答案有没有进 Top-K（进来没有）
- "精确率"= 正确答案排第几（排得准不准）
- 哪种方式召回率最高？哪种精确率最高？

---

## ✅ 完成本课后，你应该能回答
1. 向量检索最大的软肋是什么？举一个翻车场景。
2. BM25 的工作原理（TF/IDF）？它擅长什么、不擅长什么？
3. 混合检索为什么是生产标配？RRF 融合是怎么算的？
4. Rerank 两段式架构是什么？为什么不一上来就用精排模型？
5. 召回率和精确率的区别？Rerank 主要提升哪一个？
