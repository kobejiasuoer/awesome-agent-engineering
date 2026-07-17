"""L09 · 毕业整合：research-assistant v4（常驻主动）定稿
==================================================

本脚本是全课程的端到端合拢演示——八个开关全开，跑一段「v4 的一周」：
    Day1  建仓（首启体检：无心跳历史，不算缺勤）
    Day2  确认无变化（沉默 + 心跳照跳 + 退避生效）
    Day3  小更新（minor → 摘要）……当晚进程被杀
    Day4  全天缺勤（世界发生了重大反转，但没有进程在看）
    Day5  重启：缺勤告警 + 班次 catch-up + 一口气发现 Day4 的重磅与修正
          （major → 立即通知 ⚡）……随后信源故障（→ 告警通道）
    收尾  收件箱全景 + 日报 + jobs 记账 + 版本演进 v1→v4

诚实标注：研究步骤 mock（离线硬约束）；调度/扫描/判级/配额/投递/心跳/
预算/恢复全部真实模块。收益数字见 eval_agent/AMBIENT_REPORT.md（确定性可复现）。

跑法（零 API、零联网、零等待）：
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

from eval_agent.ambient_timeline import TOPIC, AmbientTimeline  # noqa: E402
from research_assistant import (  # noqa: E402
    config, inbox, jobs, period_budget, proactivity, schedules, watcher,
)
from research_assistant.clock import DAY_SECONDS, FakeClock  # noqa: E402
from research_assistant.daemon import AmbientDaemon  # noqa: E402
from research_assistant.proactivity import day_key  # noqa: E402

DAY = DAY_SECONDS

ALL_ON = {"enable_schedules": True, "enable_source_watch": True,
          "enable_incremental_run": True, "enable_proactivity": True,
          "enable_inbox": True, "enable_period_budget": True,
          "enable_adaptive_scan": True, "enable_heartbeat": True}


def _env():
    tmp = tempfile.mkdtemp(prefix="ambient_l09_")
    for mod, name in ((schedules, "schedules"), (jobs, "jobs"), (inbox, "inbox"),
                      (watcher, "snapshots"), (proactivity, "quota"),
                      (period_budget, "period")):
        mod.set_db_path_for_test(str(Path(tmp) / f"{name}.db"))
    for k, v in ALL_ON.items():
        config.settings.__dict__[k] = v
    config.settings.__dict__["proactivity_policy"] = "threshold"
    config.settings.__dict__["daily_interrupt_quota"] = 2
    config.settings.__dict__["period_budget_tokens"] = 200_000


async def scripted_research(topic, change_set, thread_id):
    """确定性 mock 研究（真实版 = run_incremental 进研究图）。"""
    if change_set is None or not change_set.ok:
        err = getattr(change_set, "error", "no source") if change_set else "no source"
        return {"status": "source_failed",
                "brief": f"⚠️ 没能看到信源（{err[:50]}）——不等于没有变化"}
    if change_set.is_no_change():
        return {"status": "no_change", "brief": "✅ 确认无变化"}
    parts = []
    if change_set.first_scan:
        parts.append(f"🆕 建仓：{len(change_set.new_items)} 条基线结论入账")
    else:
        parts += [f"🆕 新增: {it.title}" for it in change_set.new_items]
        parts += [f"✏️ 修正: {it.title}——此前结论已不成立" for it in change_set.changed_items]
    n = max(1, len(change_set.new_items) + len(change_set.changed_items))
    return {"status": "researched", "brief": "；".join(parts),
            "result": {"report": "", "token_usage": 150 * n}}


ACTION_ICON = {"notify_now": "⚡ 立即通知", "add_to_digest": "📥 进摘要",
               "stay_silent": "🤫 沉默"}


def _describe(r):
    if r["status"] == "source_failed":
        return "🚨 告警通道（没能看到 ≠ 没有变化）"
    if r["status"] == "budget_paused":
        return "🛑 时段预算暂停"
    dec = r.get("decision") or {}
    return ACTION_ICON.get(dec.get("decision"), "🤫 沉默")


async def main():
    print("=" * 72)
    print("  L09 · research-assistant v4（常驻主动）——全机制协同的一周")
    print("=" * 72)
    _env()
    clock = FakeClock()
    tl = AmbientTimeline(clock=clock, start_ts=clock.now())
    schedules.add_schedule(TOPIC, DAY, clock=clock)

    d = AmbientDaemon(clock=clock, fetch=tl.fetch_items, source_id="tl",
                      llm_judge=None, run_research=scripted_research)
    print(f"\n八开关全开；注册盯梢调度：{TOPIC}（每日一班）\n")

    boot = await d.startup()
    print(f"Day1 09:00 首启体检：孤儿 {boot['orphans_found']} 个；"
          f"缺勤 {boot['absence']['absent']}（{boot['absence']['note']}）")

    for day in (1, 2, 3):
        rep = await d.step()
        for r in rep["ran"]:
            print(f"Day{day}        班次 → {r['status']:<13} → {_describe(r)}")
        if not rep["ran"] and not rep["skipped"]:
            print(f"Day{day}        （自适应退避中，本日无班——Day3 的小更新"
                  f"将晚一天发现，这是 L08 记录过的省钱代价）")
        clock.advance_days(1)

    print("Day3 23:00  💀 进程被杀（没有优雅退出）")

    d2 = AmbientDaemon(clock=clock, fetch=tl.fetch_items, source_id="tl",
                       llm_judge=None, run_research=scripted_research)
    boot2 = await d2.startup()
    print(f"Day4 09:00  重启体检：缺勤 {boot2['absence']['absent']}"
          f"（gap {boot2['absence']['gap_hours']}h > 阈值 6h）→ 🚨 告警落箱")
    rep = await d2.step()
    for r in rep["ran"]:
        print(f"Day4        班次 → {r['status']:<13} → {_describe(r)}"
              f"（Day3 小更新 + Day4 重磅/修正同班发现，✏️ 触发 major）")
    clock.advance_days(1)
    rep = await d2.step()      # Day5：信源故障日
    for r in rep["ran"]:
        print(f"Day5        班次 → {r['status']:<13} → {_describe(r)}")

    # ── 收尾全景 ──
    print("\n" + "─" * 72)
    print("一周后的收件箱（人全程只被 ⚡ 打扰 1 次，其余各归其位）：")
    print("─" * 72)
    for e in reversed(inbox.list_entries(limit=50)):
        print(f"  [{e['kind']:<8}] {e['title'][:56]}")
    print()
    print(f"  摘要日结：{inbox.build_digest(clock=clock).splitlines()[0]}")
    week_tokens = sum(
        period_budget.period_usage(day_key(1_700_000_000.0 + i * DAY))["tokens"]
        for i in range(7))
    print(f"  本周研究花费：{week_tokens} token（估）——对照 L00 人肉基线同周期约 5000")
    done = jobs.list_jobs(status=jobs.STATUS_DONE)
    print(f"  jobs 记账：{len(done)} 班 done（全程可审计）")

    print()
    print("=" * 72)
    print("  版本演进（两条产品线在此对称收官）")
    print("=" * 72)
    print("  v1 多智能体      能跑的搜索→写报告        rag/workflow 课程")
    print("  v2 Deep Research 有记忆/反思/代码/浏览器   frontier + gui-agent 课程")
    print("  v3 生产可靠      故障可生存/崩溃可恢复     agent-ops 课程")
    print("  v4 常驻主动      自己醒/只研究变化/        ambient-agent 课程")
    print("                   知道何时开口/死了有人知道")
    print()
    print("  收益数字：eval_agent/AMBIENT_REPORT.md（cron档=基线实证 / token -79% /")
    print("  打扰 5→1 精确率 100% / 静默失败归零 / 缺勤可检出，确定性可复现）")


if __name__ == "__main__":
    asyncio.run(main())
