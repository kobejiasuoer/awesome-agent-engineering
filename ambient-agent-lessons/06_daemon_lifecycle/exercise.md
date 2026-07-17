# L06 练习

> 改 `code.py` 或 `research_assistant/daemon.py`，运行观察变化。零联网、零等待。

---

## 练习 1：实现 queue 变体，找到它翻车的场景（设计实验类）

本课 overlap 固定 skip。现在把另一条路走一遍：

1. 给 `AmbientDaemon` 加 `overlap_policy` 参数（`"skip"` | `"queue"`）：queue 模式下，overlap 的班次不跳过，而是记入 `self._pending_cycles`，当前轮结束后补跑。
2. **实验设计**：模拟「慢班次」——`run_research` 里 `await clock.asleep(2.5 * DAY)`（假装一班跑 2.5 天），调度间隔仍 1 天，跑 10 个模拟日。
3. **预期**：skip 版跑 ~4 班（每班之间自然间隔）；queue 版积压出「连续补跑」——第 10 天一口气跑掉积压的班次，收件箱在几分钟内收到连环投递。
4. **思考**：什么任务该用 queue？（每班消费**不同增量**、漏班=丢数据的消费型任务。）盯梢为什么天然适合 skip？（每班重看世界，后班覆盖前班。）

**验收**：两种策略的班次执行时间线对比 + 一句话判据「班次可覆盖吗」。

---

## 练习 2：设计实验——「单轮失败不倒」的边界（取舍类）

daemon 把 cycle 异常吞掉继续跑。但有一类失败不该被吞：**连续失败**。

1. **假设**：信源永久搬家（404）后，daemon 会每天失败一次、每天发一条 alert——一周后收件箱里 7 条一模一样的告警（告警疲劳，L04 的教训在系统通道重演）。
2. **实验设计**：`run_research` 恒抛异常，跑 7 个模拟日，数 alert 条目。
3. 修复：给 daemon 加连续失败计数——同主题连续失败 ≥3 次后：(a) 告警去重（只在第 1、3 次和每第 10 次发）；(b) 或自动 `set_enabled(schedule, False)` 并发一条「已暂停，需人工介入」的 alert。
4. **思考**：(b) 是 Agent 自己关掉自己的调度——这在 agency ladder（L05）里属于哪一级的动作？要不要走 propose？

**验收**：7 日 alert 从 7 条降到 ≤3 条；说清「自动暂停调度」的自主级别归属。

---

## 练习 3：把 daemon 托管到你的操作系统（动手类，平台相关）

选你的平台把教学入口变成真守护：

- **Windows**：任务计划程序（开机启动 + 失败重启），或 NSSM 包装 `python -m research_assistant.daemon`。
- **Linux**：写一个 systemd unit（`Restart=on-failure`，`ExecStop` 发 SIGTERM 触发 `request_stop` 优雅退出）。
- **Docker**：compose 里加 `restart: unless-stopped`。

**验收**：kill 掉进程后平台自动拉起，且拉起后日志里能看到 `startup()` 的孤儿体检行——「谁拉起我」交给平台，「被拉起后收拾家」是 daemon 自己的（这就是两者的分工）。

---

## 练习 4：思考题——为什么 HITL 挂起不算「失败」（语义类）

`run_cycle` 里任务等审批时标 `awaiting_approval` 并 return，而不是走 failed 分支。

1. **思考**：awaiting 和 failed 的三个语义差异——谁来解除（人 vs 重试）？占不占 overlap 检查（awaiting 的任务还算「在跑」吗——本课实现里它不算 running，下一班照开；对吗？想想同主题挂着一个待审批发布、新班次又研究出新报告的场景）？孤儿恢复该不该碰它（startup 恢复 running/interrupted，awaiting 该被 resume 吗——不该，resume 它等于替人审批）？
2. 检查 `jobs.find_orphans` 的查询：它扫 `running/interrupted`，恰好不含 `awaiting_approval`——这是巧合还是设计？（agent-ops L06 写下这个查询时给出的理由是什么？去读 jobs.py 的注释。）

**验收**：一句话说清「awaiting 是人的队列，failed/orphan 是机器的队列——恢复机制只能碰机器的队列」。
