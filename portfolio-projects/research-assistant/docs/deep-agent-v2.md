# Deep Research Agent v2 架构文档（Frontier L11 毕业整合）

> 从「搜索→写报告」的一次性系统，进化为**有记忆、能反思、会写代码、跨会话进化的深度研究智能体**。
>
> 本文档是 frontier-lessons 13 课的毕业产出，记录五机制协同的架构、数据流、开关与降级路径。

---

## 1. 五机制全景

```
┌─────────────────── Deep Research Agent v2 ───────────────────┐
│                                                               │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐  │
│  │  记忆     │   │ Skills   │   │  反思     │   │ 代码解释器│  │
│  │ (L01-02) │   │ (L03)    │   │ (L04-05) │   │ (L06-07) │  │
│  │          │   │          │   │          │   │          │  │
│  │ 经验调回  │   │ 能力调回  │   │ 错误修正  │   │ 可复算计算│  │
│  │ recall   │   │ load     │   │ reflect  │   │ execute  │  │
│  └─────┬────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘  │
│        │             │              │              │         │
│        └──────┬──────┴──────┬───────┴──────┬───────┘         │
│               │             │              │                 │
│               ▼             ▼              ▼                 │
│         researcher      writer        reviewer               │
│               │             │              │                 │
│               └──────┬──────┴──────────────┘                 │
│                      │                                       │
│              ┌───────▼────────┐                               │
│              │  TaskLedger    │   跨会话计划推进（L10）         │
│              │  (进度管理)     │   断点续跑 + 增量简报          │
│              └────────────────┘                               │
│                                                               │
│              ┌────────────────┐                               │
│              │ TrajectoryEval │   轨迹评估（L08-09）           │
│              │  (质量度量)     │   机制收益量化                 │
│              └────────────────┘                               │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

---

## 2. 一次运行中的数据流

以"第 2 次研究 MCP 生态"为例（全机制开启）：

```
用户输入: "继续追踪 MCP 生态演进"
    │
    ▼
① TaskLedger.next_actions("MCP 生态演进")
    → 返回未完成 TODO: [查 MCP 2025 路线图]
    → "接着上次做，而非从头"
    │
    ▼
② research_team 子图
    ├─ split: 拆子题（基于 next_actions 的 TODO）
    ├─ researcher (并行):
    │    ├─ MemoryStore.recall("MCP 2025 路线图")
    │    │    → 命中旧记忆: "上次查到 MCP 聚焦互操作"
    │    │    → 注入 prompt: "在旧记忆基础上深化"
    │    ├─ web_search: 联网补充新信息
    │    └─ kb_search: 内部知识库（可选）
    └─ summarize: 汇总发现
    │
    ▼
③ writer
    ├─ SkillLoader.load_matched_skills(摘要)
    │    → 匹配 "research-brief-format" skill → 加载格式规范
    ├─ 写报告（遵循 skill 格式 + 增量标注 🆕✏️➡️）
    ├─ if should_use_code(摘要):
    │    ├─ LLM 生成分析代码
    │    ├─ CodeInterpreter.execute_code (沙箱)
    │    └─ 结果 + 代码附录附报告（可复算）
    └─ 产出报告
    │
    ▼
④ reviewer (双通道)
    ├─ 事实通道: check_conflicts(新findings, 记忆旧结论)
    │    → 发现冲突？ → re_research → 回 ② 补研
    └─ 文字通道: 评估报告质量
         → 不合格？ → rework → 回 ③ 重写
         → 合格？ → pass
    │
    ▼
⑤ 研究结束（后处理）
    ├─ reflect_and_store(findings → 记忆库)
    │    → LLM 提炼"学到了什么" → 存入 MemoryStore
    ├─ MemoryStore.consolidate → 多条情景归纳成语义结论
    ├─ MemoryStore.forget → 淘汰旧且不用的记忆
    ├─ TaskLedger.update_status → 标记 TODO 完成
    └─ TrajectoryEval → 轨迹落盘 + 指标卡
    │
    ▼
产出: 增量简报（含 🆕新增/✏️修正/➡️不变）+ 可复算附录
```

---

## 3. 开关与降级路径

每个机制默认关闭，可独立开关。关掉任一机制系统仍能跑（降级路径完好）。

| 机制 | config 开关 | 默认 | 关闭时降级 |
|------|------------|------|-----------|
| 记忆 recall | `enable_memory` | False | researcher 不注入旧记忆（从零研究） |
| 反思式写入 | `enable_memory` | False | 研究后不提炼记忆（无跨会话学习） |
| Skills | `enable_skills` | False | writer 不加载格式规范（默认格式） |
| 代码解释器 | `enable_code_interpreter` | False | 数值走 LLM 直出（不可复算） |
| 双通道 reviewer | `enable_memory` | False | 只走文字通道（不检测事实冲突） |
| 任务账本 | `enable_ledger` | False | 每次从头研究（无断点续跑） |
| 轨迹落盘 | 总是开启 | — | 每次运行产出 traces/ |

### 降级保证

```bash
# 全关：等同原始 research-assistant（25 测试全绿）
# 部分开：只开需要的机制，其余降级
# 全开：Deep Research v2 完整能力
```

> **关键约束**：全部 104 个测试在所有开关组合下都应通过（默认全关测）。

---

## 4. 机制收益表（对照 L00 裸基线）

| 指标 | L00 裸基线 | v2 全开 | 差异 |
|------|-----------|---------|------|
| 记忆召回 | 0% | 100% | 从失忆到记得 |
| 反思 | 无 | 有 | 失败可修正 |
| 冲突修正 | 无 | 有 | 错误结论可纠正 |
| 代码执行 | 无 | 有 | 数值可复算 |
| 跨会话增量 | 无 | 有 | 不从头重写 |
| 步数效率 | 9 步/次 | 更少（第2次起） | 记忆避免重复查 |

> ⚠️ 诚实标注：具体数字来自 L09 的 mock 演示（非真实 API）。真实数字需 `run_harness.py --real` 跑。mock 演示验证的是**机制成立**（从无到有），不是**具体数值**。

---

## 5. 技术栈

- **LLM**: 智谱 GLM-4 / glm-4-flash（多模型路由，绝不引入 OpenAI/Anthropic）
- **框架**: LangGraph（图编排 + checkpoint）
- **记忆**: Chroma 向量库（情景）+ 内存 list（语义）
- **账本**: sqlite（TODO 树持久化）
- **沙箱**: subprocess + import 白名单 + 超时（进程级）
- **评估**: 自研 TrajectoryEvaluator（规则 + judge 混合）
- **所有核心机制手写**：记忆/反思/沙箱/评估器/skill_loader/task_ledger
