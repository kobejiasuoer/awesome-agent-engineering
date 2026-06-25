# Lesson 01 — 先跑通：你的第一个 RAG 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让学习者配置好环境、跑通一个完整的 RAG（embedding → 向量检索 → GLM 生成），并在 20 分钟内看到可运行的成果，建立对 RAG 全流程的直观认知。

**Architecture:** 主题选取贴近生活、容易理解的"ACME 公司员工手册问答"。code.py 用线性、带大量中文注释的函数分解，每个函数对应 RAG 流水线的一个环节，让学习者能一步步跟着执行流程走。知识文本硬编码在代码里，方便修改实验。向量库用 Chroma 持久化到本地磁盘。

**Tech Stack:** Python 3.9+、zhipuai SDK（embedding-3 + GLM-4）、chromadb、python-dotenv

---

## 关于 TDD 的适配说明

writing-plans 技能默认采用严格 TDD（先写测试再实现）。但本计划是**学习教程，不是生产软件**——code.py 的价值在于让学习者读懂、跑通，而非被单元测试驱动出来。给一个 50 行教学 demo 套 TDD 反而会让代码更难读，违背学习目的。

因此本计划把"写测试"环节替换为**端到端真实运行验证**：配置好真实 API Key → 运行 code.py → 确认输出符合预期。技能的其他规范（精确路径、完整代码、自查、频繁提交）保留。

---

## 文件结构

本计划创建的文件及职责：

- `D:/workspace/RAG-test/.gitignore` — 忽略 `.env`、`__pycache__`、`chroma_db/` 等
- `D:/workspace/RAG-test/requirements.txt` — 依赖清单
- `D:/workspace/RAG-test/.env.example` — API Key 配置模板
- `D:/workspace/RAG-test/README.md` — 课程总览、学习路径、环境准备
- `D:/workspace/RAG-test/data/sample_docs/employee_handbook.md` — 示例知识文档（员工手册）
- `D:/workspace/RAG-test/lessons/01_getting_started/README.md` — 本课原理讲解
- `D:/workspace/RAG-test/lessons/01_getting_started/code.py` — 可运行 RAG 代码（核心）
- `D:/workspace/RAG-test/lessons/01_getting_started/exercise.md` — 小练习 + 思考题

**职责边界**：`data/sample_docs/employee_handbook.md` 是"原料文档"，code.py 里另有几条**硬编码的精简知识**（为了让第 1 课足够简单、不用先学文件加载），两者并存。后续 Lesson 04 会教如何把 md 文件加载切块。

---

## Task 1: 初始化 Git 仓库与项目骨架

**Files:**
- Create: `D:/workspace/RAG-test/.gitignore`
- Create: `D:/workspace/RAG-test/requirements.txt`
- Create: `D:/workspace/RAG-test/.env.example`

- [ ] **Step 1: 初始化 git 仓库**

Run:
```bash
cd D:/workspace/RAG-test
git init
```
Expected: 输出 `Initialized empty Git repository in D:/workspace/RAG-test/.git/`

- [ ] **Step 2: 创建 .gitignore**

写入 `D:/workspace/RAG-test/.gitignore`：

```gitignore
# 敏感配置（千万别提交真实的 API Key）
.env

# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/

# Chroma 本地持久化数据（每台机器自己生成）
chroma_db/

# 系统/编辑器
.DS_Store
.idea/
.vscode/
```

- [ ] **Step 3: 创建 requirements.txt**

写入 `D:/workspace/RAG-test/requirements.txt`：

```txt
zhipuai>=2.1.0
chromadb>=0.5.0
python-dotenv>=1.0.0
```

- [ ] **Step 4: 创建 .env.example**

写入 `D:/workspace/RAG-test/.env.example`：

```env
# 把这一行的 xxx 换成你的真实 Key，然后把文件改名为 .env
# Key 获取：https://bigmodel.cn/ 登录后 → 控制台 → API Keys
ZHIPUAI_API_KEY=xxxxxxxx.xxxxxxxx
```

- [ ] **Step 5: 提交**

```bash
cd D:/workspace/RAG-test
git add .gitignore requirements.txt .env.example docs/
git commit -m "chore: 初始化项目骨架与设计文档"
```

---

## Task 2: 创建示例知识文档

**Files:**
- Create: `D:/workspace/RAG-test/data/sample_docs/employee_handbook.md`

- [ ] **Step 1: 创建员工手册文档**

写入 `D:/workspace/RAG-test/data/sample_docs/employee_handbook.md`：

```markdown
# ACME 公司员工手册（示例文档）

本手册仅用于 RAG 学习演示，内容为虚构。

## 1. 工作时间
公司实行弹性工作制，标准工作时间为每周一至周五，每天 9:00-18:00，
其中 12:00-13:00 为午休时间。员工需在每个工作日累计工作满 8 小时。
每月最后一个周六为全员培训日，需正常出勤。

## 2. 请假制度
- 年假：入职满 1 年享有 5 天带薪年假，满 3 年享有 10 天，满 5 年及以上享有 15 天。
- 病假：需提供三甲医院开具的病假条，病假期间发放基本工资的 60%。
- 事假：事假为无薪假，需提前 1 个工作日在 OA 系统提交申请，经直属上级审批。
- 婚假：依法登记结婚的员工享有 3 天带薪婚假。

## 3. 报销流程
员工因公产生的差旅、餐饮、办公用品等费用可申请报销。
流程为：保留原始发票 → 登录 OA 系统填写报销单 → 直属上级审批 → 财务复核 → 打款。
餐饮报销标准为每人每餐不超过 80 元，差旅住宿标准为一线城市不超过 500 元/晚。
报销单需在费用发生后的 30 个自然日内提交，逾期不予受理。

## 4. 远程办公
经直属上级批准，员工每周可申请最多 2 个工作日远程办公。
远程办公期间需保持通讯畅通，正常响应工作消息。
试用期员工不适用远程办公政策。

## 5. 福利体系
- 补充商业医疗保险（覆盖员工本人及一名直系亲属）。
- 生日福利：200 元生日礼金。
- 年度体检：每年一次全员免费体检。
- 节日福利：春节、中秋等法定节日发放节日礼品。
```

- [ ] **Step 2: 提交**

```bash
cd D:/workspace/RAG-test
git add data/sample_docs/employee_handbook.md
git commit -m "docs: 添加示例员工手册文档"
```

---

## Task 3: 编写 Lesson 01 原理讲解 README

**Files:**
- Create: `D:/workspace/RAG-test/lessons/01_getting_started/README.md`

- [ ] **Step 1: 创建课程目录并编写 README**

写入 `D:/workspace/RAG-test/lessons/01_getting_started/README.md`：

````markdown
# Lesson 01 — 先跑通：你的第一个 RAG

> 本课目标：**20 分钟内跑通一个完整的 RAG**，先看到效果，建立全局认知。理论细节后面的课再深入。

---

## 1. RAG 到底在解决什么问题？

直接问大模型（比如 GLM-4）会有三个痛点：

| 痛点 | 例子 |
|------|------|
| **幻觉** | 它会一本正经地编造不存在的"事实" |
| **知识截止** | 它的训练数据有截止日期，不知道最近的事 |
| **不知道你的私有数据** | 它不知道你们公司的请假制度、你的产品文档 |

RAG（Retrieval-Augmented Generation，检索增强生成）的思路很朴素：
**回答之前，先去你的文档库里"检索"相关片段，把片段塞进提问里，让模型基于真实材料作答。**

> 💡 一个类比：闭卷考试 vs 开卷考试。直接问大模型 = 闭卷（靠记忆，可能记错）；RAG = 开卷（允许翻书，答案更靠谱）。

---

## 2. RAG 的完整流水线

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐     ┌──────────┐
│  用户提问    │ ──▶ │  问题向量化   │ ──▶ │  向量检索    │ ──▶ │  拼接 Prompt  │ ──▶ │ 大模型生成│
│ "年假几天？" │     │  (Embedding)  │     │  Top-K 片段  │     │  上下文+问题  │     │   答案    │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘     └──────────┘
                                                ▲
                                                │ 从这里取
                                    ┌───────────────────────┐
                                    │ 你的文档 → 向量化 → 存储 │  （提前做好，存进向量库）
                                    └───────────────────────┘
```

一句话概括：**把"问题"和"文档"都变成向量，算谁和谁更近，把最近的几段喂给大模型。**

---

## 3. 三个核心概念（先有个印象，后面课会深讲）

- **Embedding（向量嵌入）**：把一段文字变成一串数字（向量）。语义相近的文字，向量也相近。这是让计算机"理解"文字相似度的方法。
- **向量检索**：在所有文档向量里，找出和"问题向量"最接近的 K 个（Top-K）。本课用 **Chroma** 这个向量库来做。
- **Prompt 拼接**：把检索到的文档片段 + 用户问题，按固定格式拼成一段提示词，交给大模型生成答案。

---

## 4. 本课代码在做什么

打开同目录的 `code.py`，你会发现它被拆成了几个函数，每个函数对应流水线的一个环节：

| 函数 | 对应环节 | 干什么 |
|------|----------|--------|
| `create_zhipu_client()` | 准备 | 用 API Key 初始化智谱客户端 |
| `embed_texts()` | 向量化 | 调 embedding-3 把文本变成向量 |
| `build_knowledge_base()` | 存储 | 把知识文本向量化后存进 Chroma |
| `retrieve()` | 检索 | 把问题向量化，从 Chroma 捞最相关的 K 段 |
| `generate_answer()` | 生成 | 把检索结果拼进 prompt，调 GLM-4 生成答案 |
| `main()` | 串联 | 把上面几步串起来跑一遍 |

**重点观察**：运行时程序会打印出**"检索到了哪些片段"**和**"模型最终回答"**。这是理解 RAG 的关键——你能亲眼看到模型"看到了什么材料"才作答。

---

## 5. 跑起来

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置密钥（把 .env.example 复制成 .env，填入你的 Key）
cp .env.example .env
# 然后编辑 .env，把 ZHIPUAI_API_KEY 换成真实值

# 3. 运行
python lessons/01_getting_started/code.py
```

跑通后，试着改 `code.py` 里的 `QUESTION`，或增删 `KNOWLEDGE` 列表里的内容，看模型回答怎么变。

> 💰 **省钱提示**：智谱的 `glm-4-flash` 模型是免费的。如果想零成本试，可把代码里 `model="glm-4"` 改成 `model="glm-4-flash"`，效果略弱但不花钱。

---

下一课 [Lesson 02 — 深入 Embedding](../02_embedding/) 我们再拆开讲"向量到底怎么表示语义"。
````

- [ ] **Step 2: 提交**

```bash
cd D:/workspace/RAG-test
git add lessons/01_getting_started/README.md
git commit -m "docs(lesson01): 添加原理讲解 README"
```

---

## Task 4: 编写 Lesson 01 核心代码 code.py

**Files:**
- Create: `D:/workspace/RAG-test/lessons/01_getting_started/code.py`

- [ ] **Step 1: 编写完整可运行的 code.py**

写入 `D:/workspace/RAG-test/lessons/01_getting_started/code.py`：

```python
"""
Lesson 01 — 你的第一个 RAG
============================
本脚本演示一个最简但完整的 RAG（检索增强生成）流程：
    用户提问 → 问题向量化 → 向量库检索相关片段 → 拼接 Prompt → 大模型生成答案

跟着 main() 往下读，每一步都有中文注释。运行方式见同目录 README.md。
"""

import os

import chromadb
from dotenv import load_dotenv
from zhipuai import ZhipuAI

# ──────────────────────────────────────────────────────────────
# 常量配置：模型名、检索数量等。初学先不用动这里。
# ──────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "embedding-3"   # 智谱向量模型，默认输出 2048 维向量
CHAT_MODEL = "glm-4"              # 智谱对话模型；想免费可换成 "glm-4-flash"
TOP_K = 2                         # 每次检索返回最相关的几段
COLLECTION_NAME = "acme_handbook" # Chroma 里这个"集合"的名字
CHROMA_PATH = "./chroma_db"       # Chroma 数据存在本地哪个文件夹

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
]

# 要问的问题。运行后可以改这里试不同问题。
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
        f"如果材料里没有相关信息，请直接回答"我不知道"，不要编造。\n\n"
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
```

- [ ] **Step 2: 提交**

```bash
cd D:/workspace/RAG-test
git add lessons/01_getting_started/code.py
git commit -m "feat(lesson01): 添加第一个可运行的 RAG 代码"
```

---

## Task 5: 编写练习 exercise.md

**Files:**
- Create: `D:/workspace/RAG-test/lessons/01_getting_started/exercise.md`

- [ ] **Step 1: 编写 exercise.md**

写入 `D:/workspace/RAG-test/lessons/01_getting_started/exercise.md`：

```markdown
# Lesson 01 练习

> 改 `code.py` 里对应的代码，运行 `python lessons/01_getting_started/code.py` 观察变化。
> 没有标准答案，重点是建立"改动→观察→理解"的直觉。

---

## 练习 1：换一个问题（热身）
把 `QUESTION` 改成下面这些，逐个运行，观察检索到的材料和回答：

- `"公司中午能休息多久？"`
- `"我生病了怎么请假？"`
- `"请告诉我公司的 wifi 密码"` ← 文档里没有的信息

**观察重点**：第三个问题，模型应该回答"我不知道"。这正是提示词里"没有就说不知道"在起作用。

---

## 练习 2：增删知识
在 `KNOWLEDGE` 列表里加一条新知识，比如：

```python
"ACME 公司茶水间位于 3 楼东侧，提供免费咖啡和零食，每天 15:00 供应下午茶。",
```

然后问 `"下午茶几点？"`，看模型能不能答对。

再把这条**删掉**，问同样的问题，看模型这次回答什么（应该回到"我不知道"）。

**思考**：这说明 RAG 的回答质量本质上取决于什么？

---

## 练习 3：调检索数量
把 `TOP_K` 从 2 改成 4（甚至 5），再问 `"我在公司干了 4 年，能休几天年假？"`。

**观察**：检索到的材料变多了，回答有没有变得更好？还是混入了无关内容？

**思考**：Top-K 是不是越大越好？(提示：后面 Lesson 03 会讲)

---

## 练习 4：对比"不开 RAG"
临时把 `generate_answer` 里的 prompt 换成**只发问题、不给材料**：

```python
prompt = QUESTION  # 直接问，不给任何材料
```

同样问 `"我在公司干了 4 年，能休几天年假？"`，对比有材料和无材料的回答差异。

**思考**：没有材料时，模型会怎么回答？(提示：它可能会编，因为它不知道"ACME 公司"的真实制度)

---

## ✅ 完成本课后，你应该能回答
1. RAG 解决了直接问大模型的哪三个问题？
2. 完整的 RAG 流水线有哪几步？每步分别用什么技术？
3. 为什么"检索"这一步能让模型少产生幻觉？
```

- [ ] **Step 2: 提交**

```bash
cd D:/workspace/RAG-test
git add lessons/01_getting_started/exercise.md
git commit -m "docs(lesson01): 添加课后练习"
```

---

## Task 6: 端到端运行验证

这一步需要真实的智谱 API Key。如果当前环境无法联网调用智谱 API，则跳过实际运行，但需在交付说明里标注"待用户配置 Key 后验证"。

- [ ] **Step 1: 安装依赖**

Run:
```bash
cd D:/workspace/RAG-test
pip install -r requirements.txt
```
Expected: 成功安装 zhipuai、chromadb、python-dotenv 及其依赖，无报错。

- [ ] **Step 2: 配置 API Key**

若工作区存在 `.env`（含真实 Key），跳过；否则提示用户配置：
```bash
cp .env.example .env
# 编辑 .env 填入真实 ZHIPUAI_API_KEY
```

- [ ] **Step 3: 运行 code.py**

Run:
```bash
cd D:/workspace/RAG-test
python lessons/01_getting_started/code.py
```
Expected output（结构大致如下，具体向量/文字会变）：
```
============================================================
Lesson 01 — 你的第一个 RAG
============================================================
✅ 已向量化并存入 5 条知识

🔎 问题：我在公司干了 4 年，能休几天年假？

📚 检索到的材料（模型会基于这些作答）：
  [1] 年假制度：入职满 1 年享有 5 天带薪年假，满 3 年享有 10 天，满 5 年及以上享有 15 天。
  [2] ...（另一段相关材料）

🤖 模型回答：
根据材料，入职满 3 年享有 10 天带薪年假，满 5 年及以上才有 15 天。
你目前工作 4 年，处于满 3 年不满 5 年之间，因此享有 10 天带薪年假。
============================================================
```

- [ ] **Step 4: 验证"无答案"场景**

把 `QUESTION` 临时改为 `"公司的 wifi 密码是多少？"`，重新运行。
Expected: 模型回答"我不知道"或类似拒绝表述（因为材料里没有）。

- [ ] **Step 5: 若运行失败，按以下排查**

- `RuntimeError: 还没配置 API Key` → `.env` 未创建或 Key 未填
- `openai.APIConnectionError` / 超时 → 网络问题，检查能否访问 `open.bigmodel.cn`
- `Chroma 相关报错` → 删除 `./chroma_db` 文件夹后重试

- [ ] **Step 6: 最终提交（若有改动）**

```bash
cd D:/workspace/RAG-test
git add -A
git commit -m "chore(lesson01): 完成端到端验证" --allow-empty
```

---

## 完成标准

Lesson 01 完成的标志：
1. ✅ `code.py` 能跑通，打印出检索材料 + 模型回答
2. ✅ README 讲清了 RAG 流水线和本课代码结构
3. ✅ exercise.md 提供了至少 4 个有引导的练习
4. ✅ 学习者按 README 能在 20 分钟内独立跑起来
```

现在做计划自查。我已确认代码关键 API 写法（`client.embeddings.create`、`client.chat.completions.create`、Chroma `PersistentClient`/`query`）均符合官方文档，类型与函数名在各 Task 间一致（`embed_texts`、`build_knowledge_base`、`retrieve`、`generate_answer` 在 Task 4 定义、Task 6 验证中引用一致），无占位符，spec 中 Lesson 01 的要求（硬编码知识、top-k、拼 prompt、打印检索片段+回答）均有对应任务。

一个细节我要修正：code.py 里的 prompt 字符串使用了中文引号 `"我不知道"`，这在 f-string 里和外层双引号冲突。让我检查 —— 外层是 `f"..."` 双引号，里面 `"我不知道"` 是中文全角引号 `""`，不冲突。✓ 没问题。

计划完成。现在交付。

## 计划完成 ✅

实现计划已写好并保存到：`docs/superpowers/plans/2026-06-25-lesson01-getting-started.md`

**计划要点**：
- 共 6 个任务：git 初始化与骨架 → 示例文档 → 原理 README → 核心 code.py → 练习 → 端到端验证
- 主题是贴近生活的 **"ACME 公司员工手册问答"**（请假/报销/作息），容易理解、好设计问题
- code.py 拆成 6 个对应流水线的函数（准备/向量化/存库/检索/生成/串联），每个都有详细中文注释
- 用真实 API（智谱 embedding-3 + GLM-4）验证能跑通，含省钱提示（可换 glm-4-flash）
- 一个适配说明：教程性质，用端到端运行验证替代严格 TDD，避免让教学代码变难读

**注意**：Task 6（端到端验证）需要你的真实智谱 API Key 才能真正跑通。如果你现在有 Key，我可以在写完后直接帮你验证；如果没有，我会把代码写好、标注"待你配置 Key 后运行验证"。

Sources:
- [Embedding-3 - 智谱AI开放文档](https://docs.bigmodel.cn/cn/guide/models/embedding/embedding-3)
- [zhipuai-sdk-python-v4 issue #7](https://github.com/MetaGLM/zhipuai-sdk-python-v4/issues/7)

---

接下来怎么执行，有两种方式：