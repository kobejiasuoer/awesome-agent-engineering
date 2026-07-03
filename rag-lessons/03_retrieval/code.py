"""
Lesson 03 — 向量检索：从相似到 Top-K
=====================================
本脚本把"检索"这个黑盒拆开，让你看清：
    ① 暴力检索 vs Chroma 检索（结果对比 + 耗时对比）
    ② Top-K 实验（K=1/3/5 的差异）
    ③ metadata 过滤（先按标签筛选，再做向量检索）
    ④ 距离度量对比（cosine vs l2）

运行：python lessons/03_retrieval/code.py
"""
from __future__ import annotations

import os
import time

import chromadb
import numpy as np
from dotenv import load_dotenv
from zhipuai import ZhipuAI

EMBEDDING_MODEL = "embedding-3"
COLLECTION_NAME = "lesson03_docs"
CHROMA_PATH = "./chroma_db_03"

# ──────────────────────────────────────────────────────────────
# 文档集：8 条员工手册知识，每条带 category 标签（供 metadata 过滤演示）
# ──────────────────────────────────────────────────────────────
DOCUMENTS = [
    "年假：入职满 1 年有 5 天带薪年假，满 3 年有 10 天，满 5 年有 15 天。",
    "病假需提供三甲医院病假条，期间发基本工资的 60%。",
    "婚假：依法登记结婚享有 3 天带薪婚假。",
    "餐饮报销每人每餐不超过 80 元，需保留发票。",
    "差旅住宿一线城市每晚不超过 500 元，二线城市不超过 400 元。",
    "报销单需在费用发生后 30 个自然日内提交，逾期不受理。",
    "每周可远程办公最多 2 个工作日，需直属上级批准。",
    "试用期员工不适用远程办公政策。",
]
METADATA = [
    {"category": "请假"},
    {"category": "请假"},
    {"category": "请假"},
    {"category": "报销"},
    {"category": "报销"},
    {"category": "报销"},
    {"category": "远程"},
    {"category": "远程"},
]

#QUESTION = "我出差住了两晚酒店，能报多少住宿费？"
QUESTION = "我在家办公的时候生病了，能请病假吗？"


def create_zhipu_client() -> ZhipuAI:
    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env 里配置 ZHIPUAI_API_KEY")
    return ZhipuAI(api_key=api_key)


def embed_texts(client: ZhipuAI, texts: list[str]) -> np.ndarray:
    """批量向量化，返回 numpy 数组。"""
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    sorted_data = sorted(resp.data, key=lambda x: x.index)
    return np.array([d.embedding for d in sorted_data])


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """算两个向量的余弦相似度。"""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ════════════════════════════════════════════════════════════
# ① 暴力检索：自己手写遍历
# ════════════════════════════════════════════════════════════
def brute_force_search(
    doc_vectors: np.ndarray, query_vec: np.ndarray, docs: list[str], top_k: int
) -> list[tuple[str, float]]:
    """遍历所有文档向量，算相似度，排序取前 K。

    返回 [(文档, 相似度), ...]，相似度从高到低。
    """
    sims = [cosine_sim(query_vec, dv) for dv in doc_vectors]
    # 按相似度从高到低排序，取前 top_k
    ranked = sorted(zip(docs, sims), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


# ════════════════════════════════════════════════════════════
# ② Chroma 检索：用向量库做同样的事
# ════════════════════════════════════════════════════════════
def build_chroma_collection(doc_vectors: np.ndarray):
    """把文档向量存进 Chroma（默认 cosine 度量）。"""
    db = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        db.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    # cosine: 用余弦相似度；想试 l2 欧氏距离就改成 metadata={"hnsw:space": "l2"}
    collection = db.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )
    collection.add(
        documents=DOCUMENTS,
        embeddings=doc_vectors.tolist(),
        metadatas=METADATA,
        ids=[f"doc_{i}" for i in range(len(DOCUMENTS))],
    )
    return collection


def chroma_search(collection, query_vec: np.ndarray, top_k: int, where: dict = None):
    """用 Chroma 做向量检索。where 可选：metadata 过滤条件。"""
    results = collection.query(
        query_embeddings=[query_vec.tolist()],
        n_results=top_k,
        where=where,  # 例如 {"category": "报销"}
    )
    docs = results["documents"][0]
    dists = results["distances"][0]
    return list(zip(docs, dists))


def section_brute_vs_chroma(client, doc_vectors, query_vec):
    """第①部分：暴力 vs Chroma 结果与耗时对比。"""
    print("\n" + "═" * 60)
    print("① 暴力检索 vs Chroma 检索")
    print("═" * 60)

    # 暴力
    t0 = time.perf_counter()
    brute = brute_force_search(doc_vectors, query_vec, DOCUMENTS, top_k=3)
    t_brute = (time.perf_counter() - t0) * 1000

    # Chroma
    collection = build_chroma_collection(doc_vectors)
    t0 = time.perf_counter()
    chroma = chroma_search(collection, query_vec, top_k=3)
    t_chroma = (time.perf_counter() - t0) * 1000

    print(f"\n问题：{QUESTION}\n")
    print("【暴力检索】(耗时 %.2f ms)" % t_brute)
    for doc, sim in brute:
        print(f"  相似度={sim:.4f} | {doc}")
    print("\n【Chroma 检索】(耗时 %.2f ms)" % t_chroma)
    for doc, dist in chroma:
        # Chroma cosine 返回的是 distance = 1 - 余弦相似度，越小越相似
        print(f"  distance={dist:.4f} (≈相似度{1 - dist:.4f}) | {doc}")

    print("\n👉 观察：小数据量下两者结果几乎一致，说明 Chroma 做的就是「算距离+排序」。")
    print("   数据量大了之后，Chroma 用 ANN 算法会比暴力快很多。")
    return collection


def section_top_k_experiment(collection, query_vec):
    """第②部分：Top-K 实验。"""
    print("\n" + "═" * 60)
    print("② Top-K 实验（K = 1 / 3 / 5）")
    print("═" * 60)
    print(f"\n问题：{QUESTION}\n")
    for k in [1, 3, 5]:
        results = chroma_search(collection, query_vec, top_k=k)
        print(f"【K={k}】返回 {len(results)} 条：")
        for doc, dist in results:
            print(f"  {1 - dist:.4f} | {doc}")
        print()
    print("👉 观察：K 越大，排后面的文档越来越不相关（噪声）。RAG 里 K 通常 3~5 起步。")


def section_metadata_filter(collection, query_vec):
    """第③部分：metadata 过滤。"""
    print("\n" + "═" * 60)
    print("③ metadata 过滤（只在'报销'类里检索）")
    print("═" * 60)
    # 同一个问题，加不加过滤对比
    print(f"\n问题：{QUESTION}\n")

    print("【不过滤】Top-3：")
    for doc, dist in chroma_search(collection, query_vec, top_k=3):
        print(f"  {1 - dist:.4f} | {doc}")

    print("\n【过滤 category='报销'】Top-3：")
    for doc, dist in chroma_search(collection, query_vec, top_k=3, where={"category": "远程"}):
        print(f"  {1 - dist:.4f} | {doc}")

    print("\n👉 观察：加过滤后，结果全是'报销'类，不会被请假/远程类的内容干扰。")
    print("   生产环境几乎必用：能控权限、提精度。")


def section_distance_metrics(doc_vectors, query_vec):
    """第④部分：距离度量对比（cosine vs l2）。"""
    print("\n" + "═" * 60)
    print("④ 距离度量对比：cosine vs l2")
    print("═" * 60)

    db = chromadb.PersistentClient(path=CHROMA_PATH)
    results = {}
    for metric in ["cosine", "l2"]:
        try:
            db.delete_collection(f"l03_{metric}")
        except Exception:
            pass
        col = db.get_or_create_collection(
            name=f"l03_{metric}", metadata={"hnsw:space": metric}
        )
        col.add(
            documents=DOCUMENTS,
            embeddings=doc_vectors.tolist(),
            ids=[f"doc_{i}" for i in range(len(DOCUMENTS))],
        )
        res = col.query(query_embeddings=[query_vec.tolist()], n_results=3)
        results[metric] = list(zip(res["documents"][0], res["distances"][0]))

    print(f"\n问题：{QUESTION}\n")
    for metric, res in results.items():
        print(f"【{metric}】Top-3：")
        for doc, dist in res:
            print(f"  distance={dist:.4f} | {doc}")
        print()

    print("👉 观察：cosine 和 l2 的排序结果可能略有不同，但最相关的通常都排第一。")
    print("   RAG 默认用 cosine，因为它只看语义方向、不受向量长度影响。")


def main():
    print("=" * 60)
    print("Lesson 03 — 向量检索：从相似到 Top-K")
    print("=" * 60)

    client = create_zhipu_client()

    print("\n正在向量化文档和问题...")
    doc_vectors = embed_texts(client, DOCUMENTS)
    query_vec = embed_texts(client, [QUESTION])[0]
    print(f"✅ {len(DOCUMENTS)} 篇文档 + 1 个问题向量已就绪")

    # ① 暴力 vs Chroma
    collection = section_brute_vs_chroma(client, doc_vectors, query_vec)

    # ② Top-K 实验
    #section_top_k_experiment(collection, query_vec)

    # ③ metadata 过滤
    section_metadata_filter(collection, query_vec)

    # ④ 距离度量对比
    #section_distance_metrics(doc_vectors, query_vec)

    print("\n" + "=" * 60)
    print("完成！你现在理解了检索的本质：算距离 + 排序 + 取 Top-K。")
    print("向量库的价值在于：把这件事做得又快、又能持久化、还能过滤。")
    print("=" * 60)


if __name__ == "__main__":
    main()
