# Agent 渐进式学习课程设计

## 背景

学习者画像：
- **技术基础**：会 Python，已完成同工作区的 RAG 课程（懂 LLM API 调用、embedding、检索、prompt 工程）
- **学习目标**：求职/转岗大模型方向，需要系统性知识 + 能进简历的项目
- **方向选择**：Agent 方向（大模型应用最主流赛道，是 RAG 的自然延伸）
- **技术选型**：智谱 GLM-4（原生 function calling）+ glm-4-flash（免费练习）

与 RAG 课程的关系：独立成课，复用同一工作区的 venv/.env/requirements。最终毕业项目做成 Agentic RAG，自然衔接 RAG 课程。

## 技术前提（已验证）

`zhipuai` SDK（v2.1.5，已装）原生支持 function calling：
- 请求：`tools=[{type:"function", function:{name,description,parameters}}]`、`tool_choice="auto"`
- 响应：`message.tool_calls`（含 name、arguments JSON）
- 结果回传：`messages` 追加 `{role:"tool", tool_call_id, content}`
- 与 RAG 课程共用 venv，环境无需改动

## 设计原则（沿用 RAG 课程）

1. **第一课就出成果**：跑通最小 Agent，建立对 Agent 的直观认知。
2. **课时顺序 = Agent 能力进阶**：从单工具调用 → ReAct 循环 → 多工具 → 记忆 → 规划 → Agentic RAG → 多 Agent → 毕业项目。
3. **每课三件套**：原理 README（讲 why 和取舍）+ 可运行 code.py（带详细中文注释）+ 练习。
4. **原理优先于框架**：关键环节先手写一遍（如 ReAct loop、工具调度器），看清原理再谈框架。**这是求职面试核心卖点**——面试官最爱问"你手写过 Agent loop 吗"。
5. **可视化为先**：打印 Agent 每一步的 Thought/Action/Observation，让学习者"看见 Agent 在想什么"。

## 目录结构

```
RAG-test/
├── lessons/              ← RAG 课程（已完成）
├── agent-lessons/        ← Agent 课程（本课程）
│   ├── README.md         ← Agent 课程总览
│   ├── 01_what_is_agent/
│   ├── 02_function_calling/
│   ├── 03_react_loop/
│   ├── 04_tool_design/
│   ├── 05_memory/
│   ├── 06_planning/
│   ├── 07_agentic_rag/
│   ├── 08_multi_agent/
│   └── 09_capstone/
├── data/  .env  requirements.txt  ← 共用
└── docs/superpowers/specs/  ← 设计文档
```

每个课时目录统一包含：`README.md`（原理）+ `code.py`（可运行）+ `exercise.md`（练习）。

## 课时设计（共 9 节）

### L01 — 认识 Agent：从问答到行动
**目标**：跑通最小 Agent，建立"Agent = LLM + 工具 + 决策"的直观认知。

**原理 README**：LLM 的局限（只会生成文本不能做事）；Agent 三要素（LLM + 工具 + 自主决策循环）；Chatbot vs RAG vs Agent 三种形态对比；function calling 全景。

**code.py**：用原生 function calling 让 Agent 调用"获取当前时间"和"计算器"两个工具。问"现在几点了？距离今天结束还有多少分钟？"，看 Agent 自主决定调哪个工具、传什么参数。

**练习**：加一个新工具；问一个不需要工具的问题看 Agent 会不会跳过工具。

---

### L02 — Function Calling 深入：让大模型调用工具
**目标**：彻底搞懂 function calling 机制，手写工具调度器。

**原理 README**：模型怎么"决定"调用工具（不是真的理解，是基于训练学到的模式）；tools 的 JSON Schema 定义格式；tool_choice 的平台差异（通用协议可支持 auto/none/指定，智谱仅支持 auto）；参数解析与错误处理；单轮 vs 多轮调用。

**code.py**：手写一个 `execute_function(name, args)` 工具调度器，定义 3-4 个工具（天气查询模拟、计算器、时间、字符串处理），演示参数解析、错误兜底、多轮调用。

**练习**：故意传错参数看 Agent 怎么应对；设计一个需要两次工具调用的任务。

---

### L03 — ReAct：思考-行动-观察循环（面试核心）
**目标**：手写最小 ReAct loop（不用框架），这是面试必问考点。

**原理 README**：ReAct = Reasoning + Acting；Thought→Action→Observation 循环；为什么这个模式有效（显式推理让决策可追溯）；终止条件与最大步数防死循环；ReAct vs 纯 function calling 的区别。

**code.py**：**手写 ReAct loop**（不用任何框架）——一个 while 循环，每轮：让 LLM 输出 Thought + Action → 执行 Action → 把 Observation 喂回去 → 直到 LLM 给出 Final Answer。打印每一步，让学习者看清 Agent 的"思考过程"。

**练习**：调整最大步数；构造一个会让 Agent 陷入循环的问题；对比有/无 Thought 的效果。

---

### L04 — 多工具与工具设计
**目标**：学会设计好用的工具，理解"工具越多越难选"的权衡。

**原理 README**：好工具的特征（描述清晰、参数简单、单一职责、返回结构化）；工具描述怎么写模型才选得对；工具数量与选择准确率的权衡；工具冲突/重叠怎么办。

**code.py**：给 Agent 配 5+ 个工具（计算、时间、字符串、列表操作、单位换算），用一个需要多个工具配合的复杂任务，观察 Agent 怎么选工具、按什么顺序调用。

**练习**：故意写一个描述模糊的工具，看 Agent 会不会选错；合并/拆分工具对比效果。

---

### L05 — 记忆：让 Agent 记住上下文
**目标**：搞懂 Agent 的记忆机制，处理上下文窗口限制。

**原理 README**：短期记忆（对话历史即上下文）vs 长期记忆（持久化存储）；上下文窗口限制问题；窗口管理策略（截断、滑动窗口、摘要压缩）；记忆与 RAG 的关系（长期记忆本质上是"对自己的对话做 RAG"）。

**code.py**：实现一个带记忆的多轮对话 Agent——记住前面说过的话。演示三种窗口管理（全保留→超长报错、截断、摘要）的效果差异。

**练习**：和 Agent 玩一个需要记忆的游戏（如"记住我说的三个词"）；实现摘要压缩策略。

---

### L06 — 规划与任务分解
**目标**：让 Agent 能处理复杂的多步骤任务。

**原理 README**：为什么复杂任务需要规划（一步到位 vs 分步）；CoT 思维链；Plan-and-Execute 模式（先全局规划再逐步执行）；ReAct 的"边想边做" vs Plan-Execute 的"先想后做"对比。

**code.py**：实现 Plan-and-Execute——先让 LLM 生成任务计划（JSON 列表），再逐步执行每个子任务，最后汇总。对比 ReAct 模式的效果差异。

**练习**：构造一个 5+ 步骤的任务；对比 Plan-Execute 和 ReAct 各自的优劣场景。

---

### L07 — Agentic RAG：Agent + RAG（衔接 RAG 课程）
**目标**：把 RAG 包装成工具被 Agent 调用，知识闭环。

**原理 README**：传统 RAG（每次都检索）vs Agentic RAG（Agent 自主决定要不要检索）；什么时候该检索、什么时候不该；多轮检索（查一次不够再查）；自适应检索（先简单查，不够再深查）；这是 RAG 课程的直接延伸。

**code.py**：把前面 RAG 课程的知识库包装成一个 `search_knowledge_base(query)` 工具，再配几个其他工具。让 Agent 面对不同问题自主决定"这个问题要查知识库吗"。对比传统 RAG 无脑检索的区别。

**练习**：让 Agent 面对一半需要检索、一半不需要的混合问题；实现"查不到就换个关键词重查"的多轮检索。

---

### L08 — 多智能体协作
**目标**：理解为什么需要多个 Agent，怎么让它们协作。

**原理 README**：单 Agent 的局限（一个 Agent 干所有事容易乱）；多 Agent 的分工思路（按角色/按技能）；常见架构（规划者+执行者、主从、对等辩论）；Agent 间怎么通信（共享状态/消息传递）；协作的代价（成本、复杂度、调试难）。

**code.py**：实现一个简单的 3-Agent 协作——规划者（拆任务）+ 执行者（调用工具）+ 审查者（检查结果），让它们协作完成一个任务。打印每个 Agent 的角色和消息。

**练习**：加一个"批评者"Agent 看效果；对比单 Agent 和多 Agent 在同一任务上的表现。

---

### L09 — 毕业项目：智能研究助手（简历级）
**目标**：综合应用所有技术，做一个能进简历的 Agent。

**原理 README**：完整 Agent 系统的架构；工程化要点（错误处理、步数限制、可观测日志、成本控制）；从 demo 到产品的差距；简历项目该怎么包装和讲述。

**code.py**：一个**智能研究助手 Agent**——用户给一个主题，Agent 自主：联网搜索（用 duckduckgo-search，免费无 key）→ 整理信息 → 可能多轮搜索补充 → 生成结构化研究报告。集成：function calling + ReAct 循环 + 记忆 + 规划。带完整的日志输出（让用户看见 Agent 的完整工作过程）。

**练习**：扩展搜索源；加一个"事实核查"步骤；把这个项目写进简历的练习。

## 实施说明

- **分批制作**：不一次性写完 9 课。先完成 L01，让学习者跑通、确认体验 OK，再逐课推进。
- **复用现有 venv**：Agent 课程与 RAG 课程共用 `.venv`，按需往 `requirements.txt` 追加依赖（如 L09 加 `duckduckgo-search`）。
- **依赖 zhipuai**：所有课程的 function calling 都通过现有 zhipuai SDK 实现，无需额外安装。
