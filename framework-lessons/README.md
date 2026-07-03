# 框架进阶课程 🔧（LangChain + LangGraph）

这是一套**面向求职/转岗 AI 应用开发**的框架进阶课程。

> **前置**：已学完 [RAG 课程](../lessons/)（9 课）+ [Agent 课程](../agent-lessons/)（9 课），已手写过 RAG 与 Agent 的每一个环节。
>
> **本课程定位**：你已经懂原理，现在用工业界主流框架（LangChain / LangGraph，JD 高频词）把**手写能力翻译成工程化代码**。每课都做「**你手写过的版本 vs 框架版本**」并排对比——这是本课程区别于市面所有框架教程的杀手锏。

---

## 🎯 为什么学这门课？

- **JD 高频词**：LangChain / LangGraph 是 AI 应用开发岗最常出现的框架
- **认知深度**：能说清「框架替你做了什么、隐藏了什么、何时该绕回手写」——高级候选人才答得上
- **简历作品**：L09 用 LangGraph 重做研究助手，图结构、可部署、可演示

> 💡 **核心技术认知**：你已经手写过每个环节，学框架不是"背 API"，而是"给原理找现成的家"。

---

## 🗺️ 学习路径（共 9 节课，两段式）

### 第一段：LangChain — RAG 工程化（L01-L05）

| # | 课程 | 对应你的手写课 |
|---|------|---------------|
| 01 | [LCEL 与框架全景](01_lcel_overview/) | RAG L01（第一个 RAG）|
| 02 | [Models + Prompts + Output Parsers](02_models_prompts_parsers/) | RAG L05、Agent L02 |
| 03 | [Loaders + Splitters + VectorStores](03_documents_splitter_vectorstore/) | RAG L03、L04 |
| 04 | Retrievers + RAG Chain（即将推出）| RAG L01-L05 |
| 05 | 高级检索工程化（即将推出）| RAG L06、L07 |

### 第二段：LangGraph — Agent 工程化（L06-L09）

| # | 课程 | 对应你的手写课 |
|---|------|---------------|
| 06 | StateGraph 重写 ReAct（即将推出）| Agent L03 |
| 07 | @tool 工具 + 预置 Agent（即将推出）| Agent L02、L04 |
| 08 | 状态持久化 + 人机协作（即将推出）| Agent L05 |
| 09 | 毕业项目：LangGraph 研究助手（即将推出）| Agent L09、L07 |

> 目前已完成 **3 / 9** 节课。每课包含原理讲解 + 可运行代码 + 练习。

---

## 🚀 快速开始

与前两门课共用环境，如果你已跑通过 RAG / Agent 课程，直接开始：

```bash
# 1. 安装框架进阶依赖（第一次需要）
pip install -r requirements.txt

# 2. 确认 .env 里有智谱 API Key（已配好）

# 3. 跑第一课
python framework-lessons/01_lcel_overview/code.py
```

> 💰 **省钱**：代码里 `CHAT_MODEL = "glm-4"` 可改成 `"glm-4-flash"`（免费）。

---

## 📁 目录结构

```
RAG-test/
├── lessons/              ← RAG 手写课程（已完成）
├── agent-lessons/        ← Agent 手写课程（已完成）
├── framework-lessons/    ← 框架进阶课程（你在这里）
│   ├── README.md         ← 课程总览
│   └── 01_lcel_overview/
│       ├── README.md     ← 原理 + 映射对比
│       ├── code.py       ← 可运行代码（LCEL 重写 RAG）
│       └── exercise.md   ← 练习
├── data/ .env requirements.txt  ← 三门课共用
└── docs/                 ← 设计文档
```

---

## 💡 学习建议

- **每课都先回看对应的手写课**：对比着学，效果翻倍
- **重点理解数据流**：LCEL 链里每一步的输入输出类型是核心
- **求职重点**：L01（LCEL）、L06（StateGraph）、L09（毕业项目）是面试和简历核心
- 别被框架的"省事"迷惑——原理（embedding、检索、ReAct）一点没变，框架只是封装

---

## 📚 技术版本

本课程基于 **LangChain 1.x**（2025 重构后）：
- `langchain` 1.3.x / `langchain-core` 0.3.x+ / `langgraph` 1.2.x
- 智谱集成：`langchain-community` 的 `ChatZhipuAI` / `ZhipuAIEmbeddings`
- Chroma：独立包 `langchain-chroma`

> ⚠️ `langchain-community` 正在被 sunset（官方拆分为独立集成包），本课程 L01 README 专门讲了背景。未来智谱会有独立包 `langchain-zhipuai`，届时改 import 路径即可。
