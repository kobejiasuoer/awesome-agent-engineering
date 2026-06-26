# Lesson 03 练习

> 改 `code.py` 里的代码，运行 `python lessons/03_retrieval/code.py` 观察变化。

---

## 练习 1：换一个"跨类别"的问题
把 `QUESTION` 改成：

```python
QUESTION = "我在家办公的时候生病了，能请病假吗？"
```

**观察**：
- 暴力检索和 Chroma 检索的结果是否一致？
- Top-K 变大时，召回了哪些类别的文档？（这个问题其实涉及"远程"和"请假"两个类别）

**思考**：这种跨类别的问题，单靠向量检索够吗？如果相关文档分散在两个类别里，metadata 过滤会不会反而帮倒忙？（这是后面"query 改写/多查询"要解决的）

---

## 练习 2：测试 metadata 过滤的"帮倒忙"
用练习 1 那个跨类别问题，在 `section_metadata_filter` 里把过滤条件改成只查"远程"：

```python
where={"category": "远程"}
```

**观察**：过滤后还能召回"病假"那条文档吗？

**思考**：这说明 metadata 过滤虽然能提精度，但用错了也会漏召回。什么场景下该用、什么场景下不该用？（提示：明确知道答案在某一个类别里时才用）

---

## 练习 3：自己实现一个"带 metadata 的暴力检索"
在 `brute_force_search` 基础上改造，加一个 `category_filter` 参数：

```python
def brute_force_search_with_filter(doc_vectors, query_vec, docs, metadatas, top_k, category_filter=None):
    results = []
    for i, dv in enumerate(doc_vectors):
        if category_filter and metadatas[i]["category"] != category_filter:
            continue  # 不符合类别的跳过
        sim = cosine_sim(query_vec, dv)
        results.append((docs[i], sim))
    ranked = sorted(results, key=lambda x: x[1], reverse=True)
    return ranked[:top_k]
```

调用它对比"过滤前"和"过滤后"的结果，理解"先筛后检"的逻辑。

---

## 练习 4：调大文档集，感受 ANN 的价值
把 `DOCUMENTS` 复制扩展到 100 条（可以用循环把现有 8 条重复几遍，或加更多内容），然后用 `QUESTION` 查。

**观察**：暴力检索和 Chroma 的耗时差距变大了吗？

**思考**：虽然重复内容会让相似度都接近 1，但你可以从耗时上感受到——数据量越大，向量库的 ANN 优势越明显。真实生产环境文档数都是万级以上，暴力检索完全不可行。

---

## ✅ 完成本课后，你应该能回答
1. 检索的本质是什么？（一句话）
2. 为什么大规模数据必须用向量库？ANN 解决了什么问题？
3. Top-K 是越大越好吗？为什么？
4. cosine 和 l2 这两种度量有什么区别？RAG 为什么默认用 cosine？
5. metadata 过滤解决什么问题？有什么副作用？
