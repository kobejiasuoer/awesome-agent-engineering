# Lesson 07 — CrewAI 对比：角色驱动的声明式编排

> **本课定位**：LangGraph 段（L01-L06）已收官，进入**横向框架对比段**。本课用 CrewAI 重写 L01 的 supervisor 系统，对比两种范式：LangGraph 的「节点+边」命令式图 vs CrewAI 的「角色+任务+编队」声明式编排。看清两者的取舍，是架构师选型的基本功。
>
> **对比基准**：`workflow-lessons/01_supervisor_pattern`（L01 的 supervisor 系统，本课用 CrewAI 重写它）。

---

## 一、两种范式的根本区别

### LangGraph：命令式（Imperative）

你在 L01-L06 一直在做的方式——**画图**：

```python
# 定义节点（每个节点是一个函数/Agent）
researcher = create_agent(llm, name="researcher", ...)
analyst = create_agent(llm, name="analyst", ...)

# 显式连线（谁是 supervisor，派给谁）
supervisor = create_supervisor(agents=[researcher, analyst], model=llm, prompt="...")
graph = supervisor.compile()  # 编译成图

# 运行
result = graph.invoke({"messages": [...]})
```

特点：**你控制一切**——每个节点做什么、怎么连、条件路由、并行、HITL，全是你显式声明的。灵活，但代码多。

### CrewAI：声明式（Declarative）

CrewAI 的方式——**声明角色和任务**，框架自动编排：

```python
# 声明角色（role + goal + backstory）
researcher = Agent(role="研究员", goal="查资料", backstory="...", llm=llm)
analyst = Agent(role="分析师", goal="分析", backstory="...", llm=llm)

# 声明任务
task1 = Task(description="查RAG", expected_output="简介", agent=researcher)
task2 = Task(description="分析RAG优点", expected_output="分析", agent=analyst)

# 组建编队，框架自动编排
crew = Crew(agents=[researcher, analyst], tasks=[task1, task2],
            process=Process.hierarchical, manager_llm=llm)
result = crew.kickoff()
```

特点：**框架控制流程**——你不画图、不连边，只声明"谁做什么"，框架自动决定执行顺序。简洁，但灵活性低。

### 范式对比表

| | LangGraph（命令式）| CrewAI（声明式）|
|---|---|---|
| 心智模型 | 画图（节点+边）| 声明角色（role+goal+backstory）|
| 流程控制 | 你显式控制（add_edge/条件边）| 框架自动编排（process 参数）|
| 灵活性 | **高**（子图/并行/HITL/流式/自定义 State）| 低（框架预设几种模式）|
| 代码量 | 多 | **少** |
| 学习曲线 | 陡（要懂图、State、reducer）| 缓（角色+任务直觉）|
| 适合 | 复杂系统、精细控制 | 快速原型、角色明确的场景 |
| 调试 | 可视化图、trace 每个节点 | 看 manager 决策日志 |

> 💡 **类比**：LangGraph 像"手挡"（手动挡汽车，控制力强但要技术），CrewAI 像"自挡"（自动挡，省心但控制弱）。

---

## 二、CrewAI 的三件套

CrewAI 用三个概念组织多 Agent 系统：

### 1. Agent（角色）

```python
researcher = Agent(
    role="研究员",          # 角色名（manager 靠它识别）
    goal="收集事实信息",     # 目标
    backstory="资深研究员",  # 背景（给 LLM 的人设）
    llm=llm,                # 用哪个模型
)
```

对比 LangGraph 的 `create_agent`：CrewAI 的 Agent 强调**人设**（role/goal/backstory），LangGraph 强调**系统提示词**（system_prompt）。本质一样，表达不同。

### 2. Task（任务）

```python
task = Task(
    description="查一下什么是 RAG 技术",  # 任务描述
    expected_output="RAG 技术简介",        # 期望输出（CrewAI 特色：约束输出）
    agent=researcher,                     # 由谁做
)
```

`expected_output` 是 CrewAI 的特色——它让 LLM 知道"成功长什么样"，有助于输出质量。LangGraph 没有这个概念。

### 3. Crew（编队）

```python
crew = Crew(
    agents=[researcher, analyst],
    tasks=[task1, task2],
    process=Process.hierarchical,  # ⭐ 编排模式
    manager_llm=llm,               # hierarchical 时的 manager LLM
)
```

`process` 决定怎么编排：

| process | 对应 LangGraph | 行为 |
|---|---|---|
| `Process.sequential` | 流水线（手写 L08 / L04 串行）| 按 agents 列表顺序自动执行 |
| `Process.hierarchical` | supervisor（L01）| manager 动态调度 |

---

## 三、教学金矿：CrewAI 接国产模型（智谱 GLM）

这是本课最有实用价值的知识点——CrewAI 不像 LangGraph 有 `ChatZhipuAI` 直接封装，它要**通过 litellm 桥接**。

### 接 GLM 的三步

```python
os.environ["CREWAI_TRACING_ENABLED"] = "false"  # 第 1 步：关 tracing（否则交互卡住）

llm = LLM(
    model="openai/glm-4-flash",              # 第 2 步：model 名加 "openai/" 前缀
    api_key=os.getenv("ZHIPUAI_API_KEY"),
    base_url="https://open.bigmodel.cn/api/paas/v4",  # 第 3 步：指向智谱
)
```

### 三个坑（踩过才知）

**坑 1：model 名必须加 `openai/` 前缀**
```python
# ❌ 错误：CrewAI 不认识 glm-4-flash
llm = LLM(model="glm-4-flash", ...)

# ✅ 正确：加 openai/ 前缀，告诉 litellm 走 OpenAI 兼容协议
llm = LLM(model="openai/glm-4-flash", ...)
```

**坑 2：必须关 tracing**
```python
# 不加这行，首次运行会弹交互提示"是否启用 tracing"，卡住程序
os.environ["CREWAI_TRACING_ENABLED"] = "false"
```

**坑 3：必须传 base_url**
```python
# 不传 base_url，litellm 默认请求 OpenAI 官方，认证失败
llm = LLM(model="openai/glm-4-flash", api_key=..., base_url="https://open.bigmodel.cn/api/paas/v4")
```

> 💡 对比 LangGraph：LangGraph 用 `ChatZhipuAI(model="glm-4", api_key=...)` 一行搞定（有官方封装）。CrewAI 要走 litellm 桥接，多两步。这是"官方封装 vs 通用桥接"的代价。

---

## 四、CrewAI hierarchical vs LangGraph supervisor

这是本课核心对比——同一个"调度中心"模式，两种框架怎么写：

| | LangGraph（L01）| CrewAI（本课）|
|---|---|---|
| 创建调度中心 | `create_supervisor(agents=..., model=..., prompt=...)` | `Crew(agents=..., process=hierarchical, manager_llm=...)` |
| 教调度中心怎么调度 | 手写 `prompt="研究派 researcher..."` | **不用写**（框架内置调度逻辑）|
| worker 定义 | `create_agent(llm, name=..., system_prompt=...)` | `Agent(role=..., goal=..., backstory=..., llm=...)` |
| 运行 | `graph.invoke({"messages": [...]})` | `crew.kickoff()` |
| 输出 | `result["messages"][-1].content` | `str(result)` |

**CrewAI 更简洁**（不用写 prompt 教 manager 怎么调度），**LangGraph 更可控**（你能精确控制 supervisor 的行为）。

---

## 五、什么时候用 CrewAI，什么时候用 LangGraph？

**用 CrewAI 当……**
- 快速原型（想 10 分钟搭一个多 Agent 系统）
- 角色明确（每个 Agent 有清晰的人设和职责）
- 不需要精细控制（子图/并行/HITL/流式/自定义 State）
- 团队协作（声明式更易读，非技术人员能看懂角色定义）

**用 LangGraph 当……**
- 需要精细控制（L03 子图、L04 并行、framework-L08 HITL）
- 复杂流程（条件路由、动态分支、回环）
- 生产级系统（可观测性、持久化、错误处理）
- 自定义 State（带业务字段的 TypedDict）

> 经验法则：原型阶段用 CrewAI 快速验证想法，生产阶段迁移到 LangGraph 精细化。两个框架不冲突，可以先用 CrewAI 搭骨架，再用 LangGraph 重写关键路径。

---

## 六、本课代码

`code.py` 三个实验：

1. **实验 1（sequential）**：CrewAI 按角色顺序自动执行（researcher→analyst→writer），对应流水线
2. **实验 2（hierarchical）**：CrewAI manager 动态调度，对应 L01 supervisor
3. **实验 3（代码量对比）**：同样系统，CrewAI vs LangGraph 各多少行，直观对比两种范式

```bash
python workflow-lessons/07_crewai_comparison/code.py
```

---

## 七、小结 & 下节预告

**✅ 本课要点**：
- CrewAI 三件套：Agent(角色) + Task(任务) + Crew(编队)
- sequential = 流水线（按顺序）；hierarchical = supervisor（manager 调度）
- 范式差异：声明式（角色+任务）vs 命令式（节点+边）
- 接国产模型：`LLM(model='openai/glm-4')` 走 litellm + 关 tracing + 传 base_url
- hierarchical = L01 supervisor 的 CrewAI 版（manager 动态调度）
- 选型：快速原型用 CrewAI，精细控制用 LangGraph

**🔜 下节预告（L08 — AutoGen 对比）**：
本课 CrewAI 是「角色驱动」，下课 AutoGen 是「对话驱动」——多 Agent 在一个 GroupChat 里像开会一样发言。还会补全 Agent L08 exercise 留的"辩论模式"坑。AutoGen 0.4+ 是异步架构（`async/await`），和 CrewAI/LangGraph 的同步风格不同，这是另一个教学点。

> ⚠️ **清醒认知**：CrewAI 的"简洁"是有代价的——它的 `process` 只有 sequential/hierarchical 两种预设模式。你要做 L03 的子图、L04 的并行 map-reduce、L05 的黑板模式？CrewAI 做不到（或很难做）。CrewAI 适合"标准模式的多 Agent"，LangGraph 适合"非标准流程"。选型前先想清楚你的流程是不是"标准"的。
