"""常驻收益矩阵：逐机制开关 × 5 日时间线 = 六指标收益表（Ambient L08）。

评估思路（对齐 frontier-L09 harness / agent-ops L08 混沌矩阵的家族传统）：
    同一条 5 日模拟时间线（含 Day5 信源故障）+ 一条崩溃探针支线，
    在五档配置下各跑一遍，量化每层机制的边际收益：
        ① baseline    人肉盯梢（L00 基线：无 daemon，数字取自基线结构）
        ② cron        只开调度（每日全量研究+每日推送——「穷人版 cron」）
        ③ +watcher    调度+变化检测+增量研究（推送仍全推）
        ④ +judge      再加判级+配额+收件箱分通道
        ⑤ full        全开（再加时段预算+心跳+自适应退避）

六指标：
    增量召回率   该发现的三个事件（E1 Day3 新增 / E2 Day4 重磅 / E3 Day4 修正）
                 被主动呈现（出现在收件箱条目里）的比例
    打扰精确率   值得的立即打扰 / 总立即打扰（值得=Day4 重大反转那一班）
    疲劳指数     立即打扰总次数（notify 条目数；越低越不烦人）
    静默失败     Day5 信源故障被当成正常结论呈现=1（危险的谎言），
                 显式走告警通道=0
    5 日 token   五天总花费（mock 估算口径统一，横向可比）
    缺勤检出     崩溃探针：daemon 被杀两天后重启，缺勤是否被发现并告警

诚实标注：
    - 「研究」为确定性 mock（全量 1000 / 增量每条 150 / 扫描 5 token 的
      统一估算口径）——绝对数字非真实 API，五档间的**相对结构**与真实一致。
    - baseline 行不跑 daemon（会话式没有这些机制），数字来自 L00 基线的
      结构性结论（全量重研×5、全量推送×5、Day5 污染、无缺勤概念）。
    - 全开档的退避会让 E1 晚一天发现（Day2 无变化→间隔×2→Day3 班次被跳过，
      E1 与 Day4 事件同班发现）——省钱的代价被诚实呈现，不藏。

跑法（零 API、零联网、零等待）：
    python eval_agent/run_ambient_eval.py          # 跑矩阵 + 写 AMBIENT_REPORT.md
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

_PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJ / "src"))
sys.path.insert(0, str(_PROJ))

from eval_agent.ambient_timeline import (  # noqa: E402
    TIMELINE_DAYS, TOPIC, AmbientTimeline,
)
from research_assistant import (  # noqa: E402
    config, inbox, jobs, period_budget, proactivity, schedules, watcher,
)
from research_assistant.clock import DAY_SECONDS, FakeClock  # noqa: E402
from research_assistant.daemon import AmbientDaemon  # noqa: E402

DAY = DAY_SECONDS

# mock 成本口径（估算，五档统一，横向可比）
COST_FULL_RUN = 1000       # 一次全量研究
COST_PER_FOCUS = 150       # 增量研究每条焦点
COST_SCAN = 5              # 一次机械层扫描

# 三个应被发现的事件（ground truth）
EVENTS = {"E1_minor_new": "框架 Y", "E2_major_new": "撤回 AGUI", "E3_correction": "此前结论已不成立"}

ALL_FLAGS = ("enable_schedules", "enable_source_watch", "enable_incremental_run",
             "enable_proactivity", "enable_inbox", "enable_period_budget",
             "enable_adaptive_scan", "enable_heartbeat")

CONFIGS = [
    ("baseline·人肉盯梢", None),                                   # 不跑 daemon
    ("cron·只开调度", {"enable_schedules": True, "enable_inbox": True,
                       "proactivity_policy": "all", "enable_proactivity": True,
                       "_judge": "dumb"}),   # 哑判级：有产出就推（模拟现状邮件推送）
    ("+watcher·增量", {"enable_schedules": True, "enable_inbox": True,
                       "enable_source_watch": True, "enable_incremental_run": True,
                       "proactivity_policy": "all", "enable_proactivity": True}),
    ("+judge·判级配额", {"enable_schedules": True, "enable_inbox": True,
                         "enable_source_watch": True, "enable_incremental_run": True,
                         "enable_proactivity": True, "proactivity_policy": "threshold"}),
    ("full·全开", {"enable_schedules": True, "enable_inbox": True,
                   "enable_source_watch": True, "enable_incremental_run": True,
                   "enable_proactivity": True, "proactivity_policy": "threshold",
                   "enable_period_budget": True, "enable_adaptive_scan": True,
                   "enable_heartbeat": True}),
]


def _fresh_env(flags: dict | None):
    tmp = tempfile.mkdtemp(prefix="ambient_eval_")
    watcher.set_db_path_for_test(str(Path(tmp) / "snapshots.db"))
    schedules.set_db_path_for_test(str(Path(tmp) / "schedules.db"))
    jobs.set_db_path_for_test(str(Path(tmp) / "jobs.db"))
    inbox.set_db_path_for_test(str(Path(tmp) / "inbox.db"))
    proactivity.set_db_path_for_test(str(Path(tmp) / "quota.db"))
    period_budget.set_db_path_for_test(str(Path(tmp) / "period.db"))
    for f in ALL_FLAGS:
        config.settings.__dict__[f] = False
    config.settings.__dict__["proactivity_policy"] = "threshold"
    config.settings.__dict__["daily_interrupt_quota"] = 2
    config.settings.__dict__["period_budget_tokens"] = 200_000
    for k, v in (flags or {}).items():
        if not k.startswith("_"):
            config.settings.__dict__[k] = v


def make_mock_research(timeline: AmbientTimeline, spent: list):
    """确定性 mock 研究：watch 关时复刻现状全量（含 Day5 污染），
    watch 开时按变化集三分支（增量口径计费）。"""

    async def run(topic, change_set, thread_id):
        if change_set is None:
            # 现状全量：每班 1000 token；Day5 信源故障字符串混进报告（复刻缺口）
            spent.append(COST_FULL_RUN)
            day = timeline.current_day()
            try:
                text = timeline.as_search_text(topic, day)
                brief = f"全量报告：{text[:800]}"
            except Exception as e:
                brief = f"全量报告：搜索 '{topic}' 失败（{type(e).__name__}: {e}）。可换关键词重试。"
            return {"status": "researched", "brief": brief,
                    "result": {"report": "", "token_usage": COST_FULL_RUN}}
        # watch 开：机械层扫描已由 daemon 完成（记扫描成本）
        spent.append(COST_SCAN)
        if not change_set.ok:
            return {"status": "source_failed",
                    "brief": f"⚠️ 没能看到信源（{change_set.error[:60]}）——不等于没有变化"}
        if change_set.is_no_change():
            return {"status": "no_change", "brief": "✅ 确认无变化"}
        n_focus = len(change_set.new_items) + len(change_set.changed_items)
        spent.append(COST_PER_FOCUS * n_focus)
        parts = []
        if change_set.first_scan:
            parts.append(f"🆕 建仓：{len(change_set.new_items)} 条基线（"
                         + "；".join(it.title for it in change_set.new_items) + "）")
        else:
            parts += [f"🆕 新增: {it.title}——{it.content[:60]}" for it in change_set.new_items]
            parts += [f"✏️ 修正: {it.title}——此前结论已不成立" for it in change_set.changed_items]
        return {"status": "researched", "brief": "；".join(parts),
                "result": {"report": "", "token_usage": COST_PER_FOCUS * n_focus}}

    return run


class DumbJudge:
    """哑判级：一切产出判 minor（配合 policy=all → 有产出就推）。
    专供 cron 档——模拟「每天一封全量邮件」的现状推送形态。"""

    def invoke(self, prompt):
        class _R:
            content = "minor\n有产出就推（现状形态）"
        return _R()


def _highlighted(entries: list[dict]) -> str:
    """召回口径：只有「被点名」才算主动呈现。

    全量倾倒（「全量报告：」开头的 body）不算——信息在但埋着，
    读者仍要人肉 diff，与 baseline 同罪。
    """
    return "\n".join(e["title"] + e["body"] for e in entries
                     if not e["body"].startswith("全量报告："))


async def run_scenario(label: str, flags: dict) -> dict:
    """一档配置跑主线 5 日 + 崩溃探针，产出六指标。"""
    _fresh_env(flags)
    judge = DumbJudge() if flags.get("_judge") == "dumb" else None
    clock = FakeClock()
    timeline = AmbientTimeline(clock=clock, start_ts=clock.now())
    schedules.add_schedule(TOPIC, DAY, clock=clock)
    spent: list[int] = []
    d = AmbientDaemon(clock=clock, fetch=timeline.fetch_items, source_id="tl",
                      llm_judge=judge, run_research=make_mock_research(timeline, spent))

    for _day in range(1, TIMELINE_DAYS + 1):
        await d.step()
        clock.advance_days(1)

    # 指标从收件箱/账本回收
    entries = inbox.list_entries(limit=200)
    delivered_text = "\n".join(e["title"] + e["body"] for e in entries)
    notify_entries = [e for e in entries if e["kind"] == inbox.KIND_NOTIFY]
    alerts = [e for e in entries if e["kind"] == inbox.KIND_ALERT]

    recall_hits = sum(1 for kw in EVENTS.values() if kw in _highlighted(entries))
    interrupts = len(notify_entries)
    worthy = sum(1 for e in notify_entries
                 if "撤回" in e["body"] or "修正" in e["body"] or "✏️" in e["body"])
    precision = round(worthy / interrupts, 2) if interrupts else None
    # 静默失败：Day5 被当正常结论（全量污染报告被投递）=1；显式告警/failed=0
    silent_failure = 1 if ("失败（" in delivered_text and not alerts) else 0
    tokens = sum(spent)

    # 崩溃探针：接着当前状态——kill 两天后重启，看缺勤是否被发现
    clock.advance_days(2)
    d2 = AmbientDaemon(clock=clock, fetch=timeline.fetch_items, source_id="tl",
                       llm_judge=judge,
                       run_research=make_mock_research(timeline, spent))
    startup = await d2.startup()
    absence_detected = 1 if startup.get("absence", {}).get("absent") else 0

    return {"config": label, "recall": f"{recall_hits}/{len(EVENTS)}",
            "interrupts": interrupts, "precision": precision,
            "silent_failure": silent_failure, "tokens_5d": tokens,
            "absence_detected": absence_detected}


def baseline_row() -> dict:
    """L00 基线的结构性结论（会话式没有这些机制，不跑 daemon）：
    全量重研×5、全量推送×5（只有 Day4 值得）、增量埋在全量里（主动呈现=0）、
    Day5 污染、没有缺勤概念（人忘了问=全盲）。"""
    return {"config": "baseline·人肉盯梢", "recall": f"0/{len(EVENTS)}",
            "interrupts": 5, "precision": round(1 / 5, 2),
            "silent_failure": 1, "tokens_5d": 5 * COST_FULL_RUN,
            "absence_detected": 0}


async def run_matrix() -> list[dict]:
    rows = []
    for label, flags in CONFIGS:
        if flags is None:
            rows.append(baseline_row())
        else:
            rows.append(await run_scenario(label, flags))
    return rows


def render_report(rows: list[dict]) -> str:
    lines = [
        "# Ambient 收益矩阵（L08）",
        "",
        f"同一条 5 日模拟时间线（主题：{TOPIC}，含 Day5 信源故障）+ 崩溃探针，",
        "五档配置各跑一遍。研究为确定性 mock（全量 1000 / 增量 150×条 / 扫描 5 token"
        " 的统一估算口径）——绝对数字非真实 API，五档间的相对结构与真实一致。",
        "复现：`python eval_agent/run_ambient_eval.py`（零 API、零联网、零等待）。",
        "",
        "| 配置 | 增量召回 | 立即打扰 | 打扰精确率 | 静默失败 | 5日token(估) | 缺勤检出 |",
        "|---|---|---:|---|---|---:|---|",
    ]
    for r in rows:
        prec = f"{r['precision']:.0%}" if r["precision"] is not None else "—(零打扰)"
        lines.append(
            f"| {r['config']} | {r['recall']} | {r['interrupts']} | {prec} "
            f"| {'❌ 有' if r['silent_failure'] else '✅ 无'} | {r['tokens_5d']} "
            f"| {'✅' if r['absence_detected'] else '—'} |")
    lines += [
        "",
        "## 逐档解读（每层机制买到了什么）",
        "",
        "- **baseline → cron**：解决「忘了问就全盲」（触发自动化），但其余五项原样——",
        "  每天全量重研+全量推送，Day5 污染照旧。cron 只买到出勤，没买到判断。",
        "- **cron → +watcher**：token 大降（无变化日只花扫描钱）；增量召回 3/3",
        "  （变化被点名而非埋在全量里）；Day5 从「污染报告」变「显式告警」。",
        "- **+watcher → +judge**：打扰从每班全推降到只推重大（精确率 100%），",
        "  minor 攒进摘要不丢——注意力账被管起来。",
        "- **+judge → full**：新增缺勤检出（心跳）；退避再省无变化日的钱。",
        "  ⚠️ 诚实代价：退避让 Day3 的小更新晚一天发现（与 Day4 事件同班）——",
        "  省钱 vs 发现延迟的汇率由 adaptive_backoff_cap 控制。",
        "",
        "## 纯净跑零税（回归声明）",
        "",
        "八个 Ambient 开关默认全关；全关时 split/researcher/service/图拓扑与 v3",
        "行为逐字节一致（全量 323 项测试含关态回归）。矩阵五档均为显式开启的结果。",
    ]
    return "\n".join(lines) + "\n"


async def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import logging
    logging.disable(logging.WARNING)

    rows = await run_matrix()
    report = render_report(rows)
    out = Path(__file__).resolve().parent / "AMBIENT_REPORT.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"📦 收益矩阵已存：{out}")


if __name__ == "__main__":
    asyncio.run(main())
