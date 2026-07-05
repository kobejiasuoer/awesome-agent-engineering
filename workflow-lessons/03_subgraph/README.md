# Lesson 03 — 子图 Subgraph：模块化与复用

> **本课定位**：L01/L02 的系统都在一张图里。但随着 Agent 越加越多，单图会变成蜘蛛网。本课学**子图**——把一个编译好的图（如 L02 的 swarm）当作节点嵌入更大的父图。这是**兑现框架课 L07 决策表预告的「子图」伏笔**（那个预告 L09 会讲，但 L09 实际没讲，本课来填这个坑）。
>
> **映射的手写课**：`agent-lessons/08_multi_agent`（你手写 L08 的 planner/executor/reviewer 是三个平铺函数，没有封装概念——本课用子图把这种"一组 Agent"封装成模块）。
>
> **复用的前序课**：`workflow-lessons/02_swarm_handoff`（L02 的客服 swarm，本课直接拿来当子图嵌入）。

---

## 一、为什么需要子图？

### 单图的困境

假设你的客服系统越来越复杂：除了退款/售后（L02 的 swarm），还要加投诉处理、订单查询、VIP 通道……如果全塞进一张图：

```
START → classify → refund → after_sales → complaint → order_query → vip → ... → END
                       （一张图里十几个节点，线连成蜘蛛网）
```

问题：
1. **读不懂**：一张图几十个节点，没人能看全流程
2. **改不动**：改退款流程可能碰坏投诉流程（耦合）
3. **没法复用**：这套客服系统想用在另一个项目？得整张图搬过去
4. **没法独立测试**：测退款流程得跑起整张图

### 子图的解法

把"一组相关 Agent"封装成一个**子图**（编译好的图），在父图里当作**一个节点**：

```
父图视角（简洁）：                 子图内部（封装的复杂性）：
START → classify → customer_service → END      triage → refund → after_sales
                       ↑                         （L02 的 swarm）
                  看起来是 1 个节点
```

这就是软件工程里**模块化**思想在多智能体里的应用——和函数、类、微服务一脉相承。

---

## 二、核心思想：子图即节点

### 子图怎么用？

LangGraph 里，**任何编译好的图（`compiled_graph`）都可以直接作为 `add_node` 的参数**——它就是一个节点：

```python
# 1. 构建并编译子图（L02 的客服 swarm）
service_subgraph = create_swarm(
    agents=[triage, refund, after_sales],
    default_active_agent="triage",
).compile()

# 2. 在父图里把它当节点
builder = StateGraph(ParentState)
builder.add_node("classify", classify)
builder.add_node("customer_service", service_subgraph)  # ⭐ 子图当节点
builder.add_node("other_handler", other_handler)
```

从父图看，`customer_service` 就是一个普通节点——内部是 swarm 还是单 Agent，父图不关心（**黑盒**）。

### State 对齐（关键技术点）

子图和父图怎么共享数据？靠 **State 对齐**：

- 父图 State ⊇ 子图 State（父图字段是子图的超集）
- 子图只读写它**认识的字段**（共享字段），父图独有的字段子图不碰

```python
# 父图 State（字段多）
class ParentState(TypedDict):
    messages: Annotated[list, add_messages]
    category: str      # 父图独有

# 子图 State（MessagesState，字段少）
# 只有 messages —— 是 ParentState 的子集
```

运行时：
- 父图把 `messages` 传给子图
- 子图读写 `messages`（处理客服请求）
- 子图**看不到** `category`（它不关心分类，那是父图的事）
- 子图处理完，`messages` 更新回流到父图

> 💡 **类比**：这就像函数参数。子图"声明"它需要 `messages`（参数），父图传入 `messages`（实参）。父图的其他变量（`category`）子图访问不到——**封装**。

---

## 三、本课的架构：父图 + 客服子图

本课把 L02 的客服 swarm **原封不动**封装成子图，嵌入一个更大的父图：

```
                ┌──────────────────────────────────┐
                │             父 图                 │
                │                                   │
START → classify ──(客服?)──→ customer_service ──→ END
            │                   │                  │
            │(非客服)           │ ⭐子图节点         │
            └──→ other_handler ─→┘                 │
                                                   │
        customer_service 内部（子图，父图看不到）：   │
        triage → refund → after_sales（L02 swarm）  │
        └──────────────────────────────────┘
```

**父图的三个节点**：
1. `classify`：前置分类（写父图独有字段 `category`）
2. `customer_service`：**子图节点**（客服 swarm）
3. `other_handler`：非客服兜底

**条件路由的价值**：客服问题才启动 swarm 子图（贵），咨询问题走轻量兜底（省）。这比"所有请求都跑整套 swarm"高效得多。

---

## 四、关键 API

### 1. 构建子图（和普通图一模一样）

子图的构建没有特殊 API——它就是一个普通的编译图：

```python
service_subgraph = create_swarm(
    agents=[triage, refund, after_sales],
    default_active_agent="triage",
).compile()
# 到这里，service_subgraph 既可以独立运行，也可以当节点嵌入
```

### 2. 子图当节点（本课核心，就这一行）

```python
builder.add_node("customer_service", service_subgraph)
```

**就这一行**。子图不需要任何特殊标记，`add_node` 的第二个参数可以是函数，也可以是编译好的图——LangGraph 自动识别。

### 3. State 对齐（用 TypedDict 定义共享字段）

```python
class ParentState(TypedDict):
    messages: Annotated[list, add_messages]  # 子图也用（共享）
    category: str                             # 父图独有（子图看不到）
```

> ⚠️ **State 对齐的前提**：子图和父图的共享字段（如 `messages`）必须**类型一致**且用**相同的 reducer**（如 `add_messages`）。否则数据对接会出错。本课用 `MessagesState`（子图）和包含 `messages` 的 `ParentState`（父图），天然对齐。

---

## 五、框架替你做了什么？

| 没有子图时（手写 L08 风格）| 有子图后（本课）|
|---|---|
| 所有 Agent 平铺，没有边界 | 一组 Agent 封装成子图，有清晰边界 |
| 复用要复制粘贴 | 子图编译一次，到处嵌入 |
| 改一块可能碰坏另一块 | 子图内部改动不影响父图 |
| 测一块得跑整套 | 子图可独立 `invoke` 测试 |
| 图越来越大，读不懂 | 父图保持简洁，复杂性封装 |

**子图没有"额外能力"**——它解决的不是"能不能做到"的问题，而是"**怎么管理复杂度**"的问题。这和函数、模块、微服务的价值完全一致。

---

## 六、子图 vs 普通函数节点

容易混淆，重点说清：

| | 普通函数节点 | 子图节点 |
|---|---|---|
| `add_node` 参数 | 一个函数 `def node(state): ...` | 一个编译好的图 `compiled_graph` |
| 内部复杂度 | 单个函数（简单逻辑） | 一整张图（可以是 swarm/supervisor）|
| 有没有自己的 State | 共用父图 State | 有自己的 State（与父图对齐共享字段）|
| 能不能独立运行 | 不能（只是个函数） | **能**（`subgraph.invoke(...)`）|
| 适合 | 简单转换、分类、汇总 | **封装一组 Agent / 一个子系统** |

> 经验法则：如果一个节点内部逻辑超过 3 个步骤，或者包含多个 Agent，就考虑抽成子图。

---

## 七、兑现框架课 L07 的预告

打开 `framework-lessons/07_tools_and_agents/README.md`，那张"何时手写图"的决策表里有一行：

> 「需要并行/子图（L09 毕业项目）| 手写 StateGraph | 复杂图结构」

这句话预告 L09 会讲子图，但 **framework L09 实际做的是单 Agent 三节点图，没讲子图**——这是一个挖好但没填的坑。**本课（workflow L03）正式兑现了这个预告**：你现在会建子图、嵌子图、管理子图的 State 了。

---

## 八、本课代码

`code.py` 做三件事：

1. **实验 1（客服走子图）**：客服退款问题 → classify 分类 → 路由到 customer_service 子图 → 子图内部 swarm 处理。父图只看到一个节点。
2. **实验 2（咨询跳过子图）**：非客服问题 → classify 分类为咨询 → 跳过子图走轻量兜底。展示"按需启动子图"。
3. **实验 3（拓扑黑盒）**：打印父图 Mermaid，观察 customer_service 显示为单个节点（子图内部不展开）。

```bash
python workflow-lessons/03_subgraph/code.py
```

---

## 九、小结 & 下节预告

**✅ 本课要点**：
- 子图 = 把编译好的图当节点：`add_node("name", compiled_graph)`
- 价值：**封装**（父图简洁）+ **复用**（到处嵌入）+ **独立开发测试**
- State 对齐：父图 State ⊇ 子图 State，子图只读写共享字段
- 条件路由 + 子图 = 按需启动复杂子系统（省成本）
- 对比手写 L08：三个平铺函数 → 封装成可复用模块
- **兑现了 framework L07 预告的「子图」伏笔**

**🔜 下节预告（L04 — 并行 Map-Reduce）**：
到目前为止所有图都是**串行**的（一个节点完再下一个）。但很多任务可以**并行**——比如同时查 3 个城市的天气。L04 学 LangGraph 的 `Send` API，实现 fan-out（爆发）+ map-reduce（合并），兑现 Agent L08 README 提到但没实现的「并行」。

> ⚠️ **清醒认知**：子图不是免费的。每次进入子图会有 State 序列化/反序列化的开销。对于很简单的逻辑（一两个步骤），抽子图反而过度设计。子图适合"一组 Agent"或"一个可复用的子系统"——和微服务一样，别为了拆而拆。
