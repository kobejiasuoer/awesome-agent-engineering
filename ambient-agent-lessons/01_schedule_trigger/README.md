# Lesson 01 — 触发与调度：谁来叫醒 Agent

> 本课目标：**手写最小调度器（sqlite 调度表 + 固定班次网格 + 可注入时钟），让「发起」这个环节第一次不需要人**——L00 基线「人忘了问 = 全盲」的那一环，从此由机器负责。
>
> 学完你能回答面试官那句：**「后台任务不就是加个 cron 吗？」**——答案是：cron 只解决「到点跑」，解决不了 missed 语义（错过几班要可数）、与 Agent 状态同生态（jobs/checkpoint）、以及可测试性（时间必须能快进）。

---

## 0. 起点：L00 基线的第①环

`baseline_ambient.json` 的 `skipped_day_probe` 记录了：人忘了问 Day4（重大进展日），系统全盲——**会话式没有触发器，「发起」完全押在人的记性上**。本课补的就是这一环：

```
 触发器三型（统一为「谁来叫醒 Agent」的抽象）：
   ① 时间触发（本课）：每天/每 N 小时扫一次     —— 盯梢任务的主力
   ② 事件触发（L02 接入）：信源变化了才醒       —— 需要先有变化检测
   ③ 条件触发（L07 用到）：预算恢复后补跑、退避到点重试
```

---

## 1. 时间必须是依赖注入（本课程的命根子）

常驻 Agent 的一切行为由时间驱动：调度到点、间隔退避、心跳过期、缺勤判定。如果代码里直接写 `time.time()` / `time.sleep()`：

- 测试「5 天的调度行为」要真等 5 天——不可测试；
- 演示脚本要真 sleep——违反课程「零真实等待」硬约束。

所以 `clock.py`（L00 已落地）把 `now()`/`sleep()` 做成可替换对象：

```python
class Clock:                    # 生产：真实时间
    def now(self): return time.time()
    def sleep(self, s): time.sleep(s)

class FakeClock(Clock):         # 测试/演示：快进
    def now(self): return self._now
    def sleep(self, s): self._now += s      # sleep = 拨表，不等待
    def advance_days(self, d): self._now += d * 86400
```

> 🎯 **核心认知**：`FakeClock.sleep()` 不等待而是**把时钟拨快**——这让 L06 的 daemon 主循环（`while: tick; sleep(poll)`）在测试里原样跑、秒级完成。**可注入时钟之于本课程，等于故障注入器之于 agent-ops 课程**：没有它，整门课不可验收。

调度器所有「到点没」的判断走 `clock.now()`，并提供手动 `tick()` 驱动——测试里 `advance_days(1); tick()` 就是「过了一天」。

---

## 2. 固定班次网格：晚触发不漂班，missed 可数

调度器最容易写错的地方是「触发后下一班排在哪」。两种语义：

```python
# 漂移间隔（实现最简，常见错误）
next_run_at = 实际触发时刻 + interval

# 固定班次（本课选择）
missed = (now - next_run_at) // interval        # 错过了几个完整周期
next_run_at = 旧 next_run_at + (missed+1) × interval   # 班次网格不动
```

`code.py` Part 1 的分岔演示（daemon 每天晚 6 小时才 tick）：

```
     tick 时刻       固定班次·下一班    漂移间隔·下一班
  Day1 +6h            1.00 天            1.25 天
  Day4 +6h            4.00 天            4.25 天      ← 每晚 6h 漂 6h
```

漂移语义跑一个月，「每天 0 点扫描」会变成「每天中午扫描」；而且 now 与班点脱钩后，**「错过了几班」无从计算**。固定网格的 `missed` 是自然产物——这正是 L06 catch-up（缺勤补跑）的地基：补几班、从哪班补，都要先数得清。

> 💡 **暂停 ≠ 缺勤**：`enabled=false` 是人主动停（休假），期间不触发也不算 missed；缺勤是「进程死了没人 tick」——那是 L07 心跳要抓的事。两者语义不同，档案里也分开记。

---

## 3. 职责边界：调度器只管叫醒，不管跑

```
Scheduler.tick()
    │ 找到期调度（enabled 且 next_run_at ≤ now）
    │ mark_fired（先记账：晚点/重复 tick 不会重复触发同一班）
    ▼
dispatch(schedule)  ——缺省实现 make_job_dispatch()：
    │ jobs.submit_job(topic)   ← 只登记 pending 任务
    ▼
（到此为止。执行、崩溃恢复、审批全部是 jobs + checkpoint 的事——agent-ops L06 资产）
```

> 🎯 **核心认知**：调度器不 invoke 图、不碰 checkpoint。「什么时候该跑」和「怎么跑」是两层——跑挂了走 `recover_orphans`（运行层），班次错过了走 catch-up（调度层），两层各管一段，L06 会把它们接起来。
>
> 另一个细节：`mark_fired` **先于** dispatch——dispatch 抛错不会让这一班被重复触发（至多一次语义）。反过来（先 dispatch 后记账）是至少一次语义，重复执行的锅要靠幂等键兜——我们已经有 L04 幂等资产，但「调度层至多一次 + 副作用幂等」双保险优于「至少一次裸奔」。

---

## 4. 流派对比：定时跑一个任务，有几种做法？

| 流派 | 做法 | 取舍 |
|---|---|---|
| ① **OS cron / 任务计划程序** | crontab 每天拉起 `cli.py` | ✅ 零开发、进程级隔离、机器重启自动恢复；🚫 与 Agent 状态隔离（不知道 jobs/checkpoint 的存在）、无 missed 语义（关机错过就错过）、Windows/Linux 写法不同、**没法在测试里快进时间** |
| ② **进程内轮询调度器**（本课） | sqlite 调度表 + `tick()` 轮询 + 可注入时钟 | ✅ 与 jobs/checkpoint 同生态、missed 可数、固定网格、FakeClock 秒测 5 天；🚫 进程死了调度也停（→ L06 守护 + L07 心跳补位） |
| ③ **工作流引擎**（Temporal/Airflow） | 平台管调度+重试+可观测 | ✅ 生产正统、跨机器、历史完备；🚫 重基建（自建集群/付费），单机盯梢任务用它是高射炮打蚊子——讲概念，不实现 |
| ④ **托管定时**（云函数 / OpenAI scheduled tasks） | 平台到点拉起你的代码/Agent | ✅ 免运维；🚫 状态全靠外存、策略不可编程（何时开口/怎么增量平台说了算）、锁定 |

**选 ② 的理由**：教学要看清机制（missed/网格/时钟注入都是手写才懂的东西）；工程上单机常驻服务 + sqlite 生态自洽。规模上去了迁 ③，语义平移（调度表 → workflow 定义）。

---

## 5. 跑起来

```bash
cd ambient-agent-lessons/01_schedule_trigger
python code.py        # 零 API、零联网、零等待
```

Part 2 实际输出（真实落地模块 + FakeClock 快进 5 日）：

```
  Day1: ⏰ 触发 → 登记任务 job-xxx（status=pending，执行留给 L06 daemon）
  Day2: ⏰ 触发 → 登记任务 job-xxx（…）
  Day3: —— 不触发（已暂停）
  Day4: ⏰ 触发（补记缺勤 1 班） → 登记任务 job-xxx（…）
  Day5: ⏰ 触发 → 登记任务 job-xxx（…）
5 日小结：触发并登记 4 个 pending 任务；missed_count=1
```

---

## 6. 落地清单

| 文件 | 改动 | 如何验证 |
|---|---|---|
| `src/research_assistant/schedules.py` | **新增**：调度表 CRUD + `Scheduler.tick()`（固定网格 + missed）+ `make_job_dispatch`（触发=登记 pending job）+ 管理入口（`PYTHONPATH=src python -m research_assistant.schedules add/list/tick`） | 见下 |
| `src/research_assistant/config.py` | **新增**：`enable_schedules` / `default_scan_interval_hours`（默认关） | `.env` 设 `ENABLE_SCHEDULES=true`（daemon 接线在 L06） |
| `tests/test_schedules.py` | **新增**：13 个测试（网格/missed/暂停/dispatch/至多一次） | `pytest tests/test_schedules.py -q` |

`cli.py` / 研究图 / service **零改动**——调度器是图外的独立层，`enable_schedules` 关闭时系统行为与现状完全一致。

### 验收

```bash
cd portfolio-projects/research-assistant
python -m pytest -q                       # 219 + 13 = 232 passed
python -m pytest tests/test_schedules.py -q   # 13 passed

# 手动驱动一次（临时体验；正式常驻入口在 L06 daemon）
PYTHONPATH=src python -m research_assistant.schedules add --topic "Agent 框架生态动态" --interval-hours 24
PYTHONPATH=src python -m research_assistant.schedules tick
PYTHONPATH=src python -m research_assistant.schedules list
```

---

## 7. 本课在两条主线上的位置

- **倒置主线**：五环节倒过来的第①环——「发起」从人的记性交给调度器；忘了问=全盲从此不成立（进程活着就有班次，进程死了 L07 心跳会叫）。
- **注意力经济主线**：本课花的是**机器的钱**（到点就跑）还没管**人的注意力**——每班跑完该不该说话，是 L04 的事；每班该不该全量研究，是 L02/L03 的事。调度器只是把「花钱的机会」规律化了，怎么少花，后面三课管。

---

## 🎯 面试话术

> 「我的常驻 Agent 调度器是手写的：sqlite 调度表 + 固定班次网格 + 可注入时钟。三个设计点：
> 一，**时间是依赖注入**——所有到点判断走 clock.now()，测试里 FakeClock 快进，5 天的调度行为秒级验证；
> 二，**固定网格不漂班**——下一班 = 旧班点 + (missed+1)×间隔，晚触发不让班次后漂，而且错过几班天然可数，这是缺勤补跑的地基；
> 三，**调度器只管叫醒**——触发即登记 pending 任务，mark_fired 先于 dispatch 保证至多一次，执行和崩溃恢复完全复用 jobs 注册表 + checkpoint。
> 为什么不用 cron？cron 与 Agent 状态隔离、没有 missed 语义、也没法在测试里快进时间——它解决『到点跑』，解决不了『错过怎么办』。」
