# Lesson 03 练习 — Loaders + Splitters + VectorStores

> 本课练习重点体会 `Document` 抽象如何贯穿全链路。

---

## 练习 1：观察 metadata 透传（关键概念，10 分钟）

在 `experiment_2_splitter` 里，每个 chunk 的 metadata 是什么？为什么它能保留 source？

做一个实验：手动给加载后的 Document **加上自定义 metadata**，再切分，观察自定义 metadata 是否也透传到子 chunk：

```python
from langchain_core.documents import Document
docs[0].metadata["category"] = "HR手册"   # 手动加标签
chunks = splitter.split_documents(docs)
# 检查 chunks[0].metadata，category 还在吗？
```

**思考**：这种"metadata 透传"在生产环境有什么用？（提示：权限控制、来源追溯、分类过滤）

---

## 练习 2：对比 RecursiveCharacterTextSplitter 的两种调用（5 分钟）

同一段文本，分别用：
- `split_text(text)` —— 你 RAG L04 用的
- `split_documents([Document(page_content=text)])` —— 本课用的

```python
splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
# 方式 A
str_chunks = splitter.split_text(text)
# 方式 B
doc_chunks = splitter.split_documents([Document(page_content=text)])
```

打印两种结果的类型，对比返回值差异。**确认**：方式 B 返回的是 `Document`，方式 A 是裸 `str`。

---

## 练习 3：换 chunk_size 重新检索（对比 RAG L04 的发现，10 分钟）

把 `experiment_2_splitter` 里的 `chunk_size` 从 300 改成 **100** 和 **800**，分别入库检索同一个问题：

```python
for size in [100, 300, 800]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=50)
    chunks = splitter.split_documents(docs)
    vs = Chroma.from_documents(chunks, embeddings, ...)
    # 检索 "我工作4年了，能休几天年假？" 看 top1 结果
```

**观察**：
- chunk_size=100 时，年假那条信息可能被切成两半，检索结果是否还完整？
- chunk_size=800 时，一个 chunk 混了多个主题，检索精度如何？
- 这和你 RAG L04 的发现一致吗？（原理没变！）

---

## 练习 4：用 metadata 做过滤检索（衔接 RAG L03，10 分钟）

`experiment_4_markdown_splitter` 切完的 chunk 带有 `section` metadata（如 `'## 2. 请假制度'`）。

把这些 markdown chunk 入库后，用 `similarity_search` 的 `filter` 参数**只检索请假章节**：

```python
# 先把 markdown header 切的 chunks 入库
vs_md = Chroma.from_documents(md_chunks, embeddings, ...)

# 带 filter 检索（Chroma 的 filter 语法）
results = vs_md.similarity_search("年假", k=3, filter={"section": "## 2. 请假制度"})
```

**对比**：不加 filter 和加 filter 的检索结果有什么不同？

> 这对应你 RAG L03 学的 `where={"category": "报销"}` metadata 过滤——原理相同，框架封装了语法。

> ⚠️ 不同 VectorStore 的 filter 语法略有差异（Chroma 用 dict，Pinecone 用别的格式）。这是"可替换性"的小代价。

---

## 练习 5：换 VectorStore 验证可替换性（可选，10 分钟）

LangChain 的 VectorStore 接口统一。如果你装了 `faiss-cpu`（`pip install faiss-cpu`），把 `Chroma` 换成 `FAISS`：

```python
from langchain_community.vectorstores import FAISS
vs = FAISS.from_documents(chunks, embeddings)
# 后续 similarity_search / as_retriever 完全一样
```

**观察**：除了 `from_documents` 前的 import 和类名，其余代码一行没改——这就是 `VectorStore` 统一接口的价值。

> 没有 FAISS 也能理解这个概念：换向量库只改类名，是 LangChain 设计的核心承诺。

---

## 思考题（不写代码）

1. **为什么 LangChain 要发明 `Document` 这个抽象？** 如果不用它，回到"裸字符串 + 平行 metadata 列表"会带来什么问题？（回忆 RAG L03 手写时的痛点）

2. **`MarkdownHeaderTextSplitter` 和 `RecursiveCharacterTextSplitter` 什么时候各用哪个？** 给一个具体场景。

3. **`as_retriever()` 把向量库变成 Retriever 的意义是什么？** 直接用 `.similarity_search()` 不行吗？（提示：L04 要把检索器接进 LCEL 链）

---

## 完成标志

- [ ] 能说清 `Document` 抽象解决的核心问题（内容与元数据绑定）
- [ ] 理解 `split_documents` 和 `split_text` 的区别（metadata 透传）
- [ ] 跑通 `Chroma.from_documents` 一行入库
- [ ] 体会了不同 Splitter 适用于不同文档类型
- [ ] 理解整条流水线都是 `Document` 在流动

下一课 [L04](../04_retrievers_rag_chain/) 把 L01-L03 全部串成一条完整 RAG 链。
