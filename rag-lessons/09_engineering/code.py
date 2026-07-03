"""
Lesson 09 — 工程化：交互式 RAG 问答助手（毕业作品）
====================================================
把前 8 课学的拼成一个接近生产可用的小系统：
    ✅ 多文档加载（扫描 data/sample_docs/ 所有 md）
    ✅ 切块 + 向量化 + Chroma 持久化
    ✅ embedding 缓存（已处理过的文档不重复向量化）
    ✅ 向量检索
    ✅ 引用溯源（答案带【材料N】+ 来源文件名）
    ✅ 流式输出（打字机效果）
    ✅ 交互式 REPL（持续问答，输 exit 退出）
    ✅ 防幻觉 prompt

运行：python lessons/09_engineering/code.py
然后输入问题开始问答，输 exit 退出。
"""
from __future__ import annotations

import hashlib
import os

import chromadb
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from zhipuai import ZhipuAI

EMBEDDING_MODEL = "embedding-3"
CHAT_MODEL = "glm-4"  # 想免费可换 "glm-4-flash"
COLLECTION_NAME = "lesson09_kb"
CHROMA_PATH = "./chroma_db_09"
DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sample_docs")

CHUNK_SIZE = 400
CHUNK_OVERLAP = 60
TOP_K = 3


def create_client() -> ZhipuAI:
    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env 里配置 ZHIPUAI_API_KEY")
    return ZhipuAI(api_key=api_key)


def embed(client: ZhipuAI, texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [d.embedding for d in sorted(resp.data, key=lambda x: x.index)]


def file_hash(path: str) -> str:
    """算文件内容的 hash，用于判断文件是否改动过（缓存依据）。"""
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def chunk_file(path: str) -> list[str]:
    """读取一个 md 文件并切块。"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )
    return splitter.split_text(text)


def build_or_update_kb(client: ZhipuAI, collection):
    """加载所有 md 文件，只向量化【新增或改过】的文件（embedding 缓存）。

    缓存逻辑：用文件内容 hash 判断。已在 Chroma 里的（hash 匹配）跳过。
    """
    md_files = [
        os.path.join(DOCS_DIR, f)
        for f in os.listdir(DOCS_DIR)
        if f.endswith(".md")
    ]
    print(f"📂 发现 {len(md_files)} 个文档文件")

    # 取出已在库里的文件 hash 集合（之前存进 metadata 的）
    existing = set()
    try:
        all_data = collection.get()
        for meta in all_data.get("metadatas", []):
            if meta and "src_hash" in meta:
                existing.add(meta["src_hash"])
    except Exception:
        pass

    new_chunks = []
    new_embeddings = []
    new_metas = []
    new_ids = []
    skipped = 0

    for path in md_files:
        fname = os.path.basename(path)
        fhash = file_hash(path)
        # 缓存命中：这个文件内容没变，跳过
        if fhash in existing:
            skipped += 1
            continue
        chunks = chunk_file(path)
        embs = embed(client, chunks)
        for i, (chunk, emb) in enumerate(zip(chunks, embs)):
            new_chunks.append(chunk)
            new_embeddings.append(emb)
            new_metas.append({"source": fname, "src_hash": fhash, "chunk_idx": i})
            new_ids.append(f"{fname}_{i}")

    if new_chunks:
        collection.add(
            documents=new_chunks,
            embeddings=new_embeddings,
            metadatas=new_metas,
            ids=new_ids,
        )
        print(f"✅ 新增/更新 {len(new_chunks)} 个块（来自改动过的文件）")
    if skipped:
        print(f"♻️  跳过 {skipped} 个未改动的文件（命中缓存，省了 embedding 调用）")
    if not new_chunks and not skipped:
        print("（没有文档）")
    print(f"📚 知识库现有 {collection.count()} 个块")


def retrieve(collection, query_vec, top_k=TOP_K):
    """向量检索，返回 [(doc, source), ...]。"""
    results = collection.query(query_embeddings=[query_vec], n_results=top_k)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    return list(zip(docs, [m.get("source", "?") for m in metas]))


def build_prompt(question: str, retrieved: list) -> str:
    """拼防幻觉 prompt，给每条材料编号（供引用溯源）。"""
    context = "\n\n".join(f"【材料{i+1}】{doc}" for i, (doc, _) in enumerate(retrieved))
    return (
        "你是严谨的问答助手。请遵守：\n"
        "1. 只根据下面材料回答，材料没有就说'我不知道'，不要编造。\n"
        "2. 在答案中用【材料N】标注信息来源。\n\n"
        f"【材料】\n{context}\n\n【问题】{question}"
    )


def answer_stream(client: ZhipuAI, prompt: str):
    """流式生成，逐字 yield。"""
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    for chunk in resp:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def main():
    print("=" * 60)
    print("Lesson 09 — 交互式 RAG 问答助手（毕业作品）")
    print("=" * 60)
    print("输入问题开始问答，输 exit 退出。\n")

    client = create_client()

    # 初始化 Chroma（持久化，跨会话复用）
    db = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = db.get_or_create_collection(name=COLLECTION_NAME)

    # 加载/更新知识库（带缓存）
    print("初始化知识库...")
    build_or_update_kb(client, collection)
    print()

    # 交互式 REPL
    while True:
        try:
            question = input("🙋 你的问题> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit", "退出"):
            print("再见！")
            break

        # 检索
        print("\n🔎 检索中...")
        query_vec = embed(client, [question])[0]
        retrieved = retrieve(collection, query_vec)

        print("📚 找到相关材料：")
        for i, (doc, source) in enumerate(retrieved, 1):
            print(f"  [{i}] (来自 {source}) {doc[:40]}...")

        # 流式生成
        prompt = build_prompt(question, retrieved)
        print("\n🤖 回答：")
        for piece in answer_stream(client, prompt):
            print(piece, end="", flush=True)
        print("\n")


if __name__ == "__main__":
    main()
