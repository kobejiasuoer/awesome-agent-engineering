# 工作流与多智能体编排课程 🔀（LangGraph 主干 + CrewAI / AutoGen 对比）

这是一套**面向求职/转岗 AI 应用开发**的进阶课程，聚焦**多 Agent 协作编排**——AI 架构师方向的核心能力。

> **前置**：已学完 [RAG 课程](../rag-lessons/)（9 课）+ [Agent 课程](../agent-lessons/)（9 课）+ [框架进阶课程](../framework-lessons/)（9 课）。
>
> **本课程定位**：前三门课解决的是「**单 Agent + 单流程**」——你已经会用 LangGraph 建一个 Agent 图、用 ReAct 调工具、带记忆带 HITL。本课进入「**多 Agent 协作编排**」：supervisor 动态调度、swarm 群体交接、子图模块化、并行 map-reduce、共享状态通信、多模型路由。每课继续做「**你手写过的 Agent L08 流水线 vs 框架多智能体版**」并排对比——杀手锏 DNA 一脉相承。

---

## 🎯 为什么学这门课？

- **架构师必备**：多智能体系统是 2024-2026 年 AI 应用的核心架构（OpenAI Swarm、MetaGPT、Devin 都是这套）
- **填上前 27 课的坑**：Framework L07 决策表预告了「并行/子图」但 L09 没兑现；Agent L08 exercise 留了「辩论模式」骨架没实现——本课逐个兑现
- **三框架横向对比**：同一问题用 LangGraph / CrewAI / AutoGen 各做一遍，看清三种范式（图 / 角色 / 对话）的取舍
- **简历作品**：L09 多智能体研究系统，从单 Agent 跃迁到多 Agent 协作

> 💡 **核心心智**：前三门课你学的是「一个 Agent 怎么聪明」，本课学的是「**一群 Agent 怎么协作**」——拓扑、通信、调度是三大永恒主题。

---

## 🗺️ 学习路径（共 9 节课，三段式）

### 第一段：LangGraph 多智能体拓扑（L01-L06）— 主干

每一课讲透**一种经典架构概念**（不是讲一个框架），LangGraph 只是观察它的镜头。

| # | 课程 | 讲的架构概念 | 对应你的手写课 |
|---|------|------------|---------------|
| 01 | [Supervisor 主从模式](01_supervisor_pattern/) | 中心化动态路由调度 | Agent L08（主从，讲了没写）|
| 02 | [Swarm 与 Handoff](02_swarm_handoff/) | 去中心化 + 状态交接 | Agent L08（消息传递）|
| 03 | [子图 Subgraph](03_subgraph/) | 模块化与复用 | Agent L08（三个独立函数）|
| 04 | [并行 Map-Reduce](04_parallel_mapreduce/) | fan-out 爆发 + reducer | Agent L08（无法并行）|
| 05 | [共享状态通信](05_shared_state/) | 消息 / 共享态 / 黑板 | Agent L08（三种通信，只写了消息）|
| 06 | [多模型路由与拓扑](06_multimodel_routing/) | 星型/环型/网状/层级 + 成本 | Agent L08（单一模型）|

### 第二段：横向框架对比（L07-L08）

用 L01 的 supervisor 系统做基准，换两个框架重写同一问题，看清范式差异。

| # | 课程 | 范式 | 对比对象 |
|---|------|------|---------|
| 07 | [CrewAI 对比](07_crewai_comparison/) | 角色驱动（声明式）| 对比 L01 supervisor |
| 08 | [AutoGen 对比](08_autogen_comparison/) | 对话驱动（群聊）| 对比 L02 swarm + 补辩论模式坑 |

### 第三段：毕业项目（L09）

| # | 课程 | 综合技术 |
|---|------|---------|
| 09 | [毕业项目：多智能体研究系统](09_capstone/) | supervisor + 并行 + 共享态 + 多模型 + 子图 |

> 目前已完成 **8 / 9** 节课（L01-L06 LangGraph + L07 CrewAI + L08 AutoGen）。每课包含原理讲解 + 可运行代码 + 练习。只剩 L09 毕业项目！

---

## 🚀 快速开始

与前三门课共用 `.venv` 环境（Python 3.11），框架已全部验证可调通智谱 GLM：

```bash
# 1. 激活环境（你已有）
.venv\Scripts\Activate.ps1

# 2. 确认 .env 里有智谱 API Key（已配好）

# 3. 跑第一课（进 L01 后）
python workflow-lessons/01_supervisor_pattern/code.py
```

> 💰 **省钱**：执行类 Agent 用 `glm-4-flash`（免费），决策类用 `glm-4`。L06 会专门讲多模型成本控制。

---

## 📁 目录结构

```
RAG-test/
├── rag-lessons/          ← 课程一：RAG 手写（已完成）
├── agent-lessons/        ← 课程二：Agent 手写（已完成，L08 是本课锚点）
├── framework-lessons/    ← 课程三：框架进阶（已完成，L06-L09 是本课 LangGraph 基础）
├── workflow-lessons/     ← 课程四：工作流与多智能体编排（你在这里）
│   ├── README.md         ← 课程总览
│   ├── 01_supervisor_pattern/
│   ├── 02_swarm_handoff/
│   ├── 03_subgraph/
│   ├── 04_parallel_mapreduce/
│   ├── 05_shared_state/
│   ├── 06_multimodel_routing/
│   ├── 07_crewai_comparison/
│   ├── 08_autogen_comparison/
│   └── 09_capstone/
├── data/ .env requirements.txt  ← 四门课共用
└── docs/                 ← 设计文档
```

每个课时目录统一三件套（与前 27 课一致）：
- `README.md` — 架构原理 + 映射对比（手写 L08 vs 框架多智能体）
- `code.py` — 可运行代码，中文注释
- `exercise.md` — 练习 + 思考题

---

## 💡 学习建议

- **每课都回看 Agent L08**：那是手写多智能体的天花板（固定流水线 + 字符串拼接），本课每一课都在问「框架怎么把它做得更好」
- **重架构轻 API**：本课核心是 supervisor/swarm/subgraph/parallel 这些**架构概念**，不是背 LangGraph API。换一个框架，概念依然成立
- **三框架对比是精华**：L07/L08 不是「另起炉灶学新框架」，而是「同一问题换个镜头」——这才是架构师的思维
- **求职重点**：L01（supervisor）、L04（并行）、L09（毕业项目）是面试和简历核心

---

## 📚 技术版本

本课程基于以下已验证的技术栈（Python 3.11 + `.venv`）：

| 组件 | 版本 | 作用 |
|------|------|------|
| `langgraph` | 1.2.7 | 主干框架（L01-L06）|
| `langchain` | 1.3.11 | LangGraph 依赖 + 模型集成 |
| `crewai` | 1.15.1 | L07 对比框架（角色驱动）|
| `autogen-agentchat` | 0.7.5 | L08 对比框架（对话驱动，**异步架构**）|
| `autogen-ext[openai]` | 0.7.5 | AutoGen 接 OpenAI 兼容协议的 client |
| `litellm` | 1.91.0 | CrewAI/AutoGen 接智谱 GLM 的桥 |
| `langgraph-supervisor` | 0.0.31（L01 已验证）| supervisor prebuilt（L01）|
| `langgraph-swarm` | 0.1.0（L02 已验证）| swarm prebuilt（L02）|

> ⚠️ **两个已踩到的国产模型坑**（将变成教学点）：
> - **CrewAI**：用 `LLM(model='openai/glm-4')` 走 litellm，且要关 `CREWAI_TRACING_ENABLED` 避免交互提示
> - **AutoGen**：非 OpenAI 模型必须手传 `model_info={vision, function_calling, ...}`，否则报 `ValueError`
