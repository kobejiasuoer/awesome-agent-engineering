# RAG 渐进式学习课程 📚

这是一套**从零开始、系统理解 RAG（检索增强生成）原理**的实战课程。
面向**会 Python 但没接触过大模型**的开发者，用可运行的代码 + 原理讲解，一步步带你搞懂 RAG。

> 技术栈：智谱 GLM-4 + embedding-3 · Chroma 本地向量库 · Python

---

## 🗺️ 学习路径（共 9 节课）

按 RAG 真实数据流顺序，每课加一个环节：

| # | 课程 | 你会学到 |
|---|------|----------|
| 01 | [先跑通：你的第一个 RAG](lessons/01_getting_started/) | 跑通完整流水线，建立全局认知 |
| 02 | 深入 Embedding | 向量如何表示语义、余弦相似度 |
| 03 | 向量检索 | Top-K、ANN、Chroma 用法 |
| 04 | 文档切块 (Chunking) | chunk_size/overlap 的取舍 |
| 05 | Prompt 工程 | 防幻觉提示词、引用溯源 |
| 06 | 进阶检索 | 混合检索 + Rerank 重排序 |
| 07 | Query 改写 | HyDE、多查询展开 |
| 08 | RAG 评估 | RAGAS 三维指标 |
| 09 | 工程化 | 流式、缓存、多文档 |

> 目前已完成 **Lesson 01**。后续课程会根据你的反馈逐课制作。

---

## 🚀 快速开始（5 步）

```bash
# 1. 确保有 Python 3.9+
python --version

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env，把 ZHIPUAI_API_KEY 换成你的真实 Key
# Key 获取：https://bigmodel.cn/ → 控制台 → API Keys

# 4. 跑第一课
python lessons/01_getting_started/code.py

# 5. 看着输出，去 lessons/01_getting_started/README.md 学原理
```

跑通后，打开 [Lesson 01 的练习](lessons/01_getting_started/exercise.md) 动手改改代码。

---

## 📁 目录结构

```
RAG-test/
├── README.md                  ← 你在这里：课程总览
├── requirements.txt           ← 依赖
├── .env.example               ← API Key 配置模板
├── data/sample_docs/          ← 练习用的示例文档
├── lessons/                   ← 各课时（每课一个目录）
│   └── 01_getting_started/
│       ├── README.md          ← 原理讲解
│       ├── code.py            ← 可运行代码
│       └── exercise.md        ← 练习
└── docs/                      ← 设计文档与实现计划
```

每节课固定三件套：**①原理 README（讲 why 和取舍）+ ②可运行 code.py（带详细中文注释）+ ③练习**。

---

## 💡 学习建议

- **一定要跑代码**，不要只看。RAG 的很多直觉来自亲手改参数、看输出变化。
- 按顺序学，每课建立在前一课之上。
- 卡住了随时问我（你的 AI 助手），把报错贴给我。
