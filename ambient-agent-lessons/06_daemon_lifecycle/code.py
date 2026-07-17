"""L06 · 常驻生命周期：把它跑在真实时间里
==================================================

本脚本演示三件事：
    Part 1（五日实录）：真实 AmbientDaemon + FakeClock + 5 日时间线——
        每天一班：到班→扫描→研究→判级→投递，五种日子五种结局。
    Part 2（崩溃之夜）：模拟进程在运行中被杀（遗留 running 孤儿 + 错过班次）
        → 重启 startup() 孤儿恢复 + 固定网格天然 catch-up。
    Part 3（overlap 与优雅退出）：上一轮没跑完新班次到了 → 跳过记档；
        request_stop 跑完当前 tick 再退。

诚实标注：
    「研究」步骤注入确定性 mock（离线硬约束）；daemon 的调度/扫描/判级/
    投递/记账/恢复全部走真实落地模块。结构性行为与真实 LLM 一致。

跑法（零外部依赖、零联网、零等待——5 天毫秒级跑完）：
    python code.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_PROJ = _REPO / "portfolio-projects" / "research-assistant"
sys.path.insert(0, str(_PROJ / "src"))
sys.path.insert(0, str(_PROJ))

import logging  # noqa: E402
logging.disable(logging.WARNING)

from eval_agent.ambient_timeline import AmbientTimeline, TOPIC  # noqa: E402
from research_assistant import config, inbox, jobs, proactivity, schedules, watcher  # noqa: E402
from research_assistant.clock import DAY_SECONDS, FakeClock  # noqa: E402
from research_assistant.daemon import AmbientDaemon  # noqa: E402

DAY = DAY_SECONDS


def _fresh_env(tag: str):
    tmp = tempfile.mkdtemp(prefix=f"ambient_l06_{tag}_")
    schedules.set_db_path_for_test(str(Path(tmp) / "schedules.db"))
    jobs.set_db_path_for_test(str(Path(tmp) / "jobs.db"))
    inbox.set_db_path_for_test(str(Path(tmp) / "inbox.db"))
    watcher.set_db_path_for_test(str(Path(tmp) / "snapshots.db"))
    proactivity.set_db_path_for_test(str(Path(tmp) / "quota.db"))
    for f in ("enable_source_watch", "enable_proactivity", "enable_inbox"):
        config.settings.__dict__[f] = True


async def scripted_research(topic, change_set, thread_id):
    """确定性 mock「研究」：按变化集三分支产简报（真实版=run_incremental 进图）。"""
    if change_set is None or not change_set.ok:
        err = getattr(change_set, "error", "unknown") if change_set else "no source"
        return {"status": "source_failed",
                "brief": f"⚠️ 没能看到信源（{err[:60]}）——不等于没有变化"}
    if change_set.is_no_change():
        return {"status": "no_change", "brief": "✅ 确认无变化：今日无需研究"}
    parts = []
    if change_set.first_scan:
        parts.append(f"🆕 建仓：{len(change_set.new_items)} 条基线结论入账")
    else:
        parts += [f"🆕 新增: {it.title}" for it in change_set.new_items]
        parts += [f"✏️ 修正: {it.title}——此前结论已不成立" for it in change_set.changed_items]
    return {"status": "researched", "brief"
            : "；".join(parts), "result": {"report": ""}}   # report 空=不触发 agency


async def demo_five_days():
    _fresh_env("run")
    print("─" * 72)
    print("Part 1 · 五日实录：一个 daemon 的一周（研究步骤 mock，其余真实）")
    print("─" * 72)
    clock = FakeClock()
    tl = AmbientTimeline(clock=clock, start_ts=clock.now())
    schedules.add_schedule(TOPIC, DAY, clock=clock)

    d = AmbientDaemon(clock=clock, fetch=tl.fetch_items, source_id="timeline",
                      llm_judge=None, run_research=scripted_research)
    print(f"注册调度：{TOPIC}（每日一班）；判级用规则降级（无 LLM，离线）\n")

    for day in range(1, 6):
        report = await d.step()
        for r in report["ran"]:
            dec = r.get("decision") or {}
            action = {"notify_now": "⚡ 立即通知", "add_to_digest": "📥 进摘要",
                      "stay_silent": "🤫 沉默"}.get(dec.get("decision"),
                      "🚨 告警通道" if r["status"] == "source_failed" else "🤫 沉默")
            print(f"  Day{day}: 到班 → {r['status']:<14} → {action}")
        clock.advance_days(1)

    print()
    print("  五天后的收件箱（人这五天只被打扰了 1 次）：")
    print(f"    ⚡ notify 未读：{inbox.unread_count(inbox.KIND_NOTIFY)}（Day4 重大反转）")
    print(f"    🚨 alert  未读：{inbox.unread_count(inbox.KIND_ALERT)}（Day5 信源故障）")
    for line in inbox.build_digest(clock=clock).splitlines():
        print(f"    {line}")
    done = jobs.list_jobs(status=jobs.STATUS_DONE)
    print(f"    jobs 记账：{len(done)} 班全部 done（可审计）")
    print()


async def demo_crash_night():
    _fresh_env("crash")
    print("─" * 72)
    print("Part 2 · 崩溃之夜：Day3 夜里进程被杀 → Day5 重启")
    print("─" * 72)
    clock = FakeClock()
    schedules.add_schedule(TOPIC, DAY, clock=clock)

    # Day1-3 正常跑两班后，模拟运行中被杀：遗留一个 running 孤儿
    j = jobs.submit_job(TOPIC, "t-crash-night")
    jobs.update_status(j["task_id"], jobs.STATUS_RUNNING)
    print(f"  Day3 23:00  运行中进程被 kill——job {j['task_id']} 卡在 running")
    clock.advance(2 * DAY)
    print("  （Day4 全天缺勤：没有进程，没有班次，没有心跳……）")

    async def fake_resume(task_id):
        jobs.update_status(task_id, jobs.STATUS_DONE, result={"resumed": True})
        return {"resumed": True}   # 真实版=service.resume_job 从 checkpoint 续跑

    d = AmbientDaemon(clock=clock, run_research=scripted_research,
                      resume_orphan=fake_resume)
    print("  Day5 09:00  重启 daemon：")
    rep = await d.startup()
    print(f"    ① 启动体检：发现 {rep['orphans_found']} 个孤儿 → 恢复 {len(rep['recovered'])} 个")
    print("       （真实恢复=同 thread_id 从 checkpoint 续跑，已完成节点不重做）")
    step = await d.step()
    print(f"    ② 首个 tick：补跑 1 班 + 缺勤记档 missed={step['caught_up_missed']}")
    print("       （固定网格天然 catch-up：错过 N 班补跑一班，不逐班重放轰炸）")
    print()
    print("  🎯 两层恢复各管一段：运行层（checkpoint 续跑）管「跑到一半的任务」，")
    print("     调度层（missed 语义）管「错过的班次」。缺勤本身 L07 心跳会告警。")
    print()


async def demo_overlap_and_stop():
    _fresh_env("ov")
    print("─" * 72)
    print("Part 3 · overlap 跳过 + 优雅退出")
    print("─" * 72)
    clock = FakeClock()
    schedules.add_schedule(TOPIC, DAY, clock=clock)
    # 模拟上一轮还没跑完（慢班次）：同主题 running job
    j = jobs.submit_job(TOPIC, "t-slow")
    jobs.update_status(j["task_id"], jobs.STATUS_RUNNING)

    d = AmbientDaemon(clock=clock, run_research=scripted_research)
    rep = await d.step()
    print(f"  新班次到点，但上一轮仍在跑 → skipped={rep['skipped']}")
    print("  （策略=skip：盯梢每班都是「重看世界」，跳过的班次下一班自动覆盖；")
    print("   排队会积压出连环轰炸——queue 变体的适用场景见练习）")
    print()

    # 优雅退出：第 2 个 tick 后 request_stop
    d2 = AmbientDaemon(clock=clock, run_research=scripted_research)
    n = {"v": 0}
    def hook():
        n["v"] += 1
        if n["v"] >= 2:
            d2.request_stop()
    d2._on_tick = hook
    await d2.run_loop(poll_seconds=DAY, max_ticks=100)
    print(f"  request_stop 后主循环在第 {d2.tick_count} tick 优雅退出（跑完当前班次，")
    print("   不腰斩任务——被腰斩的任务才需要孤儿恢复，能优雅就别崩溃）")
    print()


async def main():
    print("=" * 72)
    print("  L06 · 常驻生命周期：把它跑在真实时间里")
    print("=" * 72)
    print()
    print("L01-L05 是五个模块；本课的 AmbientDaemon 把它们串成一个日夜跑、")
    print("崩了爬起来、单轮失败不倒的服务。")
    print()
    await demo_five_days()
    await demo_crash_night()
    await demo_overlap_and_stop()
    print("=" * 72)
    print("  本课小结")
    print("=" * 72)
    print("  ① 一次 tick = 到班→overlap检查→扫描→研究→判级→投递→记账")
    print("  ② 单轮失败不倒 daemon：cycle 异常 → job=failed + alert，主循环活着")
    print("  ③ 恢复分两层：孤儿续跑（checkpoint）+ 班次 catch-up（missed 网格）")
    print("  ④ overlap=skip：盯梢班次天然可覆盖，排队反而积压轰炸")
    print("  ⑤ 全部时间注入：5 天实录毫秒级跑完——这就是 FakeClock 的全部意义")


if __name__ == "__main__":
    asyncio.run(main())
