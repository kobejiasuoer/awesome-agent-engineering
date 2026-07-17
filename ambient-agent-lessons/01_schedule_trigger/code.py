"""L01 · 触发与调度：谁来叫醒 Agent
==================================================

本脚本演示两件事：
    Part 1（内存 mini 模型）：同一晚点场景下「固定班次 vs 漂移间隔」两种
        调度语义的分岔——为什么本课选固定班次（missed 可数、班次不漂）。
    Part 2（真实落地模块）：驱动 research_assistant.schedules，用 FakeClock
        快进 5 个模拟日——注册即建仓、每日触发、暂停不触发、错过班次记 missed、
        触发即登记 pending job（调度器只管叫醒，不管跑）。

为什么零真实等待还能测「5 天的调度」：
    时间是依赖注入（clock.py）。调度器所有「到点没」的判断走 clock.now()，
    FakeClock.advance_days(1) 一行就是「过了一天」。
    ——可注入时钟之于本课程，等于故障注入器之于 agent-ops 课程。

跑法（零外部依赖、零联网、零等待）：
    python code.py
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_PROJ = _REPO / "portfolio-projects" / "research-assistant"
sys.path.insert(0, str(_PROJ / "src"))

from research_assistant.clock import FakeClock, DAY_SECONDS  # noqa: E402

DAY = DAY_SECONDS


# ════════════════════════════════════════════════════════════
# Part 1 · 固定班次 vs 漂移间隔（内存 mini 模型）
# ════════════════════════════════════════════════════════════

@dataclass
class MiniSchedule:
    """最小调度：只有下一班时刻和间隔。"""
    next_run_at: float
    interval: float
    fires: int = 0
    missed: int = 0


def tick_fixed_grid(s: MiniSchedule, now: float) -> bool:
    """固定班次：next = 旧 next + (missed+1)×interval（网格稳定）。"""
    if now < s.next_run_at:
        return False
    missed = int((now - s.next_run_at) // s.interval)
    s.next_run_at = s.next_run_at + (missed + 1) * s.interval
    s.fires += 1
    s.missed += missed
    return True


def tick_drift(s: MiniSchedule, now: float) -> bool:
    """漂移间隔：next = 实际触发时刻 + interval（实现最简，班次后漂）。"""
    if now < s.next_run_at:
        return False
    s.next_run_at = now + s.interval    # ← 唯一区别：从「触发时刻」起算
    s.fires += 1
    return True


def demo_grid_vs_drift():
    print("─" * 72)
    print("Part 1 · 同一晚点场景：固定班次 vs 漂移间隔")
    print("─" * 72)
    print("场景：每天 0 点一班；daemon 每次都晚 6 小时才 tick（进程忙/机器慢）。")
    print()
    start = 0.0
    fixed = MiniSchedule(next_run_at=start, interval=DAY)
    drift = MiniSchedule(next_run_at=start, interval=DAY)

    print(f"{'tick 时刻':>12} {'固定班次·下一班':>16} {'漂移间隔·下一班':>16}")
    now = start
    for day in range(4):
        now = start + day * DAY + 0.25 * DAY   # 每天晚 6h tick
        tick_fixed_grid(fixed, now)
        tick_drift(drift, now)
        print(f"  Day{day+1} +6h   {fixed.next_run_at/DAY:>11.2f} 天 "
              f"{drift.next_run_at/DAY:>13.2f} 天")
    print()
    print(f"  4 天后：固定班次的班点仍是整数天（0/1/2/3/4…不漂）；")
    print(f"  漂移间隔的班点已经漂到 {drift.next_run_at/DAY:.2f} 天——每晚 6h 漂 6h，")
    print(f"  跑一个月「每天 0 点扫描」会变成「每天中午扫描」，且 missed 无从谈起。")
    print(f"  固定班次的 missed 可数（本演示={fixed.missed}），这是 L06 catch-up 的地基。")
    print()


# ════════════════════════════════════════════════════════════
# Part 2 · 真实落地模块：5 日快进演示
# ════════════════════════════════════════════════════════════

def demo_real_module():
    import logging
    logging.getLogger().setLevel(logging.ERROR)  # 演示输出干净些（不看 INFO 流水）

    from research_assistant import jobs, schedules
    from research_assistant.schedules import Scheduler, make_job_dispatch

    # 演示用临时库（不污染项目目录；测试同款隔离手法）
    tmp = tempfile.mkdtemp(prefix="ambient_l01_")
    schedules.set_db_path_for_test(str(Path(tmp) / "schedules.db"))
    jobs.set_db_path_for_test(str(Path(tmp) / "jobs.db"))

    print("─" * 72)
    print("Part 2 · 真实模块：注册盯梢调度，FakeClock 快进 5 个模拟日")
    print("─" * 72)

    clock = FakeClock()
    sch = schedules.add_schedule("Agent 框架生态动态", DAY, clock=clock)
    print(f"注册调度：{sch['schedule_id']}  间隔=1天  首班=注册即到期（先建仓）")
    scheduler = Scheduler(clock=clock, dispatch=make_job_dispatch())

    for day in range(1, 6):
        # Day3 演示「主动暂停」（休假：不触发也不算缺勤）
        if day == 3:
            schedules.set_enabled(sch["schedule_id"], False)
        if day == 4:
            schedules.set_enabled(sch["schedule_id"], True)

        fired = scheduler.tick()
        if fired:
            f = fired[0]
            job = f["dispatch_result"]
            missed_note = f"（补记缺勤 {f['missed']} 班）" if f["missed"] else ""
            print(f"  Day{day}: ⏰ 触发{missed_note} → 登记任务 {job['task_id']}"
                  f"（status={job['status']}，执行留给 L06 daemon）")
        else:
            state = "已暂停" if not schedules.get_schedule(sch["schedule_id"])["enabled"] else "未到班"
            print(f"  Day{day}: —— 不触发（{state}）")
        clock.advance_days(1)

    s = schedules.get_schedule(sch["schedule_id"])
    pending = jobs.list_jobs(status=jobs.STATUS_PENDING)
    print()
    print(f"5 日小结：触发并登记 {len(pending)} 个 pending 任务；"
          f"missed_count={s['missed_count']}（Day4 恢复时补记了暂停后错过的班次）")
    print("注意：调度器全程没有 invoke 研究图——「什么时候叫醒」和「怎么跑」是两层，")
    print("     执行/崩溃恢复完全复用 jobs 注册表 + checkpoint（agent-ops L06 资产）。")
    print()


def main():
    print("=" * 72)
    print("  L01 · 触发与调度：谁来叫醒 Agent")
    print("=" * 72)
    print()
    print("L00 基线的第①环缺口：一切开始于人发消息——人忘了问 = 全盲。")
    print("本课把「发起」这个环节第一次交给机器：手写调度器 + 可注入时钟。")
    print()
    demo_grid_vs_drift()
    demo_real_module()
    print("=" * 72)
    print("  本课小结")
    print("=" * 72)
    print("  ① 时间必须依赖注入：FakeClock 快进让「5 天的调度」秒级可测（零等待）")
    print("  ② 固定班次网格：晚触发不漂班、missed 可数（L06 catch-up 的地基）")
    print("  ③ 调度器只管叫醒：触发=登记 pending job，跑/恢复复用现有资产")
    print("  ④ 暂停 ≠ 缺勤：enabled=false 是主动停；缺勤（进程死了没 tick）L07 用心跳抓")


if __name__ == "__main__":
    main()
