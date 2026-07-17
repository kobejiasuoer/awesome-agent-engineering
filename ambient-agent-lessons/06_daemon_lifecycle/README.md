# Lesson 06 — 常驻生命周期：把它跑在真实时间里

> 本课目标：**AmbientDaemon 把 L01-L05 的五个模块串成一个日夜跑、崩了爬起来、单轮失败不倒的服务**——到班→overlap 检查→扫描→研究→判级→投递→记账，全程 jobs 注册表可审计，全部时间可注入。
>
> 学完你能回答面试官那句：**「你的常驻 Agent 崩了怎么办？上一轮没跑完新一轮到了怎么办？」**——答案：恢复分两层（checkpoint 续跑管任务、missed 网格管班次），overlap 用 skip（盯梢班次天然可覆盖）。

---

## 0. 起点：五个模块，还没有服务

L01-L05 交付了调度器、watcher、增量回路、判级器、收件箱——但它们只是模块。没有一个进程**按真实时间驱动它们、在故障后重新站起来**。本课就是那个进程：

```
AmbientDaemon.run_loop()
   │  while not stop: await step(); await clock.asleep(poll)
   ▼
step()  ──── scheduler.tick() 到班（L01）
   │              │
   │        overlap 检查：同主题上一轮还在跑？──是──→ 跳过本班（记档）
   │              │否
   ▼              ▼
run_cycle() ── watcher 扫描（L02）→ 增量研究三分支（L03）
   │              → HITL 挂起检查（等审批 → approval 落箱，任务标 awaiting）
   │              → 判级+配额（L04）→ 投递收件箱（L05）→ agency 代办（L05）
   │
   └── jobs 注册表全程记账：pending → running → done / failed / awaiting
```

`code.py` Part 1 的五日实录（真实 daemon，研究步骤 mock）：

```
Day1: 到班 → researched    → 📥 进摘要（建仓）
Day2: 到班 → no_change     → 🤫 沉默
Day3: 到班 → researched    → 📥 进摘要（minor）
Day4: 到班 → researched    → ⚡ 立即通知（major 反转）
Day5: 到班 → source_failed → 🚨 告警通道
五天只打扰人 1 次；jobs 记账 5 班全部 done。
```

对照 L00 基线的同一条时间线：五个环节全靠人 → 五个环节全自动，且每个决策有档可查。

---

## 1. 三条常驻纪律

### 1.1 单轮失败不倒 daemon

`run_cycle` 里任何异常：job 标 `failed` + alert 条目落箱 + **主循环继续**。常驻服务的第一美德是「活着」——一次研究图崩溃如果能杀死 daemon，那么 daemon 的可用性 = 最脆弱下游的可用性。对照 agent-ops 的语义：那边治理「一条轨迹内」的故障（熔断/预算），本课治理「轨迹之间」的隔离（这班炸了，下班照开）。

### 1.2 恢复分两层，各管一段

| 层 | 问题 | 机制 | 来源 |
|---|---|---|---|
| 运行层 | 跑到一半的任务怎么办 | `startup()` 扫 `jobs.find_orphans()` → `resume_job` 从 checkpoint 续跑（已完成节点不重做，副作用被幂等键挡）；恢复不了标 failed，**不留僵尸 running** | agent-ops L06 资产，纯复用 |
| 调度层 | 错过的班次怎么办 | 固定班次网格的 missed 语义**天然 catch-up**：错过 N 班 → 恢复后的第一个 tick 补跑一班、`missed=N` 记档——不逐班重放（盯梢班次重放 N 遍 = 对着同一个世界扫 N 次 + 轰炸收件箱） | L01 设计在此兑现 |

### 1.3 时间全部注入

主循环 `await clock.asleep(poll)`——真实 Clock 是 `asyncio.sleep`（不阻塞事件循环），FakeClock 是拨表。于是「daemon 跑 5 天」在测试里是毫秒级（`test_run_loop_five_days_in_milliseconds`）。**这是 L00 埋下的地基在本课的总兑现**：没有可注入时钟，本课的一切不可测试。

---

## 2. overlap：上一轮没跑完，新班次到了

本课固定 **skip** 策略：检查 jobs 注册表里同主题的 `running` 任务，有则跳过本班（记档，班次照常 mark_fired 不积压）。

> 🎯 **核心认知**：策略选择取决于**班次的语义**。盯梢班次是「重看世界」——幂等、后班覆盖前班，跳过的班次损失≈0；排队（queue）反而会在慢班次后积压出连环执行 + 连环投递。queue 适合的是「每班处理不同增量」的消费型任务（如队列消费者）——那种班次漏了就真丢数据。skip/queue 之辨即「班次可覆盖吗」。

---

## 3. 优雅退出 vs 被杀

`request_stop()`（信号处理器挂这里）置停止位——主循环**跑完当前 tick 再退**，不腰斩任务。被 `kill -9` 的进程才会留下 running 孤儿等 `startup()` 恢复。两者的关系：**能优雅就别崩溃；崩溃恢复是给「没得选」的时刻准备的，不是日常退出方式**。（Windows 注意：本项目一贯用 `terminate()` 而非 SIGKILL 模拟强杀。）

---

## 4. 流派对比：常驻进程怎么托管？

| 流派 | 做法 | 取舍 |
|---|---|---|
| ① **前台进程 + 手动重启** | `python -m research_assistant.daemon` 挂终端 | ✅ 零基建、教学清楚；🚫 终端一关就死、没人守护 |
| ② **进程管理器**（systemd / NSSM / supervisor / pm2） | 平台守护 + 崩溃自动拉起 + 开机自启 | ✅ 生产正统、日志/重启策略齐全；🚫 平台各异（Windows 用 NSSM/任务计划程序），课程不绑定——`startup()` 的孤儿恢复正是为「被拉起后」准备的 |
| ③ **容器编排**（Docker restart / k8s） | 容器级守护 + 健康探针 | ✅ 与本项目 Docker 部署自然衔接（restart: unless-stopped + 心跳做 liveness）；🚫 单机盯梢用 k8s 是高射炮 |
| ④ **无常驻：外部 cron 逐班拉起** | 每班起进程跑一轮就退 | ✅ 不怕内存泄漏、进程管理最简；🚫 每班冷启动（载模型/连库）、overlap 要靠文件锁自管、进程内状态（如判级 LLM 连接）不复用 |

**本课选 ①（教学）+ 文档指路 ②③（生产）**：daemon 的内在纪律（孤儿恢复/catch-up/优雅退出）在哪种托管下都需要——托管方式解决「谁拉起我」，本课解决「被拉起之后我怎么把家收拾干净」。

---

## 5. 跑起来

```bash
cd ambient-agent-lessons/06_daemon_lifecycle
python code.py        # 零 API、零联网、零等待（5 日实录毫秒级）

# 真实常驻入口（需 API key + 五个开关）：
cd ../../portfolio-projects/research-assistant
PYTHONPATH=src python -m research_assistant.daemon --topic "Agent 框架生态动态" --max-ticks 3
```

---

## 6. 落地清单

| 文件 | 改动 | 如何验证 |
|---|---|---|
| `src/research_assistant/daemon.py` | **新增**：`AmbientDaemon`（startup 孤儿恢复 / run_cycle 全生命周期 / step overlap+catch-up / run_loop 优雅退出）+ `__main__` 常驻入口 | 见下 |
| `src/research_assistant/clock.py` | **新增**：`asleep()` 异步等待（真实=asyncio.sleep，Fake=拨表） | daemon 主循环不阻塞事件循环 |
| `src/research_assistant/config.py` | **新增**：`enable_ambient_daemon` / `daemon_poll_seconds`（默认关） | — |
| `tests/test_daemon.py` | **新增**：17 个测试（tick 语义/overlap/catch-up/投递矩阵/单轮失败不倒/HITL 挂起/孤儿恢复/僵尸清理/5 天毫秒级/优雅退出/钩子异常隔离） | `pytest tests/test_daemon.py -q` |

研究图 / service **零改动**——daemon 是纯编排层，所有能力经开关组合调用既有模块。

### 验收

```bash
cd portfolio-projects/research-assistant
python -m pytest -q          # 289 + 17 = 306 passed
python -m pytest tests/test_daemon.py -q   # 17 passed
```

---

## 7. 本课在两条主线上的位置

- **倒置主线**：**合拢课**——五个环节的倒置在同一个进程里首次全部同时成立：机器发起（tick）、机器定研究对象（changeset）、机器做增量（focus）、机器判开口（judge+quota）、机器管交付（inbox）。人只剩两件事：读收件箱、批审批。
- **注意力经济主线**：daemon 是预算的**执行者**——五日实录里人只被打扰 1 次，其余产出进摘要或沉默；机器的钱也只在有变化的日子花。但「一天到底花了多少、烧钱速度对不对、Agent 还活着吗」还没有账本和哨兵——这正是 L07（时段预算+心跳+日报）要补的最后一块。

---

## 🎯 面试话术

> 「我的常驻 Agent 有三条纪律。一，**单轮失败不倒 daemon**：任何一班研究崩溃只是 job 标 failed 加一条告警，主循环继续——常驻服务的可用性不能等于最脆弱下游的可用性。二，**恢复分两层**：跑到一半的任务靠 checkpoint 续跑（启动时扫孤儿，恢复不了的标 failed 不留僵尸）；错过的班次靠固定网格的 missed 语义补跑一班、缺勤记档，不逐班重放轰炸。三，**时间全部依赖注入**：主循环的等待走可注入时钟，5 天的常驻行为在测试里毫秒级验证。
>
> overlap 我选 skip 不选 queue——判断依据是班次语义：盯梢每班都是重看世界，后班覆盖前班，跳过损失为零；排队反而在慢班次后积压出连环轰炸。queue 只适合每班消费不同增量的任务。」
