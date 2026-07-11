# Lesson 01 — 记忆分层：从「对话历史」到「记忆系统」

> 本课目标：**手写一个最小但完整的 Agent 记忆系统（情景记忆 + 语义记忆两层），接入 research-assistant 的 researcher 节点，让第二次研究同一主题时记得第一次查过什么、结论是什么。**

学完你能回答：**「Agent 怎么做记忆？你的和对话历史有什么区别？」**——对话历史是日志不是记忆，记忆要有检索、有遗忘、能跨会话共享。

---

## 0. 起点：L00 拆出来的问题

L00 拆 LangGraph Checkpointer 时得出一个结论：

```
Checkpointer（现状）= 对话状态持久化
    存的是：某个 thread 的完整 State 快照
    能做：跨轮恢复对话（thread_id 相同 → 接着上次）
    不能：检索 / 遗忘 / 跨 thread 共享 / 提炼

记忆系统（本课要建）= 经验的存储与调回
    存的是：提炼后的经验/事实
    能做：按语义检索 / 衰减遗忘 / 跨会话共享 / 后续可提炼
```

research-assistant 现在只有 Checkpointer。硬任务跑两次（L00 基线），第二次完全失忆——这就是本课要补的缺口。

---

## 1. 记忆的分层模型

人脑的记忆不是一坨，是分层的。Agent 也该分层——这不是硬凑认知科学，而是不同层的记忆有不同的**检索方式、生命周期、密度**，混在一起就要么检索不动、要么信息淹没。

### 三层记忆

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent 记忆分层                           │
├──────────────┬──────────────┬───────────────────────────────┤
│  工作记忆     │  情景记忆     │       语义记忆                │
│ (working)    │ (episodic)   │ (semantic)                   │
├──────────────┼──────────────┼───────────────────────────────┤
│ 当前上下文窗口│ 发生过的事件  │ 沉淀的事实结论               │
│ = LLM 的窗口  │ "查了X发现Y" │ "MCP是基于JSON-RPC的协议"    │
├──────────────┼──────────────┼───────────────────────────────┤
│ 最短命        │ 中等寿命     │ 最持久                        │
│ 轮次结束即淘汰│ 可遗忘       │ 不遗忘（量小价值高）          │
├──────────────┼──────────────┼───────────────────────────────┤
│ 隐式（prompt）│ 向量检索     │ 结构化检索                    │
│ LangGraph管   │ 本课Chroma   │ 本课内存list                  │
└──────────────┴──────────────┴───────────────────────────────┘
```

| 层 | 存什么 | 怎么检索 | 寿命 | 本课实现 |
|---|---|---|---|---|
| 工作记忆 | 当前对话/任务上下文 | 在 prompt 里直接有 | 一个轮次 | LangGraph State + Checkpointer（已有） |
| 情景记忆 | 具体事件（"研究了X，发现Y"） | 向量相似度 | 可遗忘 | Chroma 向量库 |
| 语义记忆 | 沉淀结论（结构化） | topic 匹配 + 相似度 | 不遗忘 | 内存 list |

> 🎯 **为什么要分情景和语义？** 情景记忆高保真但低密度——原始信息多，检索时靠向量找相关的，但条数一多就噪音大。语义记忆是**从多条情景归纳出的结论**，密度高、可复用。两者关系：情景是原料，语义是成品（L02 的 consolidate 就是"原料→成品"的加工）。

### MemGPT 的「操作系统式分页」思想

> **论文**：MemGPT: Towards LLMs as Operating Systems（Packer et al. 2023, [arXiv:2310.08560](https://arxiv.org/abs/2310.08560)）

**一句话说它证明了什么**：把 LLM 的上下文窗口当「内存」、外部存储当「磁盘」，让 Agent 自己决定什么时候把什么内容在内存和磁盘间「换入换出」，能让有限窗口处理超长上下文任务。

MemGPT 的洞察是**操作系统式的**：你不能把所有东西都放进内存（窗口有限），但你可以让进程（Agent）自己管理换页——需要时调回，不用时淘汰。本课的 MemoryStore 就是这个思想的简化版：

- 内存（工作记忆）= prompt 上下文
- 磁盘（外部存储）= Chroma + 语义 list
- 换入 = `recall(query)` 把相关记忆注入 prompt
- 换出 = 遗忘策略淘汰旧记忆（L02）

> 💡 本课不实现 MemGPT 的「Agent 自己发指令换页」（那需要 LLM 主动调用 memory 工具），而是用**确定性触发**（researcher 研究前必 recall）。这是简化——L03 的 skills 范式会更接近「Agent 主动决定加载什么」。

---

## 2. 流派对比

**问题**：Agent 怎么记住跨会话的经验？

| 流派 | 做法 | 取舍 |
|---|---|---|
| ① 全量塞上下文 | 把所有历史对话塞进 prompt | ✅ 简单；🚫 贵、撞窗口上限、信息淹没 |
| ② Checkpointer/对话历史 | 按 thread 存快照（现状） | ✅ 跨轮恢复；🚫 无检索、无遗忘、不跨 thread |
| ③ 第三方记忆库（mem0 等） | 用现成记忆框架 | ✅ 省事；🚫 黑盒、学不到机制、依赖第三方 |
| ④ 手写分层记忆（本课选它） | 情景(Chroma) + 语义(list) + recall/remember/consolidate | ✅ 机制透明、可控、教学价值高；🚫 要自己写 |

**选 ④ 的理由**：任务书硬约束——"记忆分层必须从零手写（教学价值所在）"。mem0 只作对比参照不作为实现依赖。手写才能看清「存什么、怎么检索、怎么遗忘」每个环节的取舍。而且我们的场景（研究助手）记忆量不大、结构清晰，手写完全 hold 得住。

---

## 3. 手写 MemoryStore

### 核心接口

```python
class MemoryStore:
    def remember(self, content, topic, source) -> EpisodicMemory  # 写入情景记忆
    def recall(self, query, k) -> {"episodic":[...], "semantic":[...]}  # 检索
    def add_semantic(self, topic, conclusion, evidence, confidence) -> SemanticMemory  # 写语义
    def consolidate(self, llm=None) -> list[SemanticMemory]  # 巩固（L02 实现提炼）
    def forget(self, max_episodic, decay_days)  # 遗忘（L02 配置生效）
    def format_recall_for_prompt(hits) -> str  # 格式化注入 prompt
```

### 关键设计决策

**① 情景记忆用 Chroma，语义记忆用内存 list**
- 情景记忆量大、需要向量检索 → Chroma（成熟、持久化、cosine 相似度）
- 语义记忆量小、结构化、需要 LLM 归纳 → 内存 list（塞向量库反而别扭）

**② 零 API 降级路径**
- ZhipuAIEmbeddings 不可用（无 key / 401）→ 字符频次假 embedding
- Chroma 不可用 → 内存 list + 线性扫描余弦
- 这样 `code.py` 演示和测试都不依赖网络（任务书硬约束）

**③ 不可变风格**
- `remember` / `add_semantic` 返回新对象，调用方持有引用（仓库既有约定）

**④ 默认关闭**
- `enable_memory=false`，researcher 不调 recall，现有 25 测试不受影响
- 开启后第二次研究同一主题才生效

### 假 embedding 的诚实说明

```python
def _fake_embed(text, dim=64):
    # 字符频次 → 归一化向量
    # 不是真语义，但保证：字符重叠多的文本 → 向量更接近
    # 教学演示 recall 命中够用；生产必须换真 embedding
```

> ⚠️ **诚实标注**：假 embedding 的 recall 质量远低于真 embedding——它是字符级重叠，不是语义级理解。`code.py` 的演示能跑通「第二次记得第一次」，但召回精度是演示级，不是生产级。生产开 `ZHIPUAI_API_KEY` 走 embedding-3。

---

## 4. 接入 researcher 节点

改动点（`nodes.py`）：researcher 研究前先 `recall(subtopic)`，命中记忆时注入 prompt。

```python
# 研究前先 recall 相关旧记忆
mem_store = get_memory_store()  # enable_memory=false 时返回 None
if mem_store is not None:
    hits = mem_store.recall(subtopic, k=3)
    memory_hint = mem_store.format_recall_for_prompt(hits)

# 有命中时，prompt 加一句"在旧记忆基础上深化，不要简单重复旧结论"
```

**为什么不所有节点都接记忆？** researcher 是研究的入口，它决定"查什么、怎么查"——在这里注入旧记忆最有杠杆（避免重复查已知的东西）。writer 接记忆会在 L03/L05 更合适的地方做。

### get_memory_store 单例

```python
_memory_store = None  # 模块级单例

def get_memory_store():
    global _memory_store
    if not settings.enable_memory:
        return None  # 完全不介入
    if _memory_store is None:
        from .memory import MemoryStore
        _memory_store = MemoryStore()
    return _memory_store
```

单例的原因：跨会话记忆必须共享同一个库。如果每次 research 新建 MemoryStore，记忆就跨不了会话。

---

## 5. 硬任务验证：第二次记得第一次

`code.py` 演示：
1. 创建 MemoryStore，写入第 1 次研究的发现
2. 第 2 次研究前 recall，看是否命中第 1 次的记忆
3. 对比 L00 基线（recall 命中数 0）→ 本课（recall 命中数 > 0）

```
L00 基线：run2 recall 命中 = 0（完全失忆）
L01 之后：run2 recall 命中 = N（记得 run1 的发现）
```

> ⚠️ 这是 mock 演示（假搜索 + 假/真 embedding），验证的是**机制成立**（recall 能命中 remember 写入的内容），不是真实研究质量。真实质量要 L09 的 harness 量化。

---

## 6. 落地清单

### 改了哪些文件

| 文件 | 改动 | 说明 |
|---|---|---|
| `src/research_assistant/memory.py` | **新增** | MemoryStore（情景+语义两层，Chroma+内存） |
| `src/research_assistant/config.py` | 加 4 个配置项 | `enable_memory`/`memory_db_path`/`memory_max_episodic`/`memory_decay_days` |
| `src/research_assistant/nodes.py` | researcher 加 recall | 研究前检索旧记忆注入 prompt + `get_memory_store` 单例 |
| `tests/test_memory.py` | **新增** 12 个测试 | mock embedding，验证 remember/recall/consolidate/format |

### 如何验证

```bash
cd portfolio-projects/research-assistant

# 1. 全量测试（现有 25 + 新增 12 = 37 全绿）
.venv/Scripts/python.exe -m pytest tests/ -q
# 预期：37 passed

# 2. 单独跑记忆测试
.venv/Scripts/python.exe -m pytest tests/test_memory.py -v
# 预期：12 passed

# 3. 演示记忆机制（不依赖真实 API）
cd ../../frontier-lessons/01_memory
PYTHONIOENCODING=utf-8 ../../.venv/Scripts/python.exe code.py
# 预期：写入→recall 命中→对比 L00 基线（0 命中 vs N 命中）

# 4. 真实开启记忆跑硬任务（需 ZHIPUAI_API_KEY）
# 在 research-assistant/.env 设 ENABLE_MEMORY=true
# 跑两次同一主题，看第二次日志有"记忆命中"
```

---

## 7. 本课在两条主线上的位置

- **评估主线**：本课建立了记忆系统，但**还没量化它的收益**。L08 的 TrajectoryEvaluator 会拿 L00 基线轨迹（recall 命中数=0）对比本课之后的轨迹（recall 命中数>0），把"记得"变成可度量的指标。现在只能说"机制成立了"，L08 才能说"值多少分"。
- **上下文工程主线**：记忆是**上下文工程母题的第一个子问题**——"上下文窗口里该放什么"的答案是"放 recall 调回的相关旧经验"。本课的 `recall → format → 注入 prompt` 就是"按需把外部存储的内容换入工作记忆"，这是 MemGPT 分页思想的最小实现。L03 的 skills 会从另一个角度（能力按需加载）再看这个母题。

---

## 🎯 面试话术

> 「对话历史是日志不是记忆——Checkpointer 存的是完整 State 快照，没有检索、没有遗忘、不跨会话。我给 Agent 做了情景/语义两层记忆：情景记忆用 Chroma 向量库存具体事件，语义记忆用结构化 list 存沉淀结论。researcher 研究前先 recall 相关旧记忆注入 prompt，第二次研究同一主题时它记得上次查过什么、结论是什么。我手写的，没用 mem0——因为手写才看得清存什么、怎么检索、怎么遗忘每个环节的取舍。」
