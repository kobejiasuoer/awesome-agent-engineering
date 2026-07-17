"""常驻守护进程：把 L01-L05 串成一个跑在真实时间里的服务（Ambient L06）。

现状缺口：
    调度器（L01）、watcher（L02）、增量回路（L03）、判级（L04）、收件箱（L05）
    都是模块——没有进程把它们**串起来、日夜跑、崩了爬起来**。本模块就是那个进程。

一次 tick 的完整生命周期（ambient cycle）：
    scheduler.tick() 到班
      → overlap 检查（同主题上一轮还在跑？→ 本班跳过并记档）
      → run_cycle：
          watcher 扫描 → run_incremental 三分支（failed/no_change/researched）
          → 判级+配额（L04）→ 投递收件箱（L05）→ agency 代办（L05）
          → HITL 挂起检查（等审批 → approval 条目落箱，任务标 awaiting）
      → jobs 注册表全程记账（pending→running→done/failed/awaiting）

三条常驻纪律：
    ① 单轮失败不倒 daemon：cycle 抛任何异常 → job 标 failed + 告警条目，
       主循环继续（常驻服务的第一美德是「活着」）
    ② 崩溃恢复分两层：运行层复用 jobs.find_orphans + service.resume_job
       （agent-ops L06 资产）；调度层靠固定班次网格的 missed 语义天然 catch-up
       （错过 N 班 → 恢复后补跑一班、缺勤记档，不逐班重放）
    ③ 时间全部注入：主循环 await clock.asleep(poll)——FakeClock 下
       「跑 5 天」在测试里是毫秒级

overlap 策略（本课固定 skip，queue 变体留练习）：
    上一轮没跑完新班次到了 → 跳过本班（盯梢任务每班本来就是「重看世界」，
    跳过的班次下一班自动覆盖；排队反而会积压出连环轰炸）。
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from . import jobs
from .clock import Clock
from .config import settings
from .logging_config import get_logger
from .schedules import Scheduler

log = get_logger("daemon")


class AmbientDaemon:
    """常驻守护进程（全依赖可注入——测试/演示零真实等待、零 API）。

    Args:
        clock: 时钟（测试传 FakeClock）
        fetch: 信源 callable（watcher 语义；enable_source_watch 时必传）
        source_id: 快照命名空间
        llm_judge: 判级 LLM（None → 规则降级判级）
        run_research: async (topic, change_set, thread_id) -> dict，
            默认 incremental.run_incremental（真实图）；测试注入 mock
        resume_orphan: async (task_id) -> dict，默认 service.resume_job
        on_tick: 每次 tick 后回调（L07 挂心跳/时段预算检查）
    """

    def __init__(self, *, clock: Clock | None = None,
                 fetch: Callable[[], list] | None = None,
                 source_id: str = "default",
                 llm_judge: Any = None,
                 run_research: Callable | None = None,
                 resume_orphan: Callable | None = None,
                 on_tick: Callable[[], None] | None = None):
        self._clock = clock or Clock()
        self._fetch = fetch
        self._source_id = source_id
        self._llm_judge = llm_judge
        self._run_research = run_research
        self._resume_orphan = resume_orphan
        self._on_tick = on_tick
        self._scheduler = Scheduler(clock=self._clock)   # dispatch=None：daemon 自己跑
        self._stop = False
        self.tick_count = 0

    # ── 优雅退出 ─────────────────────────────────────────────
    def request_stop(self):
        """请求停止（信号处理器挂这里）：跑完当前 tick 再退，不腰斩任务。"""
        self._stop = True
        log.info("收到停止请求，将在当前 tick 结束后退出")

    # ── 启动序列：孤儿恢复 ───────────────────────────────────
    async def startup(self) -> dict:
        """启动即体检：上次进程死时没跑完的任务（running/interrupted）逐个恢复。

        恢复语义复用 agent-ops L06：同 thread_id 从 checkpoint 续跑，
        已完成节点不重做，已执行副作用被幂等键挡住。恢复失败标 failed
        （诚实：恢复不了就说恢复不了，不留僵尸 running）。
        """
        orphans = jobs.find_orphans()
        recovered, failed = [], []
        for o in orphans:
            try:
                resume = self._resume_orphan
                if resume is None:
                    from .service import resume_job
                    resume = resume_job
                await resume(o["task_id"])
                recovered.append(o["task_id"])
                log.info(f"孤儿任务已恢复：{o['task_id']}（{o['topic']}）")
            except Exception as e:
                jobs.update_status(o["task_id"], jobs.STATUS_FAILED,
                                   error=f"恢复失败：{e}")
                failed.append(o["task_id"])
                log.warning(f"孤儿任务恢复失败（标 failed）：{o['task_id']} → {e}")
        report = {"orphans_found": len(orphans),
                  "recovered": recovered, "recover_failed": failed}
        if orphans:
            log.info(f"启动体检：{len(orphans)} 个孤儿，恢复 {len(recovered)}，失败 {len(failed)}")
        return report

    # ── 一轮 ambient cycle ───────────────────────────────────
    async def run_cycle(self, topic: str, thread_id: str | None = None) -> dict:
        """一轮完整生命周期：扫描→研究→判级→投递→代办（各环节按开关降级）。"""
        thread_id = thread_id or f"ambient-{uuid.uuid4().hex[:8]}"
        job = jobs.submit_job(topic, thread_id)
        jobs.update_status(job["task_id"], jobs.STATUS_RUNNING)
        try:
            # ① 感知：watcher 扫描（关闭时 change_set=None → 全量研究语义）
            change_set = None
            if settings.enable_source_watch and self._fetch is not None:
                from .watcher import scan_source
                change_set = scan_source(self._source_id, self._fetch,
                                         clock=self._clock)

            # ② 研究：增量三分支（注入的 run_research 或真实 run_incremental）
            result = await self._research(topic, change_set, thread_id)
            status = result.get("status", "researched")
            brief = result.get("brief", "")

            # ③ HITL 挂起检查：跑到审批门闸 → approval 条目落箱，任务标 awaiting
            if settings.enable_hitl and settings.enable_inbox:
                pending = self._check_awaiting(thread_id)
                if pending:
                    from .inbox import file_approval_request
                    file_approval_request(thread_id, topic,
                                          str(pending)[:300], clock=self._clock)
                    jobs.update_status(job["task_id"], jobs.STATUS_AWAITING_APPROVAL)
                    log.info(f"任务挂起等审批（隔夜可恢复）：{thread_id}")
                    return {"topic": topic, "thread_id": thread_id,
                            "status": "awaiting_approval"}

            # ④ 开口决策 + 投递（按开关降级；沉默 = 什么都不投）
            decision = self._deliver(topic, status, brief, thread_id)

            # ⑤ 代办动作（agency ladder；notify 级 = 不碰）
            report_text = (result.get("result") or {}).get("report", "")
            if status == "researched" and report_text and settings.enable_inbox:
                from .inbox import apply_agency
                apply_agency(topic, report_text, thread_id, clock=self._clock)

            jobs.update_status(job["task_id"], jobs.STATUS_DONE,
                               result={"status": status})
            return {"topic": topic, "thread_id": thread_id,
                    "status": status, "decision": decision}
        except Exception as e:
            # 常驻纪律①：单轮失败不倒 daemon——记账、告警、继续活着
            jobs.update_status(job["task_id"], jobs.STATUS_FAILED, error=str(e))
            log.warning(f"cycle 失败（daemon 继续运行）：{topic} → {type(e).__name__}: {e}")
            if settings.enable_inbox:
                try:
                    from .inbox import KIND_ALERT, add_entry
                    add_entry(KIND_ALERT, topic, f"班次失败：{topic}",
                              f"{type(e).__name__}: {e}", clock=self._clock)
                except Exception:
                    pass
            return {"topic": topic, "thread_id": thread_id,
                    "status": "failed", "error": str(e)}

    async def _research(self, topic, change_set, thread_id) -> dict:
        if self._run_research is not None:
            return await self._run_research(topic, change_set, thread_id)
        if change_set is not None and settings.enable_incremental_run:
            from .incremental import run_incremental
            return await run_incremental(topic, change_set, thread_id)
        # watch/增量关闭：现状全量研究语义
        from .service import invoke
        result = await invoke(topic, thread_id)
        return {"status": "researched", "brief": result.get("report", "")[:500],
                "result": result}

    def _check_awaiting(self, thread_id: str):
        try:
            from .service import is_awaiting_approval
            return is_awaiting_approval(thread_id)
        except Exception:
            return None

    def _deliver(self, topic, status, brief, thread_id) -> dict | None:
        """开口决策与投递（各开关的降级矩阵）。

        source_failed → 健康告警通道（alert），不进内容判级（通道语义不同）
        no_change     → 沉默（不判级、不投递——最常见的正确结局）
        researched    → enable_proactivity 时判级+配额；关时保守全进 digest
        """
        if not settings.enable_inbox:
            return None
        from .inbox import KIND_ALERT, KIND_DIGEST, add_entry, deliver
        if status == "source_failed":
            add_entry(KIND_ALERT, topic, f"信源故障：{topic}", brief,
                      thread_id=thread_id, clock=self._clock)
            return None
        if status == "no_change":
            return None
        if settings.enable_proactivity:
            from .proactivity import classify_change, decide
            judgement = classify_change(brief, llm=self._llm_judge)
            decision = decide(judgement, clock=self._clock)
            deliver(decision, topic, brief, thread_id=thread_id, clock=self._clock)
            return decision
        add_entry(KIND_DIGEST, topic, f"[{topic}] 本轮产出", brief,
                  thread_id=thread_id, clock=self._clock)
        return None

    # ── tick 与主循环 ────────────────────────────────────────
    async def step(self) -> dict:
        """单步：触发到班调度并逐个跑 cycle（测试/演示手动驱动的入口）。"""
        fired = self._scheduler.tick()
        report = {"fired": len(fired), "ran": [], "skipped": [], "caught_up_missed": 0}
        for f in fired:
            topic = f["topic"]
            # overlap 检查：同主题上一轮还在跑 → 本班跳过（记档，不排队）
            running = [j for j in jobs.list_jobs(status=jobs.STATUS_RUNNING)
                       if j["topic"] == topic]
            if running:
                log.warning(f"班次跳过（overlap）：{topic} 上一轮仍在运行")
                report["skipped"].append({"topic": topic, "reason": "overlap"})
                continue
            if f["missed"]:
                # 固定网格的天然 catch-up：错过 N 班 → 本班补跑一次，缺勤记档
                report["caught_up_missed"] += f["missed"]
            report["ran"].append(await self.run_cycle(topic))
        self.tick_count += 1
        if self._on_tick is not None:
            try:
                self._on_tick()
            except Exception as e:
                log.warning(f"on_tick 回调失败（不影响主循环）：{e}")
        return report

    async def run_loop(self, poll_seconds: float | None = None,
                       max_ticks: int | None = None):
        """常驻主循环：tick → asleep(poll) → tick……直到 request_stop。

        max_ticks 供测试/演示限步；FakeClock 下 asleep=拨表（零真实等待）。
        """
        poll = poll_seconds if poll_seconds is not None else settings.daemon_poll_seconds
        ticks = 0
        log.info(f"daemon 主循环启动（poll={poll}s）")
        while not self._stop:
            await self.step()
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            await self._clock.asleep(poll)
        log.info(f"daemon 主循环退出（共 {ticks} tick，优雅收尾）")


if __name__ == "__main__":  # pragma: no cover
    # 极简常驻入口（真实运行需 API key + 开关：
    #   ENABLE_SCHEDULES/SOURCE_WATCH/INCREMENTAL_RUN/PROACTIVITY/INBOX=true）
    # 用法：PYTHONPATH=src python -m research_assistant.daemon --topic "主题"
    import argparse
    import asyncio
    import sys as _sys
    try:
        _sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    from . import schedules as _schedules

    p = argparse.ArgumentParser(description="常驻研究守护进程（Ambient L06）")
    p.add_argument("--topic", required=True)
    p.add_argument("--interval-hours", type=float, default=None)
    p.add_argument("--max-ticks", type=int, default=None)
    args = p.parse_args()

    interval = (args.interval_hours or settings.default_scan_interval_hours) * 3600
    if not any(s["topic"] == args.topic for s in _schedules.list_schedules()):
        _schedules.add_schedule(args.topic, interval)

    async def _main():
        d = AmbientDaemon()
        await d.startup()
        await d.run_loop(max_ticks=args.max_ticks)

    asyncio.run(_main())
