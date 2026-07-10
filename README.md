# LLM 应用实战课程 📚

这是一套**从零开始、系统掌握大模型应用开发**的实战课程，覆盖 **RAG、Agent、框架工程化、多智能体编排** 四大方向。
面向**会 Python 但刚接触大模型**的开发者，用可运行的代码 + 原理讲解，一步步从原理手写到框架落地，再到多 Agent 协作架构。

> 技术栈：智谱 GLM-4 + embedding-3 · Chroma 本地向量库 · LangChain + LangGraph · CrewAI · AutoGen · Python

---

## 🗺️ 四门课程总览

本工作区包含**四门递进课程**，建议按顺序学：

| 课程 | 内容 | 状态 |
|------|------|------|
| 📘 [RAG 手写课程](rag-lessons/) | 从零系统理解 RAG 原理（embedding→检索→切块→prompt→混合检索→改写→评估→工程化）| ✅ 9/9 完成 |
| 🤖 [Agent 手写课程](agent-lessons/) | 从零系统理解 AI Agent 原理（Function Calling→ReAct→工具设计→记忆→规划→Agentic RAG→多智能体→毕业项目）| ✅ 9/9 完成 |
| 🔧 [框架进阶课程](framework-lessons/) | LangChain + LangGraph 工程化（把手写原理翻译成框架，每课做"手写版 vs 框架版"对比）| ✅ 9/9 完成 |
| 🔀 [工作流与多智能体编排](workflow-lessons/) | 多 Agent 协作架构（supervisor/swarm/子图/并行/共享态/多模型，三框架横向对比）| ✅ 9/9 完成 |

> **学习路径**：先学 RAG（懂检索原理）→ 再学 Agent（懂自主决策）→ 再学框架进阶（工程化落地）→ 最后学多智能体编排（架构师进阶）。

---

## 🚀 生产级作品集项目

学完 36 课后，把所学能力缝合成**真正可上生产的 AI 应用**：

| 项目 | 内容 | 状态 |
|------|------|------|
| 🔬 [AI 研究分析助手](portfolio-projects/research-assistant/) | 多智能体并行研究系统：真实联网搜索 + 审稿回路 + 多模型降本 + SSE 流式 + SqliteSaver 持久化 + FastAPI 服务化 + Docker 部署。由 workflow L09 教学原型演进，补齐 8 个生产缺口。| ✅ 完成 |

> 这是课程能力的**生产级落地**——不是 demo，是能直接部署、能扛真实流量的 AI 应用服务。

---

## 📚 课程一：RAG 手写课程（共 9 节课）

按 RAG 真实数据流顺序，每课加一个环节：

| # | 课程 | 你会学到 |
|---|------|----------|
| 01 | [先跑通：你的第一个 RAG](rag-lessons/01_getting_started/) | 跑通完整流水线，建立全局认知 |
| 02 | [深入 Embedding](rag-lessons/02_embedding/) | 向量如何表示语义、余弦相似度 |
| 03 | [向量检索](rag-lessons/03_retrieval/) | Top-K、ANN、Chroma 用法 |
| 04 | [文档切块 (Chunking)](rag-lessons/04_chunking/) | chunk_size/overlap 的取舍 |
| 05 | [Prompt 工程](rag-lessons/05_prompt/) | 防幻觉提示词、引用溯源 |
| 06 | [进阶检索](rag-lessons/06_advanced_retrieval/) | 混合检索 + Rerank 重排序 |
| 07 | [Query 改写](rag-lessons/07_query_rewrite/) | HyDE、多查询展开 |
| 08 | [RAG 评估](rag-lessons/08_evaluation/) | RAGAS 三维指标 |
| 09 | [工程化：毕业作品](rag-lessons/09_engineering/) | 交互式问答助手，集成全部技术 |

> 已完成全部 **9 节课** 🎉。每课都包含原理讲解 + 可运行代码 + 练习。

---

## 🤖 课程二：Agent 手写课程（共 9 节课）

按 Agent 能力层层叠加，每课给 Agent 加一项能力（工具→循环→记忆→规划→协作）：

| # | 课程 | 你会学到 |
|---|------|----------|
| 01 | [认识 Agent：从问答到行动](agent-lessons/01_what_is_agent/) | 跑通最小 Agent，建立"LLM + 工具 + 决策"认知 |
| 02 | [Function Calling 深入](agent-lessons/02_function_calling/) | 搞懂 function calling 机制，手写通用工具调度器 |
| 03 | [ReAct：思考-行动-观察循环](agent-lessons/03_react_loop/) | 手写最小 ReAct loop（不用任何框架，面试核心） |
| 04 | [多工具与工具设计](agent-lessons/04_tool_design/) | 5+ 个工具的取舍，工具描述好坏如何影响选择 |
| 05 | [记忆：记住上下文](agent-lessons/05_memory/) | 多轮对话、上下文窗口限制与处理策略 |
| 06 | [规划与任务分解](agent-lessons/06_planning/) | Plan-and-Execute 范式，对比 ReAct 的适用场景 |
| 07 | [Agentic RAG：Agent + RAG](agent-lessons/07_agentic_rag/) | 把 RAG 包装成工具，让 Agent 自主决定检索时机 |
| 08 | [多智能体协作](agent-lessons/08_multi_agent/) | 多个 Agent 各司其职、分工协同完成复杂任务 |
| 09 | [毕业项目：智能研究助手](agent-lessons/09_capstone/) | 联网搜索 + 结构化研究报告（简历级项目） |

> 已完成全部 **9 节课** 🎉。每课都包含原理讲解 + 可运行代码 + 练习。

---

## 🔧 课程三：框架进阶课程（共 9 节课）

把前两门课手写过的东西，用 **LangChain / LangGraph** 翻译成框架版，每课做「手写版 vs 框架版」对比：

| # | 课程 | 你会学到 |
|---|------|----------|
| 01 | [LCEL 与框架全景](framework-lessons/01_lcel_overview/) | 手写 RAG vs LCEL 版对比，看清框架替你做了什么 |
| 02 | [三件套：Models + Prompts + Parsers](framework-lessons/02_models_prompts_parsers/) | 调模型、拼提示词、解析输出的标准化积木 |
| 03 | [文档处理：Loaders + Splitters + VectorStores](framework-lessons/03_documents_splitter_vectorstore/) | 数据进入环节的工程化流水线 |
| 04 | [Retrievers + RAG Chain](framework-lessons/04_retrievers_rag_chain/) | 把积木用 `\|` 拼成完整的 RAG 链 |
| 05 | [高级检索工程化](framework-lessons/05_advanced_retrieval/) | Ensemble + MultiQuery，框架真正省力的地方 |
| 06 | [LangGraph 基础](framework-lessons/06_langgraph_basics/) | StateGraph 重写 ReAct（从 LangChain 转 LangGraph 的转折点） |
| 07 | [框架级 Agent](framework-lessons/07_tools_and_agents/) | `@tool` 装饰器 + `create_agent`，几行搞定手写几十行 |
| 08 | [状态、记忆与人机协作](framework-lessons/08_state_memory_hitl/) | Checkpointer 持久化 + interrupt 人机协作（LangGraph 杀手锏） |
| 09 | [毕业项目：LangGraph 研究助手](framework-lessons/09_capstone/) | 多节点图 + Checkpointer，综合全部框架技术 |

> 已完成全部 **9 节课** 🎉。每课都包含原理讲解 + 可运行代码 + 练习。

---

## 🔀 课程四：工作流与多智能体编排课程（共 9 节课）

前三门课解决「单 Agent + 单流程」，本课进入「**多 Agent 协作编排**」——AI 架构师方向核心能力。
以 LangGraph 为主干讲透 6 种经典拓扑，再用 CrewAI / AutoGen 做同一问题的横向范式对比：

| # | 课程 | 你会学到 |
|---|------|----------|
| 01 | [Supervisor 主从模式](workflow-lessons/01_supervisor_pattern/) | 中心化动态路由调度（对比手写 L08 写死的 for 循环） |
| 02 | [Swarm 与 Handoff](workflow-lessons/02_swarm_handoff/) | 去中心化群体 + 状态交接（对比手写字符串拼接） |
| 03 | [子图 Subgraph](workflow-lessons/03_subgraph/) | 把编译好的图当节点嵌入，模块化复用 |
| 04 | [并行 Map-Reduce](workflow-lessons/04_parallel_mapreduce/) | fan-out 爆发 + reducer 合并（手写做不到的并行） |
| 05 | [共享状态通信](workflow-lessons/05_shared_state/) | 消息 / 共享态 / 黑板三种通信机制对比 |
| 06 | [多模型路由与拓扑](workflow-lessons/06_multimodel_routing/) | 星型/环型/网状/层级拓扑 + 成本控制 |
| 07 | [CrewAI 对比](workflow-lessons/07_crewai_comparison/) | 角色驱动声明式编排，对比 LangGraph supervisor |
| 08 | [AutoGen 对比](workflow-lessons/08_autogen_comparison/) | 对话驱动群聊编排，对比 LangGraph swarm |
| 09 | [毕业项目：多智能体研究系统](workflow-lessons/09_capstone/) | supervisor + 并行 + 共享态 + 多模型综合（简历级） |

> 已完成全部 **9 节课** 🎉。每课继续做「手写 Agent L08 流水线 vs 框架多智能体版」并排对比。L09 毕业项目综合 L01-L08 全部技术，是简历级作品。

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
python rag-lessons/01_getting_started/code.py

# 5. 看着输出，去 rag-lessons/01_getting_started/README.md 学原理
```

跑通后，打开 [Lesson 01 的练习](rag-lessons/01_getting_started/exercise.md) 动手改改代码。

---

## 📁 目录结构

```
RAG-test/
├── README.md                  ← 你在这里：四门课程 + 作品集项目总览
├── requirements.txt           ← 依赖（四门课统一）
├── .env.example               ← API Key 配置模板
├── data/sample_docs/          ← 练习用的示例文档（四门课共用）
├── rag-lessons/               ← 课程一：RAG 手写（9 课，已完成）
├── agent-lessons/             ← 课程二：Agent 手写（9 课，已完成）
├── framework-lessons/         ← 课程三：框架进阶（9 课，已完成）
├── workflow-lessons/          ← 课程四：工作流与多智能体编排（9 课，已完成）
├── portfolio-projects/        ← 🚀 生产级作品集项目（学完课程后的落地）
│   └── research-assistant/    ←   AI 研究分析助手（多智能体 + FastAPI + Docker）
└── docs/                      ← 设计文档与实现计划
```

每节课固定三件套：**①原理 README（讲 why 和取舍）+ ②可运行 code.py（带详细中文注释）+ ③练习**。
作品集项目则是**模块化工程结构**（src/ + api/ + tests/ + Docker），按生产标准组织。

每节课固定三件套：**①原理 README（讲 why 和取舍）+ ②可运行 code.py（带详细中文注释）+ ③练习**。

---

## 💡 学习建议

- **一定要跑代码**，不要只看。RAG 的很多直觉来自亲手改参数、看输出变化。
- 按顺序学，每课建立在前一课之上。
- 卡住了随时问我（你的 AI 助手），把报错贴给我。

---

感谢：
 Linux.do佬友支持: https://linux.do/
