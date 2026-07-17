# Lesson 09 — 毕业整合：research-assistant v4（常驻主动）定稿

> 本课目标：**八机制全开跑通端到端的「v4 的一周」，定稿 research-assistant v4，注册课程十**——全仓 README、架构文档、测试数全部对齐真值。
>
> 学完你能回答面试官那句：**「把你这个 Agent 系统从头到尾讲一遍。」**——四个版本、两条主线、一张收益矩阵。

---

## 0. 全机制协同的一周（`code.py` 实录）

```
Day1 09:00 首启体检：孤儿 0；缺勤 False（首次启动，无心跳历史）
Day1        班次 → researched    → 📥 进摘要（建仓，minor）
Day2        班次 → no_change     → 🤫 沉默（哈希层确认，零研究成本）
Day3        （自适应退避中，本日无班——小更新将晚一天发现，L08 记录过的省钱代价）
Day3 23:00  💀 进程被杀（没有优雅退出）
Day4 09:00  重启体检：缺勤 True（gap 24h > 6h）→ 🚨 告警落箱
Day4        班次 → researched    → ⚡ 立即通知（Day3+Day4 同班发现，✏️ 触发 major）
Day5        班次 → source_failed → 🚨 告警通道（没能看到 ≠ 没有变化）

一周收件箱：⚡×1（正中重大反转）+ 📥×1 + 🚨×2；花费 1050 vs 基线 5000；4 班 done 可审计。
```

一段 40 行的剧本里，十门课程的机制各就各位：调度触发（L01）、哈希确认无变化（L02）、增量焦点与 ✏️ 修正（L03）、判级+配额（L04）、五通道收件箱（L05）、崩溃恢复与补班（L06）、退避/心跳/缺勤/时段账（L07）——而收益数字由 L08 的矩阵背书。

---

## 1. v4 定稿：八机制门禁架构

```
                        ┌────────────── AmbientDaemon（L06 主循环）──────────────┐
                        │  startup: 孤儿恢复 + 缺勤体检          每 tick: 心跳     │
  [L01 调度器]──到班──→ │  [L07 时段预算门] → [L02 watcher] → [L03 增量三分支]    │
   固定网格+missed      │        pause 挡班      哈希 diff      focus→研究图       │
   （自适应退避 L07）    │                                          │              │
                        │  [L04 判级+配额] ← 增量简报 ←────────────┘              │
                        │        │                                                │
                        │  [L05 收件箱] ← notify/digest/alert/approval/proposal   │
                        └────────────────────────────────────────────────────────┘
                                     研究图本体（v3 双层图 + 七机制治理）零改动
```

| # | 机制 | 开关 | 一句话 |
|---|---|---|---|
| 1 | 调度触发 | `enable_schedules` | 固定班次网格 + missed 可数 + 可注入时钟 |
| 2 | 变化检测 | `enable_source_watch` | item 哈希快照 diff；failed ≠ 空变化集 |
| 3 | 增量研究 | `enable_incremental_run` | 焦点即子题 + 旧结论注入 + ✏️ 修正简报 |
| 4 | 打扰判级 | `enable_proactivity` | major/minor/none + 宁攒勿丢 + 每日配额 |
| 5 | 收件箱 | `enable_inbox` | 五通道交付 + 隔夜审批 + agency 三级 |
| 6 | 常驻守护 | （daemon 入口） | 单轮失败不倒 + 两层恢复 + overlap skip |
| 7 | 时段预算 | `enable_period_budget` | 第三层钱包：pause 挡班不打断 |
| 8 | 退避+心跳 | `enable_adaptive_scan` / `enable_heartbeat` | 安静降频 + 缺勤可检出 + 日报 |

**纯净跑零税**：八开关默认全关，关态行为与 v3 逐字节一致（331 项测试含关态回归）。研究图本体零改动——常驻层全部长在图的外面。

---

## 2. 两条主线的收官陈词

- **范式倒置主线**：五个环节（谁发起/研究什么/谁 diff/何时开口/谁守着）逐课从人转给机器。L08 的「cron 档六指标与基线全同」一行是这条主线的证明：**倒置 ≠ 定时自动化**——cron 只倒置了第一环，价值藏在后四环里。
- **注意力经济主线**：常驻 Agent 花两种别人的钱——用户的注意力（判级+配额+分通道管住：5 天 1 次打扰、精确率 100%）和睡觉时的 token（变化检测+增量+退避+时段钱包管住：-79%）。两本账都进日报，可审计。

## 3. 版本演进：两条产品线对称收官

```
kb-qa：            RAG（v1）→ 运维就绪（v2）→ 多模态文档（v3）
research-assistant：多智能体（v1）→ Deep Research（v2）→ 生产可靠（v3）→ 常驻主动（v4）
```

v4 的定位一句话：**从「问了才答的专家」变成「一直在岗、知道什么时候该开口的同事」**。

---

## 4. 落地清单（本课=注册课）

| 文件 | 改动 |
|---|---|
| `ambient-agent-lessons/09_capstone/` | 本三件套（端到端一周实录） |
| `portfolio-projects/research-assistant/docs/ambient-agent.md` | **新增**：v4 架构文档（八机制全景 + 开关矩阵 + 数据流 + 边界表） |
| `portfolio-projects/research-assistant/README.md` | **新增** v4 章节 + 版本演进 + 测试数 331 校准 |
| 根 `README.md` / `README.en.md` | 课程十注册：徽章 105 节 / 474 测试、路线图、课程表、目录、作品行 |
| `.github/ISSUE_TEMPLATE/bug-report.yml` | 下拉加 Ambient agent lessons |
| `CHANGELOG.md` | Unreleased·Added 记一笔 |

### 验收

```bash
cd portfolio-projects/research-assistant && python -m pytest -q   # 331 passed
cd ../knowledge-base-qa && python -m pytest -q                    # 143 passed
# 全仓 474；徽章/表格与真值一致
cd ../../ambient-agent-lessons/09_capstone && python code.py      # 一周实录
```

---

## 🎯 面试话术（v4 总集）

> 「我的研究助手走了四个版本：v1 用 LangGraph 搭多智能体并行研究；v2 加了记忆、反思、代码解释器、浏览器取证，变成深度研究智能体；v3 上了生产可靠性——步数成本预算、熔断、幂等、审批、断点续跑，混沌评估成功率 33%→100%；v4 把它从会话式变成常驻式——调度器叫醒、变化检测决定研究什么、增量回路只研究变化、判级配额决定何时开口、收件箱异步交付、daemon 守生命周期、时段预算和心跳管睡觉时的钱和命。
>
> 每一步都有数字：v4 的收益矩阵拿同一条 5 日时间线量的——cron 档和人肉基线六指标一格不动，证明 cron 只买到出勤；全开档 token 省 79%、打扰从 5 次降到 1 次且正中重大反转、信源故障不再冒充结论、daemon 死了重启即告警。八个开关默认全关，关态与 v3 逐字节一致——机制是给需要的人开的，不是税。」
