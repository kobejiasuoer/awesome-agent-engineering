"""
Lesson 07 — Query 改写：让检索更准
==================================
本脚本对比三种检索方式，看 query 改写的威力：
    ① 原始 query 直接检索（基线）
    ② HyDE：先让 LLM 生成"假设答案"，用假设答案检索
    ③ 多查询展开：把问题拆成多个子问题，分别检索合并

运行：python lessons/07_query_rewrite/code.py
"""
from __future__ import annotations

import os

import chromadb
import numpy as np
from dotenv import load_dotenv
from zhipuai import ZhipuAI

EMBEDDING_MODEL = "embedding-3"
CHAT_MODEL = "glm-4"  # 想免费可换 "glm-4-flash"
COLLECTION_NAME = "lesson07_kb"
CHROMA_PATH = "./chroma_db_07"

# ──────────────────────────────────────────────────────────────
# 文档库：故意用正式、完整的表述（真实文档就是这样）
# ──────────────────────────────────────────────────────────────
DOCUMENTS = [
    "带薪年假申请流程：员工入职满一年后，可在 OA 系统提交年假申请单，经直属上级审批后生效。年假天数按工龄递增。",
    "病假管理规定：员工因病无法出勤，需提供三甲医院开具的病假诊断书，通过 OA 系统提交病假申请，病假期间发放基本工资的 60%。",
    "出差报销制度：员工因公出差产生的交通、住宿费用，需保留原始发票，在出差结束后 7 个工作日内通过财务系统提交报销单。",
    "远程办公申请：经直属上级书面批准，员工每周可申请最多两个工作日居家办公，需在申请中说明工作安排。",
    "新员工入职引导：新员工入职首日需到人力资源部报到，领取工牌、开通各类系统账号，并由导师带领熟悉公司制度。",
]

# 故意用一个口语化、模糊的烂问题（直接检索效果差）
RAW_QUERY = "我想歇几天，那个流程是啥？要啥材料不？"
# 正确答案：应该召回 DOCUMENTS[0]（年假申请流程）和 DOCUMENTS[1]（病假材料）


def create_zhipu_client() -> ZhipuAI:
    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env 里配置 ZHIPUAI_API_KEY")
    return ZhipuAI(api_key=api_key)


def embed_texts(client: ZhipuAI, texts: list[str]) -> np.ndarray:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    sorted_data = sorted(resp.data, key=lambda x: x.index)
    return np.array([d.embedding for d in sorted_data])


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def chat(client: ZhipuAI, prompt: str) -> str:
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def build_kb(client: ZhipuAI):
    embeddings = embed_texts(client, DOCUMENTS)
    db = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        db.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    col = db.get_or_create_collection(name=COLLECTION_NAME)
    col.add(
        documents=DOCUMENTS,
        embeddings=embeddings.tolist(),
        ids=[f"doc_{i}" for i in range(len(DOCUMENTS))],
    )
    return col


def vector_search(doc_vectors: np.ndarray, query_vec: np.ndarray, top_k: int = 3):
    """向量检索，返回 [(doc_idx, doc, score)]。"""
    sims = [(i, DOCUMENTS[i], cosine_sim(query_vec, dv)) for i, dv in enumerate(doc_vectors)]
    sims.sort(key=lambda x: x[2], reverse=True)
    return sims[:top_k]


def print_results(label: str, results, correct_indices: list[int]):
    """打印检索结果，标记正确答案。"""
    print(f"\n【{label}】Top-{len(results)}：")
    for rank, (idx, doc, score) in enumerate(results, 1):
        mark = " ✅正确" if idx in correct_indices else ""
        print(f"  {rank}. [{idx}] 分数={score:.4f} | {doc[:35]}...{mark}")
    # 统计召回情况
    hit = sum(1 for idx, _, _ in results if idx in correct_indices)
    print(f"  → 召回正确答案 {hit}/{len(correct_indices)} 条")


def rrf_merge_multi(results_list: list[list], k: int = 60, top_k: int = 3):
    """多查询结果用 RRF 融合。results_list: 每个元素是一路 [(idx, doc, score)]。"""
    scores = {}
    docs_map = {}
    for results in results_list:
        for rank, (idx, doc, _) in enumerate(results, 1):
            scores[idx] = scores.get(idx, 0) + 1 / (k + rank)
            docs_map[idx] = doc
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [(idx, docs_map[idx], score) for idx, score in ranked]


# ════════════════════════════════════════════════════════════
# 实验①：原始 query 直接检索（基线）
# ════════════════════════════════════════════════════════════
def section_raw_query(client, doc_vectors):
    print("\n" + "═" * 60)
    print("① 原始 query 直接检索（基线）")
    print("═" * 60)
    print(f"\n原始问题：{RAW_QUERY}")
    query_vec = embed_texts(client, [RAW_QUERY])[0]
    results = vector_search(doc_vectors, query_vec, top_k=3)
    print_results("直接检索", results, correct_indices=[0, 1])
    print("\n👉 观察：口语化问题向量不够具体，可能召不准年假/病假那两条。")
    return query_vec


# ════════════════════════════════════════════════════════════
# 实验②：HyDE 改写
# ════════════════════════════════════════════════════════════
def section_hyde(client, doc_vectors):
    print("\n" + "═" * 60)
    print("② HyDE：用'假设答案'去检索")
    print("═" * 60)

    # ① 让 LLM 生成假设答案（一段像文档的陈述句）
    hyde_prompt = (
        f"请根据下面这个问题，写一段 50 字左右的'假设性答案'。"
        f"要求：写成正式的公司制度陈述句（像真实文档那样），"
        f"即使内容不完全准确也没关系，重点是格式像文档。\n\n"
        f"问题：{RAW_QUERY}\n\n假设性答案："
    )
    hypothetical_doc = chat(client, hyde_prompt).strip()
    print(f"\n②-1 LLM 生成的假设答案：")
    print(f"  {hypothetical_doc}")

    # ② 用假设答案（而非原问题）向量化去检索
    hyde_vec = embed_texts(client, [hypothetical_doc])[0]
    results = vector_search(doc_vectors, hyde_vec, top_k=3)
    print_results("HyDE 检索", results, correct_indices=[0, 1])

    print("\n👉 观察：假设答案是陈述句，和文档的'语言形态'一致，向量更近，召回更准。")


# ════════════════════════════════════════════════════════════
# 实验③：多查询展开
# ════════════════════════════════════════════════════════════
def section_multi_query(client, doc_vectors):
    print("\n" + "═" * 60)
    print("③ 多查询展开：拆成多个子问题分别检索")
    print("═" * 60)

    # ① 让 LLM 把原问题拆成多个子问题
    multi_prompt = (
        f"请把下面这个用户问题，拆解成 3 个更具体、更适合检索的子问题。"
        f"每个子问题单独一行，只输出问题本身，不要编号和其他内容。\n\n"
        f"用户问题：{RAW_QUERY}\n\n3 个子问题："
    )
    sub_queries_text = chat(client, multi_prompt).strip()
    sub_queries = [q.strip() for q in sub_queries_text.split("\n") if q.strip()][:3]
    print(f"\n③-1 LLM 拆出的子问题：")
    for i, q in enumerate(sub_queries, 1):
        print(f"  {i}. {q}")

    # ② 每个子问题分别检索
    print(f"\n③-2 各子问题分别检索：")
    all_results = []
    sub_vecs = embed_texts(client, sub_queries)
    for i, sv in enumerate(sub_vecs):
        res = vector_search(doc_vectors, sv, top_k=3)
        all_results.append(res)
        top_idx = res[0][0]
        print(f"  子问题{i+1} → Top1: [{top_idx}] {DOCUMENTS[top_idx][:30]}...")

    # ③ RRF 融合
    merged = rrf_merge_multi(all_results, top_k=3)
    print_results("多查询融合 (RRF)", merged, correct_indices=[0, 1])

    print("\n👉 观察：多角度覆盖后，年假和病假两条正确答案都更容易被召回。")


def main():
    print("=" * 60)
    print("Lesson 07 — Query 改写：让检索更准")
    print("=" * 60)

    client = create_zhipu_client()
    print("\n正在向量化文档...")
    doc_vectors = embed_texts(client, DOCUMENTS)
    build_kb(client)
    print(f"✅ {len(DOCUMENTS)} 篇文档已就绪")

    print(f"\n🔎 口语化烂问题：{RAW_QUERY}")
    print(f"   （正确答案应是 [0]年假申请 和 [1]病假管理）")

    # ① 原始 query
    section_raw_query(client, doc_vectors)

    # ② HyDE
    section_hyde(client, doc_vectors)

    # ③ 多查询展开
    section_multi_query(client, doc_vectors)

    print("\n" + "=" * 60)
    print("完成！检索质量 = 文档侧质量 × 问题侧质量。改写 query 提升问题侧。")
    print("=" * 60)


if __name__ == "__main__":
    main()
