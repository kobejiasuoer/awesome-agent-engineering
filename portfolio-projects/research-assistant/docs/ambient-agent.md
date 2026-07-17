# 常驻主动架构（Ambient v4）

> research-assistant 第四次进化：从「问了才答的会话式系统」到「一直在岗、知道什么时候该开口的常驻同事」。本文档是 [ambient-agent-lessons](../../../ambient-agent-lessons/)（课程十，10 课）落地改动的架构总览。

---

## 1. 范式：pull → push

前三个版本都是**会话式**（pull）：人发起 → 系统应答 → 跑完即散。v4 把五个环节倒过来（push）：

| 环节 | v3（会话式） | v4（常驻式） | 落地模块 |
|---|---|---|---|
| 谁发起 | 人发消息（忘了问=全盲） | 调度器到班叫醒 | `schedules.py` |
| 研究什么 | 人指定主题（每次全量） | 信源变化集决定 | `watcher.py` |
| 增量谁做 | 人肉 diff 两份报告 | 焦点子题+✏️修正简报 | `incremental.py` |
| 何时开口 | 有产出就全量推 | major/minor/none 判级+配额 | `proactivity.py` |
| 怎么交付 | 对话窗口（人在场才成立） | 收件箱五通道+隔夜审批 | `inbox.py` |
| 谁守着 | 没人守 | daemon+心跳+时段预算 | `daemon.py` / `period_budget.py` |

**研究图本体（v3 双层图 + 七机制治理）零改动**——常驻层全部长在图的外面：什么时候进图（触发）、带什么进图（增量焦点）、出图之后说不说（判级）。

---

## 2. 一次 tick 的数据流

```
AmbientDaemon.run_loop()
  │ while not stop: step(); await clock.asleep(poll)     ← 时间全部可注入
  ▼
step() ── scheduler.tick() 到班（固定网格，missed 可数）
  │           │ overlap：同主题上一轮在跑 → 本班跳过记档
  ▼           ▼
run_cycle() ─ [时段预算门] pause → 本班不开（不打断进行中）
  │
  ├─ watcher.scan_source()：item 哈希 vs 快照 → ChangeSet
  │     ok+空 → 「确认无变化」（一等公民：不进图不花钱）
  │     ok=False → 「没能看到」（≠没变化：快照不动，走告警通道）
  ├─ run_incremental()：焦点即子题（split 跳过 LLM 拆题）
  │     + 旧结论注入（ledger 已确认项：「只补新的，矛盾用『更正：』开头」）
  │     + record_and_brief()：🆕新增 / ✏️修正 / ➡️不变
  ├─ HITL 挂起检查：等审批 → approval 条目落箱（interrupt 在 checkpoint 里隔夜等人）
  ├─ classify_change() + decide()：判级（宁攒勿丢）× 政策 × 每日配额
  ├─ inbox.deliver()：notify / digest / silent（沉默不产生条目）
  └─ 记账：jobs 状态机 + 时段钱包 add_usage + 心跳 beat + 退避 note_scan_result
```

## 3. 开关矩阵（默认全关 = v3 行为逐字节一致）

| 开关 | 默认 | 开启后 | 关闭时降级 |
|---|---|---|---|
| `enable_schedules` | off | sqlite 调度表+固定网格 | 无调度（会话式入口照常） |
| `enable_source_watch` | off | 扫描先行，变化集进研究 | cycle 全量研究（现状语义） |
| `enable_incremental_run` | off | 焦点直用+旧结论注入 | split 照常 LLM 拆题 |
| `enable_proactivity` | off | 判级+配额三态决策 | 产出保守全进 digest |
| `enable_inbox` | off | 五通道异步交付 | 不投递（结果只在返回值/jobs） |
| `enable_period_budget` | off | 日钱包 ok/degrade/pause | 无时段限制（轨迹钱包仍在） |
| `enable_adaptive_scan` | off | 无变化指数退避（封顶） | 固定班次 |
| `enable_heartbeat` | off | 每 tick 心跳+缺勤告警 | 无缺勤检测 |

## 4. 与既有资产的边界（复用不重写）

| 资产 | 来源 | v4 怎么用 |
|---|---|---|
| jobs 注册表 + resume_job | agent-ops L06 | daemon 记账 + 孤儿恢复（运行层）；班次 catch-up 是调度层，两层各管一段 |
| interrupt/submit_approval | agent-ops L05 | 隔夜审批：approval 条目是它的「人不在场收发室」 |
| 幂等键 publish | agent-ops L04 | agency=act 的重放保护 + first_only 审批复用 |
| 轨迹钱包 token_usage | agent-ops L02 | 每班计量凭证，喂给时段钱包（第三层预算） |
| run summary | agent-ops L07 | 轨迹体检；v4 日报是其上的服务级聚合 |
| TaskLedger | frontier L10 | **首次接入运行时主链路**：世界增量→工作增量→下次的「已知」 |
| MemoryStore recall | frontier L01 | researcher 语义记忆与 ledger 精确结论并行注入，互不替代 |

## 5. 收益（AMBIENT_REPORT.md，确定性可复现）

| 配置 | 增量召回 | 立即打扰 | 打扰精确率 | 静默失败 | 5日token | 缺勤检出 |
|---|---|---:|---|---|---:|---|
| baseline·人肉盯梢 | 0/3 | 5 | 20% | ❌ 有 | 5000 | — |
| cron·只开调度 | 0/3 | 5 | 20% | ❌ 有 | 5000 | — |
| +watcher·增量 | 3/3 | 3 | 33% | ✅ 无 | 1075 | — |
| +judge·判级配额 | 3/3 | 1 | 100% | ✅ 无 | 1075 | — |
| full·全开 | 3/3 | 1 | 100% | ✅ 无 | 1070 | ✅ |

关键一行：**cron 档与人肉基线六指标全同**——cron 只买到出勤，买不到判断（变化检测/增量/判级才是价值所在）。诚实标注：数字为 mock 估算口径（全量 1000/增量 150×条/扫描 5），五档相对结构与真实一致；full 档退避使 Day3 小更新晚一天发现（省钱的代价，`adaptive_backoff_cap` 控制汇率）。复现：`python eval_agent/run_ambient_eval.py`。

## 6. 版本演进

```
v1 多智能体        能跑的搜索→写报告          rag/workflow 课程
v2 Deep Research   记忆/反思/CodeAct/浏览器    frontier + gui-agent 课程
v3 生产可靠        预算/熔断/幂等/审批/续跑    agent-ops 课程
v4 常驻主动        调度/变化检测/增量/判级/    ambient-agent 课程
                   收件箱/守护/时段预算/心跳
```

测试：331 项全绿（v3 的 219 + ambient 新增 112），全部离线、零真实等待（可注入时钟）、零 API。
