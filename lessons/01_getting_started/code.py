"""
Lesson 01 — 你的第一个 RAG
============================
本脚本演示一个最简但完整的 RAG（检索增强生成）流程：
    用户提问 → 问题向量化 → 向量库检索相关片段 → 拼接 Prompt → 大模型生成答案

跟着 main() 往下读，每一步都有中文注释。运行方式见同目录 README.md。
"""
# 兼容 Python 3.8：让 list[str] 这种类型注解在旧版本也能正常解析
from __future__ import annotations

# ──────────────────────────────────────────────────────────────
# 兼容旧版 Python（3.8）自带的 sqlite3 版本过低、Chroma 无法启动的问题。
# 如果你用的是 Python 3.9+，这段会自动跳过，无需关心。
# 原理：用 pysqlite3 这个库替换掉标准库的 sqlite3。
# ──────────────────────────────────────────────────────────────
try:
    import pysqlite3
    import sys
    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass  # 没装 pysqlite3 也没关系（Python 3.9+ 自带的 sqlite3 够新）

import os

import chromadb
from dotenv import load_dotenv
from zhipuai import ZhipuAI

# ──────────────────────────────────────────────────────────────
# 常量配置：模型名、检索数量等。初学先不用动这里。
# ──────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "embedding-3"    # 智谱向量模型，默认输出 2048 维向量
CHAT_MODEL = "glm-4"               # 智谱对话模型；想免费可换成 "glm-4-flash"
TOP_K = 5                          # 每次检索返回最相关的几段
COLLECTION_NAME = "acme_handbook"  # Chroma 里这个"集合"的名字
CHROMA_PATH = "./chroma_db"        # Chroma 数据存在本地哪个文件夹

# ──────────────────────────────────────────────────────────────
# 知识库：几条"员工手册"的精简知识。
# 第 1 课先用硬编码（直接写在代码里），方便你增删改做实验。
# （data/sample_docs/employee_handbook.md 是更完整的版本，第 04 课会教怎么加载文件）
# ──────────────────────────────────────────────────────────────
KNOWLEDGE = [
    "ACME 公司实行弹性工作制，标准工作时间为周一至周五 9:00-18:00，午休 12:00-13:00，每天累计工作满 8 小时。每月最后一个周六为全员培训日，需正常出勤。",
    "年假制度：入职满 1 年享有 5 天带薪年假，满 3 年享有 10 天，满 5 年及以上享有 15 天。",
    "病假需提供三甲医院病假条，期间发放基本工资的 60%；事假为无薪假，需提前 1 个工作日 OA 申请并经直属上级审批。",
    "餐饮报销每人每餐不超过 80 元，差旅住宿一线城市不超过 500 元每晚；报销单需在费用发生后 30 个自然日内提交。",
    "经直属上级批准，员工每周可远程办公最多 2 个工作日；试用期员工不适用远程办公政策。",
    "ACME 公司茶水间位于 3 楼东侧，提供免费咖啡和零食，每天 15:00 供应下午茶。",
]

# 要问的问题。运行后可以改这里试不同问题。
# QUESTION = "我在公司干了 4 年，能休几天年假？"
QUESTION = "我在公司干了 4 年，能休几天年假？"


# ════════════════════════════════════════════════════════════
# 第 0 步：准备客户端
# ════════════════════════════════════════════════════════════
def create_zhipu_client() -> ZhipuAI:
    """从 .env 读取 API Key，创建智谱 AI 客户端。"""
    load_dotenv()  # 把 .env 里的变量加载进环境变量
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError(
            "还没配置 API Key！请把 .env.example 复制成 .env，"
            "填入真实的 ZHIPUAI_API_KEY。获取地址：https://bigmodel.cn/"
        )
    return ZhipuAI(api_key=api_key)


# ════════════════════════════════════════════════════════════
# 第 1 步：向量化（Embedding）
# ════════════════════════════════════════════════════════════
def embed_texts(client: ZhipuAI, texts: list[str]) -> list[list[float]]:
    """把若干段文本变成向量。

    返回值是一个列表的列表：每个文本对应一个向量（一串浮点数）。
    语义相近的文本，向量在空间里也离得近——这是后面"检索"能成立的基础。
    """
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    # response.data 里的元素顺序和 input 一一对应；按 index 排好序保证不错位
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]


# ════════════════════════════════════════════════════════════
# 第 2 步：把知识向量化后存进向量库
# ════════════════════════════════════════════════════════════
def build_knowledge_base(client: ZhipuAI):
    """把 KNOWLEDGE 里的每条文本向量化，存进 Chroma 向量库。

    Chroma 是一个本地向量数据库。我们用 PersistentClient 让数据落盘到
    ./chroma_db，下次运行还能复用（本课每次重建，先有个印象即可）。
    """
    # 1) 先算出每条知识的向量
    embeddings = embed_texts(client, KNOWLEDGE)

    # ── 调试：看看 embeddings 长什么样 ──
    print(type(embeddings))              # <class 'list'>
    print(f"共 {len(embeddings)} 条向量，每条维度 = {len(embeddings[0])}")
    print(f"第一条向量前 10 个值：{embeddings[0][:10]}")

    # 2) 建一个 Chroma 集合，把 (文本, 向量, 编号) 存进去
    db = chromadb.PersistentClient(path=CHROMA_PATH)
    # 如果之前跑过，先删掉旧集合，保证每次都是干净的知识库
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
    print(f"✅ 已向量化并存入 {collection.count()} 条知识")
    return collection


# ════════════════════════════════════════════════════════════
# 第 3 步：检索 —— 找出和问题最相关的几段
# ════════════════════════════════════════════════════════════
def retrieve(client: ZhipuAI, collection, question: str, top_k: int = TOP_K) -> list[str]:
    """把问题也变成向量，去 Chroma 里找最接近的 top_k 段文本。"""
    # 问题同样要走 embedding
    query_embedding = embed_texts(client, [question])[0]

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )
    # results["documents"] 是 [[doc1, doc2, ...]]，外层对应每个查询，我们只有一个查询
    retrieved_docs = results["documents"][0]
    return retrieved_docs


# ════════════════════════════════════════════════════════════
# 第 4 步：拼接 Prompt + 调大模型生成答案
# ════════════════════════════════════════════════════════════
def generate_answer(client: ZhipuAI, question: str, context_docs: list[str]) -> str:
    """把检索到的片段拼进提示词，让 GLM 基于这些材料回答。

    注意提示词里的关键约束："只根据提供的材料回答，材料里没有就说不知道"。
    这是压低模型幻觉的核心手段，第 05 课会专门讲。
    """
    # 把多段材料拼成一段，加上编号方便模型引用
    context_text = "\n\n".join(
        f"【材料{i + 1}】{doc}" for i, doc in enumerate(context_docs)
    )

    prompt = (
        f"你是一个严谨的问答助手。请只根据下面提供的材料回答用户问题。"
        f"如果材料里没有相关信息，请直接回答“我不知道”，不要编造。\n\n"
        f"【材料】\n{context_text}\n\n"
        f"【用户问题】{question}"
    )

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ],
    )
    return response.choices[0].message.content


# ════════════════════════════════════════════════════════════
# 主流程：把上面几步串起来
# ════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("Lesson 01 — 你的第一个 RAG")
    print("=" * 60)

    # 0. 准备
    client = create_zhipu_client()

    # 1 & 2. 建知识库（文本 → 向量 → 存 Chroma）
    collection = build_knowledge_base(client)

    # ── 调试：看看 Chroma 里到底存了什么 ──
    all_data = collection.get(include=["embeddings", "documents"])
    print("\n🗄️  Chroma 集合里的所有内容：")
    for i, (doc_id, doc) in enumerate(zip(all_data["ids"], all_data["documents"]), 1):
        print(f"  [{i}] id={doc_id}  text={doc[:30]}...")  # 文本只打前30字
    print(f"  向量维度验证：第一条向量有 {len(all_data['embeddings'][0])} 维")

    # 3. 检索
    print(f"\n🔎 问题：{QUESTION}")
    retrieved = retrieve(client, collection, QUESTION)
    print("\n📚 检索到的材料（模型会基于这些作答）：")
    for i, doc in enumerate(retrieved, 1):
        print(f"  [{i}] {doc}")

    # 4. 生成
    answer = generate_answer(client, QUESTION, retrieved)
    print("\n🤖 模型回答：")
    print(answer)
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
