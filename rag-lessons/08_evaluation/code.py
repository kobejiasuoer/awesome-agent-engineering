"""
Lesson 08 — RAG 评估：怎么知道好不好
=====================================
本脚本自己实现一套简化版 RAGAS，让你看清三个指标怎么算：
    ① 构造小型评估集（问题+标准答案+参考文档）
    ② 跑完整 RAG（检索+生成），收集召回文档和答案
    ③ 用 LLM 当裁判，打三个分：检索相关性 / 忠实度 / 答案相关性
    ④ 汇总分数 + 诊断该优化哪个环节

运行：python lessons/08_evaluation/code.py
"""
from __future__ import annotations

import os
import re

import chromadb
from dotenv import load_dotenv
from zhipuai import ZhipuAI

EMBEDDING_MODEL = "embedding-3"
CHAT_MODEL = "glm-4"  # 想免费可换 "glm-4-flash"
COLLECTION_NAME = "lesson08_kb"
CHROMA_PATH = "./chroma_db_08"

# ──────────────────────────────────────────────────────────────
# 文档库（被检索的知识）
# ──────────────────────────────────────────────────────────────
DOCUMENTS = [
    "年假：入职满 1 年有 5 天带薪年假，满 3 年有 10 天，满 5 年有 15 天。未休完的可在次年第一季度补休。",
    "病假需提供三甲医院病假条，期间发基本工资的 60%。连续病假超 3 天需提供住院证明。",
    "餐饮报销每人每餐不超过 80 元，差旅住宿一线城市不超过 500 元每晚。报销单需 30 天内提交。",
    "每周可远程办公最多 2 个工作日，需直属上级批准。试用期员工不适用远程办公。",
    "公司地址在科技园 3 号楼 8 层，前台电话 8001。（这条是干扰项，多数问题用不到）",
]

# ──────────────────────────────────────────────────────────────
# 评估集：问题 + 标准答案 + 参考文档（人工标注的 Ground Truth）
# 故意包含不同难度：简单/中等/刁钻/无关
# ──────────────────────────────────────────────────────────────
EVAL_SET = [
    {
        "question": "我工作 4 年了，能休几天年假？",
        "reference_answer": "满 3 年有 10 天，满 5 年才有 15 天，4 年属于满 3 年不满 5 年，所以是 10 天。",
        "reference_doc_idx": 0,
    },
    {
        "question": "病假工资怎么算？",
        "reference_answer": "病假期间发放基本工资的 60%，需提供三甲医院病假条。",
        "reference_doc_idx": 1,
    },
    {
        "question": "出差住酒店能报多少？",
        "reference_answer": "一线城市不超过 500 元每晚，需 30 天内提交报销单。",
        "reference_doc_idx": 2,
    },
    {
        "question": "试用期可以居家办公吗？",
        "reference_answer": "不可以，试用期员工不适用远程办公政策。",
        "reference_doc_idx": 3,
    },
    {
        "question": "公司股价最近怎么样？",
        "reference_answer": "我不知道，材料里没有相关信息。",
        "reference_doc_idx": None,
    },
]


def create_zhipu_client() -> ZhipuAI:
    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env 里配置 ZHIPUAI_API_KEY")
    return ZhipuAI(api_key=api_key)


def embed_texts(client: ZhipuAI, texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    sorted_data = sorted(resp.data, key=lambda x: x.index)
    return [d.embedding for d in sorted_data]


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
        embeddings=embeddings,
        ids=[f"doc_{i}" for i in range(len(DOCUMENTS))],
    )
    return col


def retrieve(client: ZhipuAI, collection, question: str, top_k: int = 2) -> list[str]:
    query_emb = embed_texts(client, [question])[0]
    results = collection.query(query_embeddings=[query_emb], n_results=top_k)
    return results["documents"][0]


def generate_answer(client: ZhipuAI, question: str, docs: list[str]) -> str:
    context = "\n\n".join(f"【材料{i+1}】{d}" for i, d in enumerate(docs))
    prompt = (
        "你是严谨的问答助手。只根据下面材料回答，材料没有就说'我不知道'，不要编造。\n\n"
        f"【材料】\n{context}\n\n【问题】{question}"
    )
    return chat(client, prompt)


# ════════════════════════════════════════════════════════════
# LLM-as-a-Judge：三个指标
# ════════════════════════════════════════════════════════════
def extract_score(text: str) -> float:
    """从裁判的回答里提取 0~10 的分数。"""
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
    if match:
        score = float(match.group(1))
        return min(max(score, 0), 10)
    return 5.0


def score_context_relevance(client: ZhipuAI, question: str, retrieved_docs: list[str]) -> float:
    """指标①：检索相关性。召回的文档和问题相关吗？"""
    docs_text = "\n".join(f"- {d}" for d in retrieved_docs)
    prompt = (
        "你是严格的评估裁判。请评估下面检索回来的文档，和用户问题的相关性。\n"
        "如果文档能帮助回答问题，给高分；如果文档和问题无关，给低分。\n"
        "请只输出一个 0 到 10 的分数（10 分制），不要其他内容。\n\n"
        f"【用户问题】{question}\n\n【检索到的文档】\n{docs_text}\n\n分数："
    )
    return extract_score(chat(client, prompt))


def score_faithfulness(client: ZhipuAI, answer: str, retrieved_docs: list[str]) -> float:
    """指标②：忠实度。答案有没有基于文档撒谎（幻觉）？"""
    docs_text = "\n".join(f"- {d}" for d in retrieved_docs)
    prompt = (
        "你是严格的评估裁判。请判断下面这个'答案'是否完全基于提供的'文档'。\n"
        "如果答案的每个说法都能在文档里找到依据，给高分（10分）。\n"
        "如果答案编造了文档里没有的内容（幻觉），给低分。\n"
        "如果答案说'我不知道'且文档确实没有相关信息，给高分（诚实拒答是好的）。\n"
        "请只输出一个 0 到 10 的分数，不要其他内容。\n\n"
        f"【文档】\n{docs_text}\n\n【答案】{answer}\n\n分数："
    )
    return extract_score(chat(client, prompt))


def score_answer_relevance(client: ZhipuAI, question: str, answer: str) -> float:
    """指标③：答案相关性。答案有没有回答用户的问题？"""
    prompt = (
        "你是严格的评估裁判。请判断下面这个'答案'是否真正回答了用户的'问题'。\n"
        "如果答案直接回答了问题，给高分（10分）。\n"
        "如果答案答非所问、跑题，给低分。\n"
        "如果问题无法从材料回答，而答案诚实地说了'我不知道'，给中高分（7分）。\n"
        "请只输出一个 0 到 10 的分数，不要其他内容。\n\n"
        f"【用户问题】{question}\n\n【答案】{answer}\n\n分数："
    )
    return extract_score(chat(client, prompt))


def diagnose(ctx_rel: float, faith: float, ans_rel: float) -> str:
    """根据三维分数给出诊断：该优化哪个环节。"""
    issues = []
    if ctx_rel < 7:
        issues.append("检索相关性低→优化检索")
    if faith < 7:
        issues.append("忠实度低→优化生成防幻觉")
    if ans_rel < 7:
        issues.append("答案相关性低→优化生成/query改写")
    if not issues:
        return "各项指标良好"
    return "；".join(issues)


def main():
    print("=" * 60)
    print("Lesson 08 — RAG 评估：怎么知道好不好")
    print("=" * 60)

    client = create_zhipu_client()
    collection = build_kb(client)
    print(f"✅ 知识库已就绪（{collection.count()} 条），评估集 {len(EVAL_SET)} 道题\n")

    results = []
    for i, item in enumerate(EVAL_SET, 1):
        q = item["question"]
        print(f"{'─' * 60}")
        print(f"第 {i} 题：{q}")

        # 跑 RAG
        docs = retrieve(client, collection, q, top_k=2)
        answer = generate_answer(client, q, docs)
        docs_preview = " | ".join(d[:20] for d in docs)
        print(f"  召回文档：{docs_preview}")
        print(f"  答案：{answer[:60]}")

        # 三个指标打分
        ctx_rel = score_context_relevance(client, q, docs)
        faith = score_faithfulness(client, answer, docs)
        ans_rel = score_answer_relevance(client, q, answer)
        diag = diagnose(ctx_rel, faith, ans_rel)

        print(f"  📊 检索相关性={ctx_rel:.1f}  忠实度={faith:.1f}  答案相关性={ans_rel:.1f}")
        print(f"  🔧 诊断：{diag}")
        results.append((q, ctx_rel, faith, ans_rel, diag))

    # 汇总
    print("\n" + "=" * 60)
    print("📊 整体评估汇总（10 分制）")
    print("=" * 60)
    print(f"{'题号':<6}{'检索相关性':<14}{'忠实度':<12}{'答案相关性':<14}")
    for i, (_, cr, f, ar, _) in enumerate(results, 1):
        print(f"  {i:<6}{cr:<14.1f}{f:<12.1f}{ar:<14.1f}")

    avg_cr = sum(r[1] for r in results) / len(results)
    avg_f = sum(r[2] for r in results) / len(results)
    avg_ar = sum(r[3] for r in results) / len(results)
    print(f"\n  平均：检索相关性={avg_cr:.1f}  忠实度={avg_f:.1f}  答案相关性={avg_ar:.1f}")
    print(f"  整体诊断：{diagnose(avg_cr, avg_f, avg_ar)}")

    print("\n" + "=" * 60)
    print("完成！有了这把尺子，优化 RAG 就不再是凭感觉了。")
    print("=" * 60)


if __name__ == "__main__":
    main()
