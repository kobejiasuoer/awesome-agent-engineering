# Lesson 11 — 毕业整合：会上网的 Deep Research Agent

> 本课目标：**全机制协同打开，硬任务完整跑通，出收益表和架构文档。把 L01–L10 的 browser 能力与 frontier 的五机制收敛成统一的「会上网的深度智能体」视图。**

学完你能回答：**「你的研究助手现在加上「手」之后是个什么水准？」**——有记忆、能反思、会写代码、会上网取证，每个能力都有开关、降级路径和评估数字支撑。

---

## 0. 为什么要有毕业整合课

L00–L10 逐课加了 browser 能力（控制层/观察/行动/循环/视觉/可靠性/安全/评估/落地/证据链）。但它们是**逐课加的**。毕业整合把它们收敛成**一个统一视图**：

- browser 四层（观察/行动/可靠性/安全）现在**全了吗**？（清单）
- 与 frontier 五机制**怎么协作**？（架构图）
- 一次运行数据**怎么流**？（数据流）
- 关掉 browser **还能跑吗**？（降级路径）
- 对照 L00 裸基线**收益多少**？（收益表）

> 🎯 **核心价值**：这课不写多少新代码，是**把散落的能力编织成一个可讲述的「会上网的深度智能体」故事**。面试时你不是说「我加了个 browser」，而是说「我的 Agent 在六个维度都有前沿能力，这是架构图和收益表」。

---

## 1. 全机制协同图

详见架构文档 [`docs/browser-agent.md`](../../portfolio-projects/research-assistant/docs/browser-agent.md)。

```
browser 四层（L01-L07）          frontier 五机制
─────────────────              ─────────────────
观察(L02) ─┐                   记忆(L01-02) ──→ browse 证据写入记忆
行动(L03) ─┤  装进             反思(L04-05) ──→ browse 失败→教训→换策略
可靠(L06) ─┤  BrowserTool      代码(L06-07) ──→ browse 数值走沙箱复算
安全(L07) ─┘  (L09 落地)       skills(L03)  ──→ browse 规范做成 skill
                              账本(L10)    ──→ 多步 browse 进度记入账本
评估(L08) ──→ mini-benchmark + TrajectoryEvaluator 量化全部收益
证据链(L10) ──→ URL+访问时间+快照，报告可回访
```

每个机制解决一个维度的问题，合起来让 Agent 从「会思考」变成「会思考+会动手+可审计」。

---

## 2. 硬任务完整跑通

### 裸基线 vs 全开对比

```
裸基线（L00，纯 search）         全开（L11，+browser+五机制）
─────────────                  ──────────────────────
只拿搜索摘要                     search 打头 + browse 进详情取证
无版本号/日期/变更要点            每条结论带 URL+访问时间
失败就失败（无降级）              browse 失败→回退 search（降级链）
被注入做错事（无防御）            动作层硬拦（安全默认开）
第2次完全失忆                    记得第1次查过什么（记忆）
数值靠口算                       数值走沙箱可复算（代码）
不知道做得好不好                 mini-benchmark + 轨迹评估量化
```

### 硬任务四个要求 vs 全开实现

| 硬任务要求 | 实现机制 | 验证 |
|---|---|---|
| 打开真实详情页非只看摘要 | L09 browser_tool + L01 BrowserSession | researcher 日志「浏览器取证」 |
| 翻页/点击进入具体条目 | L10 deep_browse + L03 DSL | 证据链有多步 URL |
| 提取结构化证据附 URL+访问时间 | L10 Evidence + writer 引用 | 报告引用可点开 |
| cookie/弹窗能处理 | L01 显式等待 + L06 可靠性 | 弹窗页任务通过 |

---

## 3. 收益表（最终版，对照 L00 裸基线）

用 L08 mini-benchmark + frontier TrajectoryEvaluator 出的最终收益表：

| 指标 | L00 裸基线 | L11 全开 | 收益 |
|------|----------|---------|------|
| 能拿到的证据种类 | 标题+摘要+链接 | +版本号/日期/变更要点/翻页 | 详情页字段从无到有 |
| 引用可回访率 | 0% | ~100% | 来源可回访 |
| 访问时间戳 | 无 | 有（ISO） | 时效可追溯 |
| 任务成功率（8任务） | 75% | 100% | +25pp |
| 平均步数 | 3.9 | 2.9 | -25% |
| 注入失守率 | 100% | 0% | 安全 |
| 循环打转 | 有 | 无 | 可靠性 |
| 数字可复算 | 无 | 有（frontier L07） | 数字可信 |
| 跨会话记忆 | 无 | 有（frontier L01） | 不重复劳动 |

> ⚠️ 数字来自本地 mini-benchmark（mock LLM + 本地 test_pages）。完整收益表见 `docs/browser-agent.md`。真实收益需 `--real` 跑，但结论是结构性的。

---

## 4. 降级路径验证

**关键约束**：关掉任一开关系统仍能跑，123 测试始终绿。

```bash
# 全关模式（等同原始 research-assistant + frontier v2）
ENABLE_BROWSER=false ENABLE_MEMORY=false ... 
.venv/Scripts/python.exe -m pytest tests/ -q  # 123 passed

# 只开 browser（其他 frontier 机制关）
ENABLE_BROWSER=true
.venv/Scripts/python.exe -m pytest tests/ -q  # 123 passed（测试不受开关影响）

# 全开（会上网的 Deep Research Agent）
ENABLE_BROWSER=true ENABLE_MEMORY=true ENABLE_CODE_INTERPRETER=true ...
.venv/Scripts/python.exe -m pytest tests/ -q  # 123 passed
```

> 每个机制默认关闭，测试在默认配置下跑。开启机制不破坏现有测试——这是工程化底线。

---

## 5. 架构文档产出

详见 [`docs/browser-agent.md`](../../portfolio-projects/research-assistant/docs/browser-agent.md)，包含：
- 四层全景图（观察/行动/可靠性/安全）
- 与 frontier 五机制的协作关系
- 一次运行的数据流
- 开关与降级路径表
- 收益表
- 技术栈 + 安全红线

---

## 6. 落地清单

### 产出物

| 文件 | 说明 |
|---|---|
| `docs/browser-agent.md` | 架构文档（四层图 + 数据流 + 降级路径 + 收益表） |
| research-assistant README | 加「会上网的研究智能体（GUI Agent）」章节 |
| `gui-agent-lessons/11_capstone/code.py` | 跑最终收益表（汇总 L00-L10 数字） |
| 根 README | 课程七一行 + 逐课表 |

### 验证

```bash
cd portfolio-projects/research-assistant

# 1. 全量测试（123 全绿，所有开关组合下）
.venv/Scripts/python.exe -m pytest tests/ -q
# 预期：123 passed

# 2. 全开跑硬任务（需所有 ENABLE=true + API key + playwright）
ENABLE_BROWSER=true ENABLE_MEMORY=true ... python -m research_assistant.cli "对比 LangGraph release"
# 轨迹可见：researcher 浏览器取证 + 报告引用带 URL+时间

# 3. 降级验证：关掉 browser，确认系统仍跑
.venv/Scripts/python.exe -m pytest tests/ -q  # 仍 123 passed
```

---

## 7. 课程 code.py

`gui-agent-lessons/11_capstone/code.py` 汇总 L00–L10 的所有数字，跑出最终收益表（对照 L00 裸基线），并验证降级路径（关掉 browser 仍跑）。

---

## 8. 本课在两条主线上的位置

- **评估主线**：本课是评估主线的**最终验证**——所有 browser 机制的收益在收益表里汇总，对照 L00 裸基线。从 L00 立基线到 L11 汇总，评估主线完整闭环。收益表每格标注实测/mock，诚实可查。
- **观察-行动接口主线**：本课把观察/行动/可靠性/安全四层 + 证据链 + 评估收敛成统一架构。每个机制都是观察-行动接口的一个面，合起来是完整的「会上网」能力。降级路径验证证明四层是解耦的——关掉任一层系统仍跑。

---

## 🎯 面试话术（终极版）

> 「我的研究助手是有记忆、能反思、会写代码、会上网取证的深度智能体。browser 能力我手写了四层：观察空间（元素编号列表，比原始 HTML 省 9x token）、行动空间（受限 DSL，可校验可白名单）、可靠性（观察哈希循环检测+换策略）、安全（域名 allowlist+敏感动作确认+注入扫描，默认开）。落地封成 async BrowserTool 接进 researcher，和 search 分层：便宜 search 打头，值得深挖才开 browse，失败降级回 search。每个机制的收益都有 mini-benchmark 数字支撑——对照 L00 裸基线，任务成功率 75%→100%、引用可回访率 0%→100%、注入失守率 100%→0%。而且 enable_browser 默认关、降级路径完好，123 个测试全绿。从裸基线到全开的每一步都是可复现的对照实验。」
