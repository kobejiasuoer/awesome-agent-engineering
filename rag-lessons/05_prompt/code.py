"""
Lesson 05 — Prompt 工程：把检索结果喂给大模型
=============================================
本脚本做三个对比实验，让你看清 prompt 设计如何影响 RAG 答案质量：
    ① 防幻觉对比：无约束 prompt vs 防幻觉 prompt（同一问题，结果天差地别）
    ② 引用溯源：要求模型标注答案来自哪条材料
    ③ 流式输出：边生成边打印，体验真实产品效果

运行：python lessons/05_prompt/code.py
"""
from __future__ import annotations

import os

import chromadb
from dotenv import load_dotenv
from zhipuai import ZhipuAI

EMBEDDING_MODEL = "embedding-3"
CHAT_MODEL = "glm-4"  # 想免费可换成 "glm-4-flash"
COLLECTION_NAME = "lesson05_kb"
CHROMA_PATH = "./chroma_db_05"

# ──────────────────────────────────────────────────────────────
# 知识库（和第 1 课类似，但稍丰富一些，方便演示引用溯源）
# ──────────────────────────────────────────────────────────────
KNOWLEDGE = [
    "年假：入职满 1 年有 5 天带薪年假，满 3 年有 10 天，满 5 年有 15 天。未休完的年假可在次年第一季度补休。",
    "病假需提供三甲医院病假条，期间发基本工资的 60%。连续病假超过 3 天需提供住院证明。",
    "餐饮报销每人每餐不超过 80 元，差旅住宿一线城市不超过 500 元每晚。报销单需 30 天内提交。",
    "每周可远程办公最多 2 个工作日，需直属上级批准。试用期员工不适用远程办公。",
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


def build_knowledge_base(client: ZhipuAI):
    """建向量库（和第 1 课一样的流程）。"""
    embeddings = embed_texts(client, KNOWLEDGE)
    db = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        db.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = db.get_or_create_collection(name=COLLECTION_NAME)
    collection.add(
        documents=KNOWLEDGE,
        embeddings=embeddings,
        ids=[f"doc_{i}" for i in range(len(KNOWLEDGE))],
    )
    return collection


def retrieve(client: ZhipuAI, collection, question: str, top_k: int = 2) -> list[str]:
    query_emb = embed_texts(client, [question])[0]
    results = collection.query(query_embeddings=[query_emb], n_results=top_k)
    return results["documents"][0]


def chat(client: ZhipuAI, prompt: str) -> str:
    """调 GLM 生成（非流式）。"""
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def chat_stream(client: ZhipuAI, prompt: str):
    """调 GLM 流式生成：边生成边 yield 文本片段。"""
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    for chunk in resp:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ════════════════════════════════════════════════════════════
# 实验①：防幻觉对比（最核心）
# ════════════════════════════════════════════════════════════
def build_naive_prompt(question: str, docs: list[str]) -> str:
    """无约束 prompt：只给材料+问题，不加任何约束。"""
    context = "\n\n".join(docs)
    return f"材料：\n{context}\n\n问题：{question}"


def build_safe_prompt(question: str, docs: list[str]) -> str:
    """防幻觉 prompt：明确限定只能依据材料，没有就说不知道。"""
    context = "\n\n".join(f"【材料{i+1}】{doc}" for i, doc in enumerate(docs))
    return (
        "你是一个严谨的问答助手。请遵守以下规则：\n"
        "1. 只能根据下面提供的材料回答问题，不要使用材料以外的知识。\n"
        "2. 如果材料里没有相关信息，请直接回答'我不知道'，不要编造。\n"
        "3. 如果多条材料冲突，请指出冲突。\n\n"
        f"【材料】\n{context}\n\n"
        f"【问题】{question}"
    )


def section_anti_hallucination(client, collection):
    """第①部分：用文档里没有的问题，对比两种 prompt。"""
    print("\n" + "═" * 60)
    print("① 防幻觉对比（用一个文档里没有的问题）")
    print("═" * 60)

    # 注意：这个问题的答案不在 KNOWLEDGE 里
    out_of_scope = "公司的 wifi 密码是多少？茶水间在哪一层？"
    # 但为了演示，我们还是检索一下（会返回最不相关的几条）
    docs = retrieve(client, collection, out_of_scope, top_k=2)
    print(f"\n问题：{out_of_scope}")
    print(f"（检索回的材料其实和 wifi 毫无关系）：")
    for i, d in enumerate(docs, 1):
        print(f"  [{i}] {d}")

    # 无约束 prompt
    print("\n【无约束 prompt】（直接发材料+问题，不加约束）：")
    naive_answer = chat(client, build_naive_prompt(out_of_scope, docs))
    print(f"  → {naive_answer}")

    # 防幻觉 prompt
    print("\n【防幻觉 prompt】（限定只依据材料，没有就说不知道）：")
    safe_answer = chat(client, build_safe_prompt(out_of_scope, docs))
    print(f"  → {safe_answer}")

    print("\n👉 观察：无约束时模型可能会瞎编一个 wifi 密码；")
    print("   防幻觉时模型应该老实地回答'我不知道'。这就是约束的力量。")


# ════════════════════════════════════════════════════════════
# 实验②：引用溯源
# ════════════════════════════════════════════════════════════
def section_citation(client, collection):
    """第②部分：要求模型在答案里标注引用来源。"""
    print("\n" + "═" * 60)
    print("② 引用溯源（要求标注答案来自哪条材料）")
    print("═" * 60)

    question = "我工作 4 年了，能休几天年假？报销截止日期是多久？"
    docs = retrieve(client, collection, question, top_k=3)
    print(f"\n问题：{question}")

    context = "\n\n".join(f"【材料{i+1}】{doc}" for i, doc in enumerate(docs))
    prompt = (
        "你是一个严谨的问答助手。请根据下面材料回答问题，并遵守：\n"
        "1. 只依据材料回答，材料没有就说不知道。\n"
        "2. 在答案中用【材料N】标注每条信息来自哪条材料。\n"
        "3. 分点陈述。\n\n"
        f"【材料】\n{context}\n\n"
        f"【问题】{question}"
    )
    answer = chat(client, prompt)
    print(f"\n🤖 模型回答：\n{answer}")
    print("\n👉 观察：答案里应该出现【材料1】【材料2】这样的标注，方便核对来源。")


# ════════════════════════════════════════════════════════════
# 实验③：流式输出
# ════════════════════════════════════════════════════════════
def section_streaming(client, collection):
    """第③部分：流式生成，边生成边打印。"""
    print("\n" + "═" * 60)
    print("③ 流式输出（边生成边打印，打字机效果）")
    print("═" * 60)

    question = "请详细说明公司的年假和报销制度。"
    docs = retrieve(client, collection, question, top_k=3)
    context = "\n\n".join(f"【材料{i+1}】{doc}" for i, doc in enumerate(docs))
    prompt = (
        "你是严谨的问答助手，只依据下面材料回答，没有就说不知道。\n"
        "请详细、分点地回答。\n\n"
        f"【材料】\n{context}\n\n"
        f"【问题】{question}"
    )

    print(f"\n问题：{question}")
    print("\n🤖 模型回答（流式）：")
    for piece in chat_stream(client, prompt):
        print(piece, end="", flush=True)  # end="" 不换行，flush=True 立即显示
    print()  # 最后补一个换行
    print("\n👉 观察：流式输出让用户不用等整段生成完才看到结果，体验更好。")
    print("   生产环境（网页/App）几乎都用流式，提升感知速度。")


def main():
    print("=" * 60)
    print("Lesson 05 — Prompt 工程：把检索结果喂给大模型")
    print("=" * 60)

    client = create_zhipu_client()
    collection = build_knowledge_base(client)
    print(f"✅ 知识库已就绪（{collection.count()} 条知识）")

    # ① 防幻觉对比
    section_anti_hallucination(client, collection)

    # ② 引用溯源
    section_citation(client, collection)

    # ③ 流式输出
    section_streaming(client, collection)

    print("\n" + "=" * 60)
    print("完成！核心要点：用明确的指令约束模型，'我不知道'比错误答案有价值。")
    print("=" * 60)


if __name__ == "__main__":
    main()
