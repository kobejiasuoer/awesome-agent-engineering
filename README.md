# LLM 应用实战课程 📚

> **中文** | [English](README.en.md)

这是一套**从零开始、系统掌握大模型应用开发**的实战课程，覆盖 **RAG、Agent、框架工程化、多智能体编排、LLMOps 生产运维、智能体前沿** 六大方向。
面向**会 Python 但刚接触大模型**的开发者，用可运行的代码 + 原理讲解，一步步从原理手写到框架落地，再到多 Agent 协作架构，最后深入 Agent 前沿能力。

> 技术栈：智谱 GLM-4 + embedding-3 · Chroma 本地向量库 · LangChain + LangGraph · CrewAI · AutoGen · Python

---

## 🗺️ 六门课程总览

本工作区包含**六门递进课程**，建议按顺序学：

| 课程 | 内容 | 状态 |
|------|------|------|
| 📘 [RAG 手写课程](rag-lessons/) | 从零系统理解 RAG 原理（embedding→检索→切块→prompt→混合检索→改写→评估→工程化）| ✅ 9/9 完成 |
| 🤖 [Agent 手写课程](agent-lessons/) | 从零系统理解 AI Agent 原理（Function Calling→ReAct→工具设计→记忆→规划→Agentic RAG→多智能体→毕业项目）| ✅ 9/9 完成 |
| 🔧 [框架进阶课程](framework-lessons/) | LangChain + LangGraph 工程化（把手写原理翻译成框架，每课做"手写版 vs 框架版"对比）| ✅ 9/9 完成 |
| 🔀 [工作流与多智能体编排](workflow-lessons/) | 多 Agent 协作架构（supervisor/swarm/子图/并行/共享态/多模型，三框架横向对比）| ✅ 9/9 完成 |
| 🛡️ [LLMOps 生产运维](ops-lessons/) | 上线之后：可观测性（日志/追踪/线上评估）→ 安全（鉴权限流/注入攻防/守护栏）→ MCP 集成 → 性能成本（缓存/压测/选型）。把作品集项目从「能跑」推进到「运维就绪」| ✅ 13/13 完成 |
| 🧠 [智能体前沿](frontier-lessons/) | Agent 记忆/反思/Code Agent/轨迹评估/上下文工程/长任务——教未收敛的前沿，把 research-assistant 养成跨会话进化的深度智能体（Deep Research Agent v2）。**每课有流派对比 + 设计实验验证收益** | ✅ 13/13 完成 |

> **学习路径**：先学 RAG（懂检索原理）→ 再学 Agent（懂自主决策）→ 再学框架进阶（工程化落地）→ 再学多智能体编排（架构师进阶）→ 再学 LLMOps（运维就绪）→ 最后学智能体前沿（让 Agent 自主进化）。

---

## 🚀 生产级作品集项目

学完课程后，把所学能力缝合成**真正可上生产的 AI 应用**：

| 项目 | 内容 | 状态 |
|------|------|------|
| 📚 [企业知识库问答系统](portfolio-projects/knowledge-base-qa/) | 生产级 RAG：混合检索 + 智谱 rerank + 防幻觉引用 + ragas 评估。**经 ops-lessons 升级为运维就绪 v2**：结构化日志/Langfuse 追踪/线上评估闭环 + key 鉴权限流 + 注入攻防守护栏 + MCP Server（可被 Agent 调用）+ 语义缓存/压测/成本选型。| ✅ 运维就绪 |
| 🔬 [AI 研究分析助手](portfolio-projects/research-assistant/) | 多智能体并行研究系统：真实联网搜索 + 审稿回路 + 多模型降本 + SSE 流式 + SqliteSaver 持久化 + FastAPI 服务化 + Docker 部署。**经 ops-lessons L09 接入 MCP**（内部+联网双源）。**经 frontier-lessons 升级为 Deep Research Agent v2**：Agent 记忆（情景/语义分层）+ 反思式双通道 reviewer（冲突修正）+ CodeAct 代码解释器（可复算）+ Skills 渐进式加载 + 任务账本（跨会话增量简报）+ 轨迹评估（机制收益量化）。| ✅ Deep v2 |

> 这是课程能力的**生产级落地**——不是 demo，是能直接部署、能扛真实流量、能讲完整运维故事的 AI 应用服务。
> 两个项目通过 MCP 标准协议打通（见 [ops-lessons L09](ops-lessons/09_mcp_client/)）。

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

## 🛡️ 课程五：LLMOps 生产运维课程（共 13 节课）

前四门课教你把 AI 应用**做出来**，本课教你把它**运维起来**——回答面试官那句「你的项目上线之后呢？怎么知道它好不好、怎么防攻击、怎么被别的系统集成、怎么控成本」。所有改动直接落到作品集的 **knowledge-base-qa**，把它从「能跑的 demo」升级为「运维就绪 v2」。四个模块层层递进：

| # | 课程 | 你会学到 |
|---|------|----------|
| 01 | [结构化日志](ops-lessons/01_structured_logging/) | 从 print 到可查询的 JSON 事件流 + trace_id 贯穿全链路 |
| 02 | [Langfuse 全链路追踪](ops-lessons/02_langfuse_tracing/) | 每次问答的检索/rerank/生成耗时、token、成本可视化 |
| 03 | [线上评估闭环](ops-lessons/03_online_eval/) | 真实问答抽样 + 自动 ragas 打分 + 坏答案队列 |
| 04 | [API 鉴权与限流](ops-lessons/04_auth_ratelimit/) | key 鉴权 + 按 key 限流，防裸奔防账单打爆（401/429/200） |
| 05 | [Prompt 注入攻防](ops-lessons/05_prompt_injection/) | 间接注入（恶意指令藏文档里）+ 构造攻击测试集跑失守基线 |
| 06 | [输入输出守护栏](ops-lessons/06_guardrails/) | 材料隔离 + 指令-数据分离 + 输出过滤，防御固化进 CI |
| 07 | [MCP 是什么](ops-lessons/07_mcp_basics/) | AI 应用的「USB 接口」：M×N→M+N，手写最小 server/client |
| 08 | [把知识库封成 MCP Server](ops-lessons/08_mcp_server/) | kb-qa 检索封成标准工具，任意 host 零代码接入 |
| 09 | [Agent 作 MCP Client](ops-lessons/09_mcp_client/) | research-assistant 调 kb-qa 知识库，两个作品打通 |
| 10 | [语义缓存](ops-lessons/10_semantic_cache/) | 同义问法命中缓存，跳过检索+生成，降延迟降成本 |
| 11 | [压测与并发](ops-lessons/11_loadtest/) | QPS/P95/P99 基线，定位瓶颈在上游 API 限流 |
| 12 | [成本/质量权衡](ops-lessons/12_cost_quality/) | 用评估数据量化 glm-4 vs flash，分环节选型降本 |
| 13 | [毕业整合：运维就绪 v2](ops-lessons/13_capstone/) | 一张运维面板 + 生产上线检查清单串起全部 12 课 |

> 已完成全部 **13 节课** 🎉。教学 code.py 全部零依赖或有 mock 降级路径可独立跑；落地改动写进 kb-qa 并附「## 落地清单」。跑不了真实外部服务（Langfuse/Docker/压测）的地方均**诚实标注未实测**并给降级路径。

---

## 🧠 课程六：智能体前沿（共 13 节课）

前五门课教的是**已收敛的知识**（RAG 怎么切、ReAct 怎么写），本课教的是**未收敛的前沿**——Agent 记忆、反思、Code Agent、轨迹评估、上下文工程，业界没有标准答案。因此课程风格变了：README 不讲「标准做法」，讲「有哪几种流派、取舍是什么、我们选 X 因为……」；代码是「手写核心机制 + 设计实验验证有没有用」。所有改动落到 **research-assistant**，把它从「搜索→写报告」的一次性系统养成**跨会话进化的深度研究智能体（Deep Research Agent v2）**。六个模块：

| # | 课程 | 你会学到 |
|---|------|----------|
| 00 | [方法预热](frontier-lessons/00_method/) | 论文三遍读法 + 拆 LangGraph 源码 + 跑失忆基线（全程对照） |
| 01 | [记忆分层](frontier-lessons/01_memory/) | 情景(Chroma)+语义(list) MemoryStore，researcher 接入 recall |
| 02 | [反思式写入](frontier-lessons/02_reflection_write/) | reflect_and_store 提炼记忆 + consolidate 巩固 + 遗忘策略 |
| 03 | [Skills 与上下文工程](frontier-lessons/03_skills/) | 渐进式 skill_loader，记忆/skills/RAG/MCP 统一到上下文工程 |
| 04 | [Reflexion 手写](frontier-lessons/04_reflexion/) | 三组件 loop + 盲目重试 vs 反思重试对比 + 消融实验 |
| 05 | [反思进研究回路](frontier-lessons/05_reflection_research/) | 双通道 reviewer（文字+事实）+ 冲突检测 + 定向补研修正 |
| 06 | [CodeAct 手写](frontier-lessons/06_codeact/) | 代码作为行动空间 + 进程级沙箱（import 白名单/超时/截断） |
| 07 | [代码解释器落地](frontier-lessons/07_code_interpreter/) | code_interpreter 接入 writer，报告数字可复算 |
| 08 | [轨迹评估](frontier-lessons/08_trajectory_eval/) | TrajectoryEvaluator：成功率/步数/循环/归因 + 机制触发检测 |
| 09 | [Eval Harness](frontier-lessons/09_eval_harness/) | 开关矩阵 × 任务集 = 机制收益表（回归式评估） |
| 10 | [长任务](frontier-lessons/10_long_task/) | TaskLedger：TODO 树 + 断点续跑 + 增量简报 |
| 11 | [毕业整合](frontier-lessons/11_capstone/) | Deep Research v2：五机制协同 + 架构文档 + 收益表 |
| 12 | [前沿追踪方法](frontier-lessons/12_frontier_tracking/) | 三遍读法完整版 + 框架评估清单 + 多 Agent 记忆共享最小复现 |

> 已完成全部 **13 节课** 🎉。**两条贯穿主线**：①评估主线（L00 立基线→L08 建评估器→L09 harness 量化每个机制收益）；②上下文工程主线（记忆/skills/RAG/MCP 统一到「窗口里放什么」一个母题）。每课 README 有「流派对比」小节 + 至少一道「设计实验验证」练习。104 个单元测试全绿，所有新机制默认关闭、降级路径完好。

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
├── README.md                  ← 你在这里：六门课程 + 作品集项目总览
├── requirements.txt           ← 依赖（六门课统一）
├── .env.example               ← API Key 配置模板
├── data/sample_docs/          ← 练习用的示例文档（六门课共用）
├── rag-lessons/               ← 课程一：RAG 手写（9 课，已完成）
├── agent-lessons/             ← 课程二：Agent 手写（9 课，已完成）
├── framework-lessons/         ← 课程三：框架进阶（9 课，已完成）
├── workflow-lessons/          ← 课程四：工作流与多智能体编排（9 课，已完成）
├── ops-lessons/               ← 课程五：LLMOps 生产运维（13 课，已完成）
├── frontier-lessons/          ← 课程六：智能体前沿（13 课，已完成）
├── portfolio-projects/        ← 🚀 生产级作品集项目（学完课程后的落地，ops/frontier 主战场）
│   ├── knowledge-base-qa/     ←   企业知识库问答（RAG，运维就绪 v2）
│   └── research-assistant/    ←   AI 研究分析助手（多智能体 + FastAPI + Docker）
└── docs/                      ← 设计文档与实现计划
```

每节课固定三件套：**①原理 README（讲 why 和取舍）+ ②可运行 code.py（带详细中文注释）+ ③练习**。
作品集项目则是**模块化工程结构**（src/ + api/ + tests/ + Docker），按生产标准组织。

---

## 💡 学习建议

- **一定要跑代码**，不要只看。RAG 的很多直觉来自亲手改参数、看输出变化。
- 按顺序学，每课建立在前一课之上。
- 卡住了随时问我（你的 AI 助手），把报错贴给我。

---

感谢：
 Linux.do佬友支持: https://linux.do/
