"""L07 · 时段预算与常驻可观测：睡觉时的钱和心跳
==================================================

本脚本演示四件事：
    Part 1（时段钱包）：一天多班累计花费 → ok/degrade/pause 三态 →
        pause 挡住下一班，次日自动恢复。
    Part 2（自适应扫描）：连续无变化 → 间隔 ×2/×4/×8（封顶）；
        一有变化立即回基础网格；信源故障不动退避（没看到≠世界安静）。
    Part 3（心跳与缺勤）：daemon 每 tick 一笔心跳；被杀两天后重启，
        启动体检发现缺勤 → 告警落箱（安静和死了必须可区分）。
    Part 4（日报）：一天一行服务体检——班次/花费/打扰/告警/心跳聚合。

跑法（零外部依赖、零联网、零等待）：
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

import logging  # noqa: E402
logging.disable(logging.WARNING)

from research_assistant import (  # noqa: E402
    config, inbox, jobs, period_budget, schedules, watcher, proactivity,
)
from research_assistant.clock import DAY_SECONDS, FakeClock  # noqa: E402
from research_assistant.daemon import AmbientDaemon  # noqa: E402
from research_assistant.period_budget import (  # noqa: E402
    add_usage, beat, build_daily_report, check_absence, check_budget,
    note_scan_result,
)
from research_assistant.proactivity import day_key  # noqa: E402

DAY = DAY_SECONDS


def _fresh_env(tag: str, **flags):
    tmp = tempfile.mkdtemp(prefix=f"ambient_l07_{tag}_")
    period_budget.set_db_path_for_test(str(Path(tmp) / "period.db"))
    schedules.set_db_path_for_test(str(Path(tmp) / "schedules.db"))
    jobs.set_db_path_for_test(str(Path(tmp) / "jobs.db"))
    inbox.set_db_path_for_test(str(Path(tmp) / "inbox.db"))
    watcher.set_db_path_for_test(str(Path(tmp) / "snapshots.db"))
    proactivity.set_db_path_for_test(str(Path(tmp) / "quota.db"))
    defaults = {"enable_period_budget": False, "enable_adaptive_scan": False,
                "enable_heartbeat": False, "enable_inbox": False}
    for k, v in {**defaults, **flags}.items():
        config.settings.__dict__[k] = v


def _mock_research(status="researched", tokens=4000):
    async def run(topic, change_set, thread_id):
        out = {"status": status, "brief": "🆕 某更新"}
        if status == "researched":
            out["result"] = {"report": "", "token_usage": tokens}
        return out
    return run


async def demo_wallet():
    _fresh_env("wallet", enable_period_budget=True)
    config.settings.__dict__["period_budget_tokens"] = 10_000
    print("─" * 72)
    print("Part 1 · 时段钱包：一天多班累计（预算 10000 token/天，软线 80%）")
    print("─" * 72)
    clock = FakeClock()
    for i, spend in enumerate([3000, 5500, 2000], 1):
        add_usage(spend, clock=clock)
        b = check_budget(clock=clock)
        icon = {"ok": "✅", "degrade": "🟡", "pause": "🛑"}[b["state"]]
        print(f"  第{i}班花 {spend} → 累计 {b['used']}/{b['limit']}（{b['ratio']:.0%}）"
              f" {icon} {b['state']}")

    # pause 挡下一班（daemon 集成）
    d = AmbientDaemon(clock=clock, run_research=_mock_research(tokens=2000))
    out = await d.run_cycle("盯梢主题")
    print(f"  第4班到点 → {out['status']}（挡在门口，连 job 都不开——")
    print(f"           进行中的班次不受影响：那是轨迹钱包（agent-ops L02）的辖区）")
    clock.advance(DAY)
    out = await d.run_cycle("盯梢主题")
    print(f"  次日到班 → {out['status']}（时段钱包按日翻篇）")
    print()
    print("  🎯 三层预算各管一个量纲：请求级限流（ops-L04）管单调用 QPS、")
    print("     轨迹级钱包（agent-ops L02）管单次运行、时段级钱包管一天总量。")
    print()


def demo_adaptive():
    _fresh_env("adaptive")
    print("─" * 72)
    print("Part 2 · 自适应扫描：安静的信源不配每天扫")
    print("─" * 72)
    clock = FakeClock()
    s = schedules.add_schedule("盯梢主题", DAY, clock=clock)
    schedules.mark_fired(s["schedule_id"], now=clock.now())
    print("  基础班次：每天 1 班")
    for i in range(1, 5):
        r = note_scan_result(s["schedule_id"], had_changes=False, clock=clock)
        print(f"  连续无变化 ×{r['streak']} → 间隔 ×{r['multiplier']}"
              f"（下一班 {int((r['next_run_at'] - clock.now()) / DAY)} 天后）")
    r = note_scan_result(s["schedule_id"], had_changes=True, clock=clock)
    print(f"  有变化！   → streak 归零，回到基础网格（×{r['multiplier']}）")
    print()
    print("  🎯 退避倍数是 2 的幂 → 班点仍落在基础网格上（L01 的网格没被破坏，")
    print("     只是跳过一些格子）。纪律：source_failed 不动 streak——")
    print("     「没能看到」既不证明安静（不该退避）也不证明有变化（不该回冲）。")
    print()


async def demo_heartbeat():
    _fresh_env("hb", enable_heartbeat=True, enable_inbox=True)
    print("─" * 72)
    print("Part 3 · 心跳与缺勤：安静和死了必须可区分")
    print("─" * 72)
    clock = FakeClock()
    schedules.add_schedule("盯梢主题", DAY, clock=clock)
    d = AmbientDaemon(clock=clock, run_research=_mock_research("no_change"))
    await d.run_loop(poll_seconds=DAY / 2, max_ticks=4)
    hb = period_budget.last_beat()
    print(f"  daemon 跑了 2 个模拟日（4 tick）——期间全是「无变化」的安静日子，")
    print(f"  但心跳表有 {hb['tick_count']} 笔：🤫 沉默是判断，💓 心跳是证明。")
    print()
    print("  daemon 被 kill，两天没人管……")
    clock.advance(2 * DAY)
    d2 = AmbientDaemon(clock=clock, run_research=_mock_research("no_change"))
    rep = await d2.startup()
    a = rep["absence"]
    print(f"  重启体检：absent={a['absent']}（{a['note']}）")
    alerts = inbox.list_entries(kind=inbox.KIND_ALERT)
    print(f"  → 告警落箱：{alerts[0]['title']}")
    print()
    print("  🎯 L02 立的纪律在服务级重演：内容层「没能看到≠没有变化」，")
    print("     服务层「没有通知≠一切正常」。心跳是后者的证明材料。")
    print()


async def demo_daily_report():
    _fresh_env("report", enable_period_budget=True, enable_inbox=True,
               enable_heartbeat=True, enable_proactivity=True)
    config.settings.__dict__["period_budget_tokens"] = 200_000
    print("─" * 72)
    print("Part 4 · 日报：一天一行服务体检")
    print("─" * 72)
    # 诚实标注：jobs 的时间戳走真实时钟（agent-ops 资产，不为演示改）。
    # 为让「班次账」和「花费账」落在同一天，把 FakeClock 对齐到真实 now，
    # 班次间隔用 10 分钟（4 班 30 分钟，不跨日）。
    import time as _t
    clock = FakeClock(start=_t.time())
    schedules.add_schedule("盯梢主题", 600, clock=clock)   # 10 分钟一班
    d = AmbientDaemon(clock=clock, run_research=_mock_research(tokens=3500),
                      llm_judge=None)
    await d.run_loop(poll_seconds=600, max_ticks=4)
    print(f"  {build_daily_report(day_key(_t.time()), clock=clock)}")
    print()
    print("  🎯 与 agent-ops L07 的分层：run summary 是一次运行一行（轨迹体检），")
    print("     日报是一天 N 次运行一行（服务体检）。日报走 digest 通道投递——")
    print("     它是「今晚看」的内容，不配打扰。")
    print()


async def main():
    print("=" * 72)
    print("  L07 · 时段预算与常驻可观测：睡觉时的钱和心跳")
    print("=" * 72)
    print()
    print("常驻的最后两个风险：成本累积（每次都正常，一天 N 次烧穿）和")
    print("静默失败（进程死了没人知道）。本课给 daemon 装总账、退避、心跳、日报。")
    print()
    await demo_wallet()
    demo_adaptive()
    await demo_heartbeat()
    await demo_daily_report()
    print("=" * 72)
    print("  本课小结")
    print("=" * 72)
    print("  ① 时段钱包是第三层预算：pause 挡下一班，不打断进行中（分层不越权）")
    print("  ② 自适应退避：安静的信源指数降频（封顶），有变化秒回基础网格")
    print("  ③ failed 不动 streak：「没能看到」在退避决策里也是一等公民纪律")
    print("  ④ 心跳让「安静」和「死了」可区分；缺勤在重启体检时显式呈现")
    print("  ⑤ 日报=服务体检（一天一行），与轨迹级 run summary 分层不重叠")


if __name__ == "__main__":
    asyncio.run(main())
