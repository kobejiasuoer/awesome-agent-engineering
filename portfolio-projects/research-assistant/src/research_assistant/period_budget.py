"""时段预算与常驻可观测：管住睡觉时的钱，沉默时也有心跳（Ambient L07）。

现状缺口：
    agent-ops L02 的钱包管**一条轨迹**（单次运行超预算会刹车），但常驻
    Agent 一天自主跑 N 次——每次都正常，加起来照样烧穿。且没人问就没人看：
    进程悄悄死了，「没消息」会被误读成「没变化」（L02 纪律的服务级版本）。

四件套：
    ① 时段钱包：一天的 token 总预算（跨 N 次运行累计）
       ok（<80%）/ degrade（80%+，该省着花）/ pause（100%，今天到此为止）
    ② 自适应扫描：连续无变化 → 间隔指数退避（×2^streak，封顶）；
       一有变化立即回到基础班次网格——退避倍数是 2 的幂，班点仍落在网格上
    ③ 心跳：daemon 每 tick 记一笔；启动时检查上次心跳距今——超阈值=缺勤，
       告警落箱（「沉默的日子也要有心跳」：安静和死了必须可区分）
    ④ 日报：一天一行体检——班次/研究结局/花费/打扰/心跳聚合
       （agent-ops L07 是一次运行一行 run summary；本课是一天 N 次运行一行）

三层预算对照（面试高频）：
    请求级（ops-L04 限流）→ 轨迹级（agent-ops L02 钱包）→ 时段级（本课）
    ——各约束各的量纲：单调用 QPS / 单次运行 token / 一天总 token。
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .clock import Clock
from .config import settings
from .logging_config import get_logger
from .proactivity import day_key

log = get_logger("period_budget")

_DB_PATH = "period_budget.db"

STATE_OK = "ok"
STATE_DEGRADE = "degrade"
STATE_PAUSE = "pause"


def _get_db_path() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent.parent / _DB_PATH


def _connect() -> sqlite3.Connection:
    path = _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS period_usage (
            day    TEXT PRIMARY KEY,
            tokens INTEGER NOT NULL DEFAULT 0,
            runs   INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS heartbeats (
            name       TEXT PRIMARY KEY,
            last_beat  REAL NOT NULL,
            tick_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    return conn


# ── ① 时段钱包 ───────────────────────────────────────────────

def add_usage(tokens: int, *, clock: Clock | None = None):
    """一次运行结束，把它的 token 记进当日总账。"""
    day = day_key((clock or Clock()).now())
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO period_usage (day, tokens, runs) VALUES (?, ?, 1) "
            "ON CONFLICT(day) DO UPDATE SET tokens = tokens + ?, runs = runs + 1",
            (day, int(tokens), int(tokens)))
        conn.commit()
    finally:
        conn.close()


def period_usage(day: str) -> dict:
    conn = _connect()
    try:
        row = conn.execute("SELECT tokens, runs FROM period_usage WHERE day = ?",
                           (day,)).fetchone()
        return {"day": day, "tokens": int(row[0]) if row else 0,
                "runs": int(row[1]) if row else 0}
    finally:
        conn.close()


def check_budget(*, clock: Clock | None = None) -> dict:
    """当日预算体检：ok / degrade（软线）/ pause（硬线）。

    与 agent-ops L02 的分层：单轨迹钱包管「这次别跑飞」，时段钱包管
    「今天别烧穿」——pause 挡的是**下一班要不要开跑**，不打断进行中的班次
    （进行中的自有轨迹钱包管）。
    """
    now = (clock or Clock()).now()
    usage = period_usage(day_key(now))
    limit = settings.period_budget_tokens
    used = usage["tokens"]
    ratio = used / limit if limit > 0 else 0.0
    if used >= limit:
        state = STATE_PAUSE
    elif ratio >= settings.period_soft_ratio:
        state = STATE_DEGRADE
    else:
        state = STATE_OK
    return {"state": state, "used": used, "limit": limit,
            "ratio": round(ratio, 3), "runs": usage["runs"]}


# ── ② 自适应扫描（作用于 L01 调度表）─────────────────────────

def note_scan_result(schedule_id: str, had_changes: bool, *,
                     clock: Clock | None = None) -> dict:
    """把「这班有没有变化」反馈给调度表 → 无变化退避 / 有变化回网格。

    退避语义：streak 连续无变化次数，有效间隔 = base × min(2^streak, cap)；
    下一班 = 本班 last_run_at + 有效间隔。倍数是 2 的幂 → 班点仍在基础
    网格上（退避不破坏网格，只是跳过一些格子）。
    有变化：streak 归零；next_run_at 已由 mark_fired 排在基础网格上，不动。

    纪律：source_failed 的班次**不该调用本函数**——「没能看到」既不证明
    世界安静（不该退避），也不证明有变化（不该回冲）——streak 保持原样。
    """
    from . import schedules as sch_mod
    sch = sch_mod.get_schedule(schedule_id)
    if sch is None:
        raise KeyError(f"调度不存在：{schedule_id}")

    if had_changes:
        streak, mult = 0, 1
        new_next = sch["next_run_at"]          # 回到基础网格（mark_fired 已排好）
    else:
        streak = sch["no_change_streak"] + 1
        mult = min(2 ** streak, settings.adaptive_backoff_cap)
        base = sch["last_run_at"] if sch["last_run_at"] is not None else \
            (clock or Clock()).now()
        new_next = base + mult * sch["interval_seconds"]

    conn = sch_mod._connect()
    try:
        conn.execute(
            "UPDATE schedules SET no_change_streak = ?, next_run_at = ?, "
            "updated_at = ? WHERE schedule_id = ?",
            (streak, new_next, time.time(), schedule_id))
        conn.commit()
    finally:
        conn.close()
    if streak:
        log.info(f"自适应退避：{schedule_id} 连续无变化 {streak} 次 → 间隔 ×{mult}")
    return {"schedule_id": schedule_id, "streak": streak,
            "multiplier": mult, "next_run_at": new_next}


# ── ③ 心跳与缺勤 ─────────────────────────────────────────────

def beat(name: str = "daemon", *, clock: Clock | None = None):
    """daemon 每 tick 记一笔——「我还活着」的最便宜证明。"""
    now = (clock or Clock()).now()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO heartbeats (name, last_beat, tick_count) VALUES (?, ?, 1) "
            "ON CONFLICT(name) DO UPDATE SET last_beat = ?, tick_count = tick_count + 1",
            (name, now, now))
        conn.commit()
    finally:
        conn.close()


def last_beat(name: str = "daemon") -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT last_beat, tick_count FROM heartbeats "
                           "WHERE name = ?", (name,)).fetchone()
        return {"last_beat": row[0], "tick_count": row[1]} if row else None
    finally:
        conn.close()


def check_absence(name: str = "daemon", *, clock: Clock | None = None) -> dict:
    """启动时问一句：我上次活着是什么时候？

    gap 超过 absence_alert_hours = 缺勤（期间的世界变化没人看）。
    首次启动（无心跳记录）不算缺勤——没上过班谈不上旷工。
    """
    now = (clock or Clock()).now()
    hb = last_beat(name)
    if hb is None:
        return {"absent": False, "gap_hours": None, "note": "首次启动，无心跳历史"}
    gap_h = (now - hb["last_beat"]) / 3600.0
    absent = gap_h > settings.absence_alert_hours
    return {"absent": absent, "gap_hours": round(gap_h, 2),
            "note": f"上次心跳距今 {gap_h:.1f} 小时" +
                    ("（超阈值，缺勤期的世界变化没人看）" if absent else "")}


# ── ④ 日报：一天一行体检 ─────────────────────────────────────

def build_daily_report(day: str | None = None, *,
                       clock: Clock | None = None) -> str:
    """聚合一天：班次（jobs）+ 花费（时段钱包）+ 打扰（inbox）+ 心跳。

    与 agent-ops L07 run summary 的分层：那是一次运行一行（轨迹体检），
    这是一天 N 次运行一行（服务体检）。日报本身走 digest 通道投递
    （它是「今晚看」的内容，不配打扰）。
    """
    now = (clock or Clock()).now()
    d = day or day_key(now)

    # 班次账（jobs 按当日 updated_at 过滤）
    from . import jobs as jobs_mod
    day_start = time.mktime(time.strptime(d, "%Y-%m-%d"))
    day_end = day_start + 86400
    counts = {"done": 0, "failed": 0, "awaiting_approval": 0}
    for j in jobs_mod.list_jobs(limit=200):
        if day_start <= j["updated_at"] < day_end and j["status"] in counts:
            counts[j["status"]] += 1

    usage = period_usage(d)
    limit = settings.period_budget_tokens
    pct = f"{usage['tokens'] / limit:.0%}" if limit else "-"

    # 打扰账（inbox 按当日 created_at 过滤）
    from . import inbox as inbox_mod
    notify = digest = alerts = quota_exh = 0
    for e in inbox_mod.list_entries(limit=200):
        if not (day_start <= e["created_at"] < day_end):
            continue
        if e["kind"] == "notify":
            notify += 1
        elif e["kind"] == "digest":
            digest += 1
            if e["title"].startswith("⚠ 配额尽降级"):
                quota_exh += 1
        elif e["kind"] == "alert":
            alerts += 1

    hb = last_beat()
    ticks = hb["tick_count"] if hb else 0
    health = "✅" if counts["failed"] == 0 and alerts == 0 else "⚠️"

    return (f"📊 日报 {d} | 班次: {counts['done']}成/{counts['failed']}败"
            f"/{counts['awaiting_approval']}待批 | 花费: {usage['tokens']}/{limit} token（{pct}，"
            f"{usage['runs']} 班）| 打扰: {notify}立即+{digest}摘要"
            f"（配额尽降级 {quota_exh}）| 告警: {alerts} | 心跳: {ticks} tick | {health}")


def set_db_path_for_test(path: str):
    """测试用：覆盖时段账本路径（隔离）。"""
    global _DB_PATH
    _DB_PATH = path
