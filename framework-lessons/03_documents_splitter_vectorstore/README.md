# Lesson 03 — 文档处理：Loaders + Splitters + VectorStores

> **本课定位**：把 RAG 的"数据进入"环节工程化。在 RAG L03/L04 你手写过 `open().read()` 加载、手写 chromadb 入库、`RecursiveCharacterTextSplitter`（这个你**已经用过**！）切纯字符串。现在用 LangChain 的 `Document` 抽象把它们串成标准流水线。
>
> **映射的手写课**：
> - `rag-lessons/03_retrieval`（手写 `chromadb.PersistentClient` + `collection.add(query_embeddings=...)`）
> - `rag-lessons/04_chunking`（手写 `open().read()` + `RecursiveCharacterTextSplitter.split_text()`）

---

## 一、`Document` —— 贯穿全程的统一载体

这是本课最核心的抽象。回忆你手写时，数据用什么形态流转？

```python
# RAG L03 手写：文档是"字符串列表 + 平行的 metadata 列表"
DOCUMENTS = ["年假：...", "病假：...", ...]      # 文本
METADATA = [{"category": "请假"}, {"category": "请假"}, ...]   # 元数据，单独维护
# 两者靠"索引对齐"勉强绑定，一旦顺序错乱就乱了
```

```python
# RAG L04 手写：切完是 list[str]，纯字符串，没有 metadata
chunks = splitter.split_text(text)   # → list[str]
```

LangChain 用 `Document` 对象把"内容 + 元数据"绑成一个整体：

```python
from langchain_core.documents import Document
doc = Document(
    page_content="年假：入职满 1 年有 5 天...",
    metadata={"source": "employee_handbook.md", "category": "请假"}
)
doc.page_content   # 文本内容
doc.metadata       # 元数据（来源、类别、页码……任意键值对）
```

### 为什么这是大事？

1. **内容与元数据不分离**：不用再维护两个平行列表，不会错位。
2. **元数据全链路透传**：切分时自动继承、入库时自动存储、检索时自动返回、还能用它做 metadata 过滤（你 RAG L03 学过的 `where={"category":"报销"}`）。
3. **统一接口**：Loaders 吐 `Document`，Splitters 吃 `Document` 吐 `Document`，VectorStores 吃 `Document`——所有组件用同一种"货币"。

> 后面你会发现，RAG 的整条链路（load→split→embed→store→retrieve）全是 `Document` 在流动。这是 LangChain 设计的精髓之一。

---

## 二、组件一：Document Loaders —— 从"手写 open()"到"一键加载"

### 手写 vs 框架

```python
# RAG L04 手写：
with open(DOC_PATH, "r", encoding="utf-8") as f:
    text = f.read()        # 一个字符串

# 框架版：
from langchain_community.document_loaders import TextLoader
loader = TextLoader("data/sample_docs/employee_handbook.md", encoding="utf-8")
docs = loader.load()       # → [Document]，自动带 metadata={"source": "文件路径"}
```

看起来只是多了层包装，但 Loader 的价值在于：

1. **自动打 metadata**：`source`（文件路径）自动填好，检索时能追溯"这段话来自哪个文件"。
2. **统一接口**：`TextLoader` / `PyPDFLoader` / `WebBaseLoader` / `DirectoryLoader` 都返回 `List[Document]`，换数据源只改 Loader 类。
3. **生态丰富**：几十种 Loader 覆盖 PDF、Word、网页、Notion、GitHub……（L01 README 提到的"框架生态"价值在这里体现）。

| 你要加载的 | 手写要做什么 | 用 Loader |
|-----------|-------------|----------|
| .txt/.md | `open().read()` | `TextLoader` |
| .pdf | 装 pdf 库 + 解析（很麻烦） | `PyPDFLoader`（一行）|
| 网页 | `requests` + `BeautifulSoup` 解析 | `WebBaseLoader` |
| 整个目录 | 手写 `os.walk` 循环 | `DirectoryLoader`（一行）|

> 本课用 `TextLoader`（够用）。重点是理解"Loader 把异构数据源统一成 `List[Document]`"这个抽象。

---

## 三、组件二：Text Splitters —— 你在 RAG L04 已经用过！

好消息：`RecursiveCharacterTextSplitter` 你在 **RAG L04 已经用过**了。原理你懂（按分隔符优先级递归切、chunk_size/overlap 的取舍）。

这里只讲**框架用法的升级点**：

### `split_text` vs `split_documents`

```python
# RAG L04 你用的：吃字符串，吐字符串
chunks = splitter.split_text(text)       # → list[str]

# 框架版：吃 Document，吐 Document（metadata 自动透传！）
chunks = splitter.split_documents(docs)  # → list[Document]
```

这是关键升级：`split_documents` 切完的每个 chunk **自动继承**父 Document 的 metadata。这样切完入库后，你还能知道"这段话来自哪个文件、哪一类"。

### 其他 Splitter（了解）

除了 `RecursiveCharacterTextSplitter`，LangChain 还有：

| Splitter | 切分依据 | 适用 |
|----------|---------|------|
| `CharacterTextSplitter` | 单一分隔符 | 最简单，但容易劈断句子 |
| `RecursiveCharacterTextSplitter` | 多级分隔符优先级（**最常用**）| 通用文本 ✅ |
| `MarkdownHeaderTextSplitter` | 按 Markdown 标题（## ###）| 结构化文档（本课会演示）|
| `TokenTextSplitter` | 按 token 数 | 精确控制 token 成本 |
| `PythonCodeTextSplitter` | 按代码结构（函数/类）| 代码 |

本课会演示 `RecursiveCharacterTextSplitter`（通用）+ `MarkdownHeaderTextSplitter`（按结构）两种，让你体会"不同文档类型该用不同 Splitter"。

> **原理没变**：切块的核心仍是你在 RAG L04 学的——"在语义边界处切，每块是一个完整主题"。框架只是提供了更多切法、并自动处理 metadata。

---

## 四、组件三：VectorStores —— 从"手写 chromadb"到"一行入库"

### 手写 vs 框架

```python
# RAG L03 手写（约 15 行入库 + 检索）：
db = chromadb.PersistentClient(path=CHROMA_PATH)
collection = db.get_or_create_collection(name=COLLECTION_NAME)
collection.add(
    documents=DOCUMENTS,
    embeddings=doc_vectors.tolist(),   # 你得先自己调 embed_texts() 算向量
    metadatas=METADATA,
    ids=[f"doc_{i}" for i in range(len(DOCUMENTS))],
)
results = collection.query(query_embeddings=[query_vec.tolist()], n_results=3)

# 框架版（3 行）：
from langchain_chroma import Chroma
vectorstore = Chroma.from_documents(chunks, embeddings, collection_name=..., persist_directory=...)
results = vectorstore.similarity_search("问题", k=3)
```

框架替你做了什么？

1. **自动 embedding**：`from_documents` 内部自动调用 embeddings 对象算向量（省掉你手写 `embed_texts()`）。
2. **自动 id 生成**：不用手写 `ids=[f"doc_{i}"...]`。
3. **统一检索接口**：`.similarity_search(query, k=3)` / `.similarity_search_with_score(...)` / `.as_retriever()`，返回的是 `Document` 而非裸字典。
4. **可替换**：`Chroma` / `FAISS` / `Pinecone` 实现同一接口，换向量库只改类名（你在 L04 exercise 里验证过这个想法）。

### `as_retriever()` —— 把向量库变成 LCEL 链可用的积木

这是衔接 L01/L02 的关键：

```python
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
# retriever 是 Runnable，能接进 LCEL 链
chain = {"context": retriever, "question": RunnablePassthrough()} | prompt | llm | parser
```

你在 L01 已经用过它。现在你理解了：`as_retriever()` 把"向量库"包装成标准检索器接口，让检索这一步也能用 `|` 串联。

---

## 五、完整流水线：load → split → embed/store → retrieve

```
TextLoader.load()                    → List[Document]   (带 source metadata)
        ↓
RecursiveCharacterTextSplitter.split_documents()  → List[Document]   (metadata 透传)
        ↓
Chroma.from_documents()              → VectorStore     (自动 embedding + 入库)
        ↓
.similarity_search() 或 .as_retriever()  → List[Document]   (检索结果)
```

每一步的输入输出都是 `Document`（或其列表）。这是 LangChain RAG 工程化的核心美感——**统一数据载体让组件可拼装、可替换**。

对比你 RAG L03 + L04 手写时：文档是 `list[str]`、metadata 是平行 `list[dict]`、向量是 `np.ndarray`、检索结果是嵌套 dict……类型在各个环节反复转换。框架用一个 `Document` 抹平了这些摩擦。

---

## 六、本课代码

`code.py` 四个实验：

1. **TextLoader**：加载员工手册，对比手写 `open().read()`，看 `Document` 的 metadata
2. **split_documents**：用 RecursiveCharacterTextSplitter 切，对比 RAG L04 的 `split_text`，观察 metadata 透传
3. **Chroma.from_documents**：一行入库（对比 RAG L03 手写 15 行），`similarity_search` 检索
4. **MarkdownHeaderTextSplitter**：按标题切（按结构切的高级用法），体会"不同文档类型用不同 Splitter"

---

## 七、小结 & 下节预告

✅ 现在你应该明白：
- `Document`（page_content + metadata）是贯穿 RAG 全链路的统一载体
- Loaders 把异构数据源统一成 `List[Document]`
- `split_documents` 比你 RAG L04 用的 `split_text` 多了"metadata 自动透传"
- `Chroma.from_documents` + `as_retriever()` 把向量库变成 LCEL 可用的积木
- 切块/检索的**原理没变**（你 RAG L03/L04 学的照样适用），框架是封装

🔜 **L04** 把 L01-L03 全部串起来：Retrievers + RAG Chain——用一条 LCEL 链组装完整 RAG，对应你 RAG L01-L05 的全部逻辑。
