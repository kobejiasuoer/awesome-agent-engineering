# 生产可靠 Deep Research Agent v3 架构文档（AgentOps L09 毕业整合）

> 从「能力完整但跑飞了没人管」的 Deep Research Agent v2，进化为**故障下可生存、危险动作有门控、崩溃可恢复、可靠性有 SLO 数字的生产可靠 v3**。
>
> 本文档是 agent-ops-lessons 10 课的毕业产出，记录七机制协同的治理架构、开关降级路径、混沌收益矩阵与 SLO 卡。

---

## 1. 七机制全景（治理架构在双层图上的位置）

```
┌─────────────────── 生产可靠 Deep Research Agent v3 ───────────────────┐
│                                                                        │
│   ①步数预算(L01)  ⑤HITL审批(L05)                                       │
│       │               │                                                │
│       ▼               ▼                                                │
│  START → research_team → writer → reviewer ─(条件)─→ [publish] → END  │
│    │      │ ②成本预算   │ ④幂等  │ ①步数①循环                          │
│    │      │ ③熔断降级   │ (L02)  │ ②成本(L02)        ⑤审批(L05)        │
│    │      ▼            ▼        ▼                                     │
│    │   split → researcher×N → summarize                                │
│    │          ③熔断降级(L03)                                           │
│    │                                                                   │
│    │   ⑥断点续跑(L06)：jobs 注册表 + checkpoint 续跑                    │
│    │   ⑦可观测(L07)：run summary + 阈值告警                            │
│    └─── 全程贯穿 ────────────────────────────────────────────────       │
│                                                                        │
│   每个机制默认关闭，开启后只在故障下生效（纯净跑零税）                    │
└────────────────────────────────────────────────────────────────────────┘
```

| 机制 | 位置 | 兜住的故障 | 开关 |
|------|------|-----------|------|
| ① 全局步数预算 + 循环检测 | reviewer 开头检查 | ③ 死循环 | `enable_step_budget` / `enable_loop_detect` |
| ② 轨迹级成本预算 | reviewer 开头检查（与①复用） | ⑤ 成本超支 | `enable_cost_budget` |
| ③ 超时熔断与诚实降级 | web_search_structured（researcher 内） | ①② 慢/坏工具 | `enable_circuit_breaker` |
| ④ 副作用与幂等 | publish 节点（reviewer PASS 后，可选） | ⑥ 危险副作用（重放） | `enable_publish` |
| ⑤ 人在环审批 | publish 节点内 interrupt | ⑥ 危险副作用（首次） | `enable_hitl` |
| ⑥ 断点续跑 | service 层 + jobs 注册表 | ④ 进程崩溃 | `enable_job_registry` |
| ⑦ 轨迹级可观测 | service 层（每次运行结束） | 可见性（不算故障） | `enable_run_summary` |

---

## 2. 开关与降级路径

所有七机制**默认关闭**。开关全关时，图结构与 v2 完全一致（无 publish 节点、无 interrupt、web_search 走字符串降级、无 run summary）。开启后按故障类型生效：

```
故障注入                    v2（裸奔）              v3（开对应防护）
─────────────────────────────────────────────────────────────────
①慢工具（web_search挂起）    超时字符串混进材料 ☠️    L03 熔断快速失败 + 降级声明 ✅
②坏工具（搜索抛错/吐垃圾）   垃圾混进 findings ☠️     L03 同上（content 空，不污染）✅
③循环诱导（永远打回）        步数叠乘→recursion崩 💀   L01 步数预算诚实收尾 🟡（部分结果）
④进程崩溃（writer处被杀）    全部重跑 🔄              L06 checkpoint续跑 ✅（重做1节点）
⑤预算炸弹（超长文本）        token烧穿不停 💸         L02 硬预算刹车 🟡（部分结果）
⑥危险副作用（重复/未批发布） 重复发布 ⚠️             L04幂等no-op + L05审批门 ✅
```

> 🎯 **诚实收尾 vs 崩溃收尾**：v3 的截断（🟡）是「带着已有材料出部分结果 + 标注截断」，用户拿到不完整但可用的报告；v2 的 recursion_limit 崩溃（💀）是抛异常，用户拿到报错。这是「护轨迹」与「护请求」的本质区别——轨迹可以诚实截断，请求只能成功或失败。

---

## 3. 混沌收益矩阵（六类故障 × 全关/全开）

来自 [`eval_agent/run_chaos_eval.py`](../eval_agent/run_chaos_eval.py)，对照 [L00 裸基线](../../agent-ops-lessons/00_overview/baseline_chaos.json)：

| 故障 | 全关结局 | 全关浪费token | 全开结局 | 全开浪费token | 收益 |
|------|---------|--------------|---------|--------------|------|
| slow | ☠️ polluted | 124 | 🟡 truncated | 30 | 省 94 + 不污染 |
| flaky | ☠️ polluted | 162 | 🟡 truncated | 40 | 省 122 + 不污染 |
| loop | 🟡 caught | 220 | 🟡 truncated | 80 | 省 140 |
| crash | 🔄 full_rerun | 115 | ✅ completed | 60 | 省 55 + 不重跑 |
| bomb | 💸 overspent | 70714 | 🟡 truncated | 5000 | 省 65714 |
| sideeffect | ⚠️ duplicate | 168 | ✅ completed | 10 | 省 158 + 不重复 |

---

## 4. 可靠性 SLO 卡

| SLO 指标 | 全关（v2） | 全开（v3） | 改善 |
|----------|-----------|-----------|------|
| 任务成功率（含诚实截断） | 33% | 100% | +67% |
| 卡死率 | 0% | 0% | — |
| 预算超支率 | 17% | 0% | -17% |
| 副作用重复率 | 17% | 0% | -17% |
| 平均浪费 token | 11917 | 870 | -93% |

> ⚠️ **诚实标注**：mock 演示数字（基于 L00 基线的结构性结论）。真实 API 的绝对数字需 `--real` 模式，但「全关 vs 全开」的差异结构不变。

---

## 5. 版本演进图

```
v1（多智能体）              v2（Deep Research）              v3（生产可靠）
───────────────            ──────────────────              ─────────────
rag/workflow 课程           frontier + gui-agent 课程        agent-ops 课程

能跑的搜索→写报告    →      有记忆/反思/CodeAct/浏览器  →   +步数/成本/熔断/幂等/审批/恢复/观测
                            （能力完整）                    （能力完整 + 跑飞了有人管）

测试：25             →      104（+79 frontier）        →   219（+15 gui + 96 agentops）
可靠性：无            →      无                          →   SLO 卡背书（33%→100%）
```

与 kb-qa 的三版本格式对齐：kb-qa 走了 RAG→运维→多模态，research-assistant 走了多智能体→深研究→生产可靠——两个作品集项目对称，每一步都有数字。

---

## 6. 与其他课程的边界

| 课程 | 护什么 | 对象 |
|------|--------|------|
| ops-lessons（kb-qa） | 一次请求（鉴权限流守护栏） | 请求 |
| **agent-ops（本课，research-assistant）** | **一条轨迹（循环/预算/幂等/审批/恢复）** | **轨迹** |
| frontier-L08/L09 | 轨迹质量评估（事后离线） | 评估 |
| frontier-L10 TaskLedger | 跨运行语义增量 | 账本（工作层） |
| **agent-ops L06 durable** | **单次运行执行恢复** | **checkpoint（执行层）** |

账本管「跨运行增量」（第三次接着第二次做），durable 管「单次运行恢复」（这次崩在 writer 从 writer 接着跑）。两层各管一段，互补不重叠。

---

## 7. 复现命令

```bash
cd portfolio-projects/research-assistant

# 1. 全部测试（219）
python -m pytest -q

# 2. 混沌收益矩阵
python eval_agent/run_chaos_eval.py          # mock 演示
# python eval_agent/run_chaos_eval.py --real # 真实 API（需 key）

# 3. 单课演示
python ../../agent-ops-lessons/00_overview/code.py          # 裸基线
python ../../agent-ops-lessons/03_breaker_degrade/code.py   # 熔断器
python ../../agent-ops-lessons/06_durable_resume/code.py    # 断点续跑
```
