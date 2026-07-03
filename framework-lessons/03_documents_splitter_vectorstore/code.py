"""
Lesson 03 — 文档处理：Loaders + Splitters + VectorStores
=========================================================
把 RAG 的"数据进入"环节工程化。你手写过 open().read() + chromadb 手动入库，
这里用 LangChain 的 Document 抽象 + TextLoader + Chroma.from_documents 重写。

四个实验：
  ① TextLoader：加载员工手册，对比手写 open()，看 Document 的 metadata
  ② split_documents：RecursiveCharacterTextSplitter 切，对比 RAG L04 的 split_text
  ③ Chroma.from_documents：一行入库 + similarity_search（对比 RAG L03 手写 15 行）
  ④ MarkdownHeaderTextSplitter：按标题切（结构化切法）

运行：python framework-lessons/03_documents_splitter_vectorstore/code.py
"""
# 消除 langchain-community 的 sunset 警告（L01 README 已讲过背景）
import warnings
warnings.filterwarnings("ignore", message=".*langchain-community.*is being sunset.*")

import os

try:  # 兼容旧 Python 的 sqlite3（3.9+ 可忽略）
    import pysqlite3
    import sys
    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass

from dotenv import load_dotenv

# === LangChain 数据层组件 ===
from langchain_core.documents import Document                       # 统一数据载体
from langchain_community.document_loaders import TextLoader          # 文档加载器
from langchain_community.embeddings import ZhipuAIEmbeddings         # 智谱 embedding-3
from langchain_text_splitters import (                               # 切分器（独立包）
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter,
)
from langchain_chroma import Chroma                                  # Chroma 向量库（独立包）

EMBEDDING_MODEL = "embedding-3"
COLLECTION_NAME = "acme_handbook_l03"
CHROMA_PATH = "./chroma_db_l03"

# 复用已有样例文档（和前两门课共用同一份数据，方便对比）
DOC_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "sample_docs", "employee_handbook.md"
)


# ════════════════════════════════════════════════════════════
# 准备 embedding 模型
# ════════════════════════════════════════════════════════════
def create_embeddings():
    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env 里配置 ZHIPUAI_API_KEY")
    return ZhipuAIEmbeddings(model=EMBEDDING_MODEL, api_key=api_key)


# ════════════════════════════════════════════════════════════
# 实验①：TextLoader —— 从手写 open() 到一键加载
# ════════════════════════════════════════════════════════════
def experiment_1_loader():
    print("\n" + "═" * 64)
    print("实验①：TextLoader —— 加载文档为 Document 对象")
    print("═" * 64)

    # RAG L04 手写：with open(...) as f: text = f.read()  → 一个字符串
    # 框架版：loader.load() → List[Document]，自动带 metadata
    loader = TextLoader(DOC_PATH, encoding="utf-8")
    docs = loader.load()

    print(f"\n加载结果：{len(docs)} 个 Document 对象")
    print(f"类型：{type(docs[0]).__name__}")
    print(f"\n.page_content（前 80 字）：\n  {docs[0].page_content[:80]}...")
    print(f"\n.metadata（自动填的来源信息）：\n  {docs[0].metadata}")

    print("\n👉 对比 RAG L04 手写 open().read()：")
    print("   手写只得到一个裸字符串；TextLoader 得到 Document，自动带 source 元数据。")
    print("   这个 source 后面检索时能追溯到'这段话来自哪个文件'。")
    return docs


# ════════════════════════════════════════════════════════════
# 实验②：split_documents —— RecursiveCharacterTextSplitter 的框架用法
# ════════════════════════════════════════════════════════════
def experiment_2_splitter(docs):
    print("\n" + "═" * 64)
    print("实验②：split_documents —— 切 Document（metadata 自动透传）")
    print("═" * 64)

    # 这是你 RAG L04 已经用过的切分器！原理你懂：多级分隔符优先级递归切
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )

    # ⭐ 关键区别：
    #   RAG L04 你用 split_text(text)  → list[str]（纯字符串，丢 metadata）
    #   框架版用 split_documents(docs) → list[Document]（metadata 自动继承）
    chunks = splitter.split_documents(docs)

    print(f"\n切分结果：{len(chunks)} 个 chunk（Document）")
    lengths = [len(c.page_content) for c in chunks]
    print(f"每块字符数：{lengths}")

    print("\n前 3 块预览（注意 metadata 透传）：")
    for i, c in enumerate(chunks[:3], 1):
        preview = c.page_content.replace("\n", " ")[:50]
        print(f"  [{i}] ({len(c.page_content)}字) {preview}...")
        print(f"       metadata={c.metadata}")

    print("\n👉 对比 RAG L04 的 split_text：")
    print("   split_text 吐 list[str]（没 metadata）；split_documents 吐 list[Document]。")
    print("   每个 chunk 自动继承父文档的 source 元数据，后续可做过滤和溯源。")
    return chunks


# ════════════════════════════════════════════════════════════
# 实验③：Chroma.from_documents —— 一行入库 + similarity_search
# ════════════════════════════════════════════════════════════
def experiment_3_vectorstore(chunks, embeddings):
    print("\n" + "═" * 64)
    print("实验③：Chroma.from_documents —— 一行入库（对比 RAG L03 手写 15 行）")
    print("═" * 64)

    # RAG L03 手写（约 15 行）：
    #   db = chromadb.PersistentClient(path=...)
    #   collection = db.get_or_create_collection(name=...)
    #   embeddings = embed_texts(client, DOCUMENTS)     ← 你得自己算向量
    #   collection.add(documents=..., embeddings=..., metadatas=..., ids=...)
    #   results = collection.query(query_embeddings=[qv.tolist()], n_results=3)

    # ⭐ 框架版（1 行入库）：
    #   from_documents 内部自动调 embeddings 算向量、自动生成 id、自动存 metadata
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_PATH,
    )
    print(f"\n✅ 已入库 {len(chunks)} 个 chunk")

    # 检索：similarity_search（返回 Document，不是裸字典）
    question = "我工作 4 年了，能休几天年假？"
    print(f"\n检索：{question}")
    results = vectorstore.similarity_search(question, k=3)
    print("Top-3 结果：")
    for i, doc in enumerate(results, 1):
        preview = doc.page_content.replace("\n", " ")[:60]
        print(f"  [{i}] {preview}...")
        print(f"       source={doc.metadata.get('source', '?')}")

    print("\n👉 对比 RAG L03 手写：")
    print("   手写要自己 embed_texts + 手拼 add 参数 + 手剥 results['documents'][0]。")
    print("   框架版 from_documents 一行入库，similarity_search 直接返回 Document。")
    print("   ⭐ 检索结果自动带 metadata（source），这就是实验①Loader 打的标签的价值。")

    # 额外：演示 as_retriever() —— 衔接 L01/L02 的 LCEL 链
    retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
    print(f"\nas_retriever() 测试（k=2）：")
    r2 = retriever.invoke("试用期员工能远程办公吗")
    for i, d in enumerate(r2, 1):
        print(f"  [{i}] {d.page_content.replace(chr(10), ' ')[:55]}...")
    print("  → retriever 是 Runnable，能直接接进 LCEL 管道（L04 会用）")
    return vectorstore


# ════════════════════════════════════════════════════════════
# 实验④：MarkdownHeaderTextSplitter —— 按标题结构切
# ════════════════════════════════════════════════════════════
def experiment_4_markdown_splitter():
    print("\n" + "═" * 64)
    print("实验④：MarkdownHeaderTextSplitter —— 按 Markdown 标题切（结构化切法）")
    print("═" * 64)

    # 读取原始 markdown
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    # 按标题层级切：员工手册有 ## 1. 工作时间、## 2. 请假制度 ...
    # 每个标题下的内容会变成一个 Document，metadata 自动记录"属于哪个标题"
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("##", "section"),   # 二级标题 → 记为 section
            ("###", "subsection"),
        ]
    )
    md_chunks = header_splitter.split_text(text)

    print(f"\n按标题切分：{len(md_chunks)} 个 chunk")
    print("每个 chunk 自动带上所属标题的 metadata：\n")
    for i, c in enumerate(md_chunks, 1):
        section = c.metadata.get("section", "(无标题)")
        preview = c.page_content.replace("\n", " ")[:45]
        print(f"  [{i}] section={section!r}")
        print(f"       内容：{preview}...")

    print("\n👉 观察：")
    print("   RecursiveCharacterTextSplitter 按字符长度切（机械）；")
    print("   MarkdownHeaderTextSplitter 按文档结构切（语义）。")
    print("   结构化文档（手册/规范/文档站）用后者，切出来的块天然是完整主题。")
    print("   metadata 里的 section 还能用来做过滤检索（如只查'请假'章节）。")


# ════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════
def main():
    print("=" * 64)
    print("Lesson 03 — 文档处理：Loaders + Splitters + VectorStores")
    print("=" * 64)
    print("映射：rag-lessons/03_retrieval（手写Chroma）+ rag-lessons/04_chunking（切块）")

    embeddings = create_embeddings()

    # load
    docs = experiment_1_loader()
    # split
    chunks = experiment_2_splitter(docs)
    # store + retrieve
    experiment_3_vectorstore(chunks, embeddings)
    # 结构化切法
    experiment_4_markdown_splitter()

    print("\n" + "=" * 64)
    print("✅ 数据层小结：")
    print("   - Document（page_content + metadata）是贯穿全链路的统一载体")
    print("   - Loaders 把异构数据源统一成 List[Document]")
    print("   - split_documents 比你 RAG L04 的 split_text 多了 metadata 透传")
    print("   - Chroma.from_documents 一行入库（对比 RAG L03 手写 15 行）")
    print("   - 全程 Document 流动：load → split → store → retrieve")
    print("=" * 64)


if __name__ == "__main__":
    main()
