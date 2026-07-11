# Lesson 03 — Skills 与上下文工程：能力的渐进式加载

> 本课目标：**理解 2025-2026 年兴起的 Agent Skills 范式，手写最小 skills 加载器（渐进式披露），接入 research-assistant 的 writer 节点，并把记忆/skills/MCP/RAG 统一到「上下文工程」一个框架下讲清取舍。**

学完你能回答：**「了解 skills / 上下文工程吗？」**——能把它和其他三个机制统一到一个母题下讲，而不是孤立地背概念。

---

## 0. 范式转移：prompt engineering → context engineering

### 2023 年的关键词：prompt engineering

大家研究"怎么写 prompt 让 LLM 表现更好"——角色设定、few-shot、CoT、格式约束。核心假设：**上下文窗口够大，把该说的都塞进去**。

### 2026 年的关键词：context engineering

窗口确实大了（128k、200k），但问题变了：**不是写不好 prompt，是不知道该往窗口里放什么、什么时候放、怎么淘汰**。

```
prompt engineering（2023）          context engineering（2026）
─────────────────────────          ─────────────────────────────
"怎么写好一句话 prompt"             "上下文窗口里该放什么"
关注：措辞、格式、few-shot           关注：信息选择、时机、淘汰
假设：所有信息都在 prompt 里          假设：信息分散在各处，按需调回
静态：一次写好不动                   动态：运行时动态组装上下文
```

> 🎯 **核心认知**：2026 年的 Agent 难题不是"prompt 写不好"，是"上下文管理不好"。一个 Agent 运行时要面对：对话历史、记忆、知识库检索结果、工具描述、skills 规范、中间结果……全塞进去窗口爆炸，不塞又缺信息。**上下文工程就是"该放什么、何时放、怎么淘汰"的管理术**。

---

## 1. 四个机制，一个母题

前五门课 + 本课前两课，我们学了四个"往上下文里放东西"的机制。它们不是孤立的，是同一个母题的子问题：

```
              上下文工程母题
        "窗口里该放什么、何时放、怎么淘汰"
                   │
     ┌─────────┬───┴───┬─────────┐
     ▼         ▼       ▼         ▼
   记忆       RAG    Skills     MCP
  (L01-02)  (rag课)  (本课)   (ops课)
     │         │       │         │
  经验的     知识的   能力的    工具的
  按需调回   按需调回 按需调回  远程调用
     │         │       │         │
  recall()  retrieve  load()   call_tool
  注入prompt 注入prompt 注入prompt 执行返回
```

| 机制 | 放什么 | 何时放 | 怎么淘汰 | 来源课程 |
|---|---|---|---|---|
| **记忆** | 经验（上次学到的） | 研究前 recall | 时间衰减+频次 | L01-L02 |
| **RAG** | 知识（文档库的） | 查询时 retrieve | top-k 截断 | rag-lessons |
| **Skills** | 能力（操作规范） | 用到时 load | 不用不加载 | **本课** |
| **MCP** | 工具（远程能力） | Agent 决定调用 | 调用完即弃 | ops-lessons |

> 💡 **统一框架**：这四个都是"外部有信息/能力，按需调一部分进上下文"。区别只在"放什么类型的内容"和"触发时机"。能这样统一讲，说明你理解的不是四个名词，而是一个设计模式。

---

## 2. Agent Skills 范式

### 什么是 Skills

Anthropic 在 2025 年提出 Agent Skills 范式：

> **能力 = 一个文件夹**：`SKILL.md`（说明 + 规范）+ 可选脚本 + 可选资源文件。

Agent 先只看到每个 skill 的**一行描述**（几十 token），用到时才**加载全文**（可能几千 token）——这叫**渐进式披露（progressive disclosure）**。

### 渐进式披露

```
┌─ 第一层：描述（始终在上下文）──────────────────┐
│  system prompt 里有：                          │
│  可用技能：                                     │
│    - research-brief-format: 研究简报格式规范    │  ← 几十 token
│    - comparison-table: 对比表生成流程           │
│  （10 个 skill 的描述 = 200 token，很便宜）     │
└────────────────────────────────────────────────┘
          │ Agent 判断"我需要 comparison-table"
          ▼
┌─ 第二层：全文（用到才加载）────────────────────┐
│  load_skill("comparison-table") 返回：         │
│  # 对比表生成流程                               │
│  触发条件：当出现"对比""vs"时...                │  ← 几千 token
│  格式：| 维度 | A | B | ...                    │
│  流程：1.识别对象 2.提取维度 3.填充...          │
│  （只有用到的 skill 进上下文，不用的不占窗口）   │
└────────────────────────────────────────────────┘
```

### 为什么不直接全塞 system prompt？

```
全塞 system prompt                   渐进式披露
─────────────────                    ────────────
10 个 skill × 1000 token = 10000     描述：10 × 20 = 200 token
窗口占用：高（不管用不用都占）         + 用到的 1-2 个 × 1000 = 2000
噪音：Agent 被不相关 skill 干扰       总计：2200 token（省 78%）
                                     噪音：只有相关的进上下文
```

> 🎯 **核心认知**：Skills 的本质不是"多了一个工具"，是**上下文的按需加载**——和记忆的 recall、RAG 的 retrieve 完全同构。放的是"能力规范"而非"经验"或"知识"。

---

## 3. 流派对比

**问题**：怎么让 Agent 拥有多种能力/规范，又不撑爆上下文？

| 流派 | 做法 | 取舍 |
|---|---|---|
| ① 全塞 system prompt | 所有规范写进 system prompt | ✅ 简单；🚫 token 爆炸、噪音干扰 |
| ② MCP 工具 | 能力做成远程工具，Agent 调用 | ✅ 标准化、远程可共享；🚫 重协议、适合"动作"不适合"知识/流程" |
| ③ Skills（本课选它） | 能力做成文件夹，渐进式加载 | ✅ 轻量、适合知识/流程复用；🚫 不适合需要远程执行的 |
| ④ 混合 | 知识/流程用 Skills，远程动作用 MCP | ✅ 各取所长；🚫 两套机制要维护 |

**选 ③+④ 的理由**：Skills 和 MCP 不互斥——**MCP 给「手」（执行远程动作），Skills 给「操作手册」（怎么做的规范）**。研究助手需要"怎么写简报"的规范（Skills 合适），也需要"查知识库"的动作（MCP 合适）。本课先实现 Skills，MCP 已在 ops-lessons 接入。

### Skills vs 记忆的关系

| | 记忆 | Skills |
|---|---|---|
| 放什么 | 经验（动态产生） | 能力（人工编写） |
| 来源 | Agent 运行时提炼 | 开发者预设 |
| 变化 | 随经验增长 | 相对稳定 |
| 本质 | 经验的按需调回 | 能力的按需调回 |
| 母题 | 上下文工程 | 上下文工程 |

---

## 4. 手写 SkillLoader

### 核心接口

```python
class SkillLoader:
    def list_skills() -> list[SkillMeta]           # 扫描，返回元信息
    def format_skill_descriptions() -> str          # 一行描述拼成 prompt 片段
    def load_skill(name) -> str                     # 加载某个 skill 全文
    def match_skills(query) -> list[str]            # 匹配 query 需要哪些 skill
    def load_matched_skills(query) -> str           # 一步到位：匹配+加载
```

### SKILL.md 格式

```markdown
---
name: research-brief-format
description: 研究简报格式规范——规定报告的结构、标题层级和增量标注方式
---

# 技能：研究简报格式规范
## 格式要求
...（完整规范，用到时才加载）
```

frontmatter 的 `name` + `description` 是轻量元信息（进 system prompt），正文是全文（用到才加载）。

### 关键设计

**① 手写 frontmatter 解析（不引 pyyaml）**
- Skills 的 frontmatter 只需 name + description 两个字段
- 手写解析够用，避免为两个字段引入 pyyaml 依赖（仓库约定：成熟基建用库，简单逻辑手写）

**② 中文关键词匹配**
- `match_skills` 用字符滑窗取 2-4 字片段匹配（中文无空格分词）
- 生产可换 LLM 判断（"这个任务需要哪些 skill"），本课用关键词够演示

**③ 缓存**
- `load_skill` 首次 IO 后缓存，避免重复读文件

**④ 默认关闭**
- `enable_skills=false`，writer 不加载 skill，现有测试不受影响

---

## 5. 接入 writer 节点

writer 写报告前先 `load_matched_skills(摘要+反馈)`：

```python
skill_loader = get_skill_loader()  # enable_skills=false 时返回 None
if skill_loader is not None:
    skill_text = skill_loader.load_matched_skills(summary + feedback)
    if skill_text:
        prompt += f"📋 参考技能规范（请遵循其格式要求）：\n{skill_text}"
```

### 示例 skills

**research-brief-format**：规定报告结构（摘要/核心要点/增量标注/来源）。开启后 writer 产出遵循这个格式，且第二次研究时会有增量标注（🆕新增/✏️修正/➡️不变）——这正好和 L01-L02 的记忆配合。

**comparison-table**：当研究涉及对比时，用表格呈现。writer 的摘要里出现"对比/vs"时触发。

### token 节省验证

```
不开 skills：writer prompt = 摘要 + 基础指令 ≈ 500 token
开 skills 但无匹配：prompt 不变（skill_text 为空）
开 skills 且匹配 1 个：prompt + skill 全文 ≈ 500 + 800 = 1300 token
全塞 system prompt（10 个 skill）：500 + 8000 = 8500 token

→ 渐进式只在用到时加 800 token，全塞永远多 8000 token。
```

> ⚠️ **诚实标注**：token 数字是估算（实际 token 数取决于分词器），用于说明量级差异。精确数字可用 tiktoken 实测。

---

## 6. 落地清单

### 改了哪些文件

| 文件 | 改动 | 说明 |
|---|---|---|
| `src/research_assistant/skill_loader.py` | **新增** | SkillLoader（扫描+渐进式加载+匹配） |
| `skills/research-brief-format/SKILL.md` | **新增** | 示例 skill：简报格式规范 |
| `skills/comparison-table/SKILL.md` | **新增** | 示例 skill：对比表生成流程 |
| `src/research_assistant/config.py` | 加 `enable_skills` | 默认关 |
| `src/research_assistant/nodes.py` | writer 加 skill 加载 + `get_skill_loader` 单例 | 用到时加载全文注入 |
| `tests/test_skills.py` | **新增** 13 个测试 | 扫描/加载/匹配/降级 |

### 如何验证

```bash
cd portfolio-projects/research-assistant

# 1. 全量测试（25 原有 + 18 记忆 + 13 skills = 56 全绿）
.venv/Scripts/python.exe -m pytest tests/ -q
# 预期：56 passed

# 2. 演示 skills 渐进式加载
cd ../../frontier-lessons/03_skills
PYTHONIOENCODING=utf-8 ../../.venv/Scripts/python.exe code.py
# 预期：扫描 2 个 skill → 只看描述（200 token）→ 匹配后加载全文（800 token）

# 3. 真实开启 skills 跑研究
# 在 .env 设 ENABLE_SKILLS=true
# 跑一个涉及对比的主题，看 writer 输出是否遵循 skill 格式
```

---

## 7. 本课在两条主线上的位置

- **评估主线**：本课引入了 skills 机制，但**还没量化它的收益**（"用了 skill 的报告是不是更好"）。L09 的 harness 会对比"开 skills vs 关 skills"的报告质量指标。现在只能说"机制成立了"。
- **上下文工程主线**：本课是**上下文工程母题的核心一课**——把记忆/skills/RAG/MCP 统一到一个框架。Skills 是"能力的按需调回"，和记忆的"经验按需调回"完全同构。至此，上下文工程的四个子问题都有了对应的实现，L10 的长任务会把它们协同起来。

---

## 🎯 面试话术

> 「我理解 skills 的本质是渐进式上下文加载——能力做成文件夹，Agent 先只看一行描述（不占窗口），用到时才加载全文。我手写了 skill_loader：扫描目录、frontmatter 解析、关键词匹配、缓存。而且我能把记忆、skills、RAG、MCP 统一到上下文工程一个框架下讲——它们都是"外部信息/能力的按需调回"，区别只在放什么类型的内容。记忆是经验，skills 是能力，RAG 是知识，MCP 是远程工具。窗口里该放什么、何时放、怎么淘汰，这就是 2026 年的 context engineering。」
