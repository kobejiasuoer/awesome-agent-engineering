"""调度器：谁来叫醒 Agent（Ambient L01）。

现状缺口：
    会话式的一切开始于人发消息——人忘了问，Agent 就永远沉默（L00 基线
    「人忘了问」支线：重大进展日全盲）。本模块给系统装第一个触发器。

设计：
    - schedules 表（sqlite，风格对齐 jobs.py）：一行 = 一个盯梢调度
    - Scheduler.tick()：单步驱动——找到期调度、触发、按固定班次网格排下一班
    - 时间全部走可注入时钟（clock.py）：测试/演示用 FakeClock 快进，零真实等待
    - 职责边界：调度器只管「什么时候叫醒」，不管「跑」——触发即登记进
      jobs 注册表（复用 agent-ops L06 资产），执行由常驻 daemon（L06）认领

固定班次 vs 漂移间隔（本课关键取舍，README「流派对比」详述）：
    固定班次（本模块）：next = 上一班 + (missed+1)×interval —— 班次网格稳定，
        错过几班算得清（missed 语义是 L06 catch-up 的地基）
    漂移间隔：next = 实际触发时刻 + interval —— 实现最简，但每次晚触发都让
        班次整体后漂，跑一个月后「每天 9 点」变成「每天 11 点半」

与 langgraph/jobs 的关系：
    调度器不碰图、不碰 checkpoint。它产出的只是「该跑了」这个事实
    （登记 pending job），研究图的执行/恢复语义完全复用现有机制。
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .clock import Clock
from .logging_config import get_logger

log = get_logger("schedules")

_DB_PATH = "schedules.db"


def _get_db_path() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent.parent / _DB_PATH


def _connect() -> sqlite3.Connection:
    path = _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            schedule_id      TEXT PRIMARY KEY,
            topic            TEXT NOT NULL,
            interval_seconds REAL NOT NULL,
            next_run_at      REAL NOT NULL,
            enabled          INTEGER NOT NULL DEFAULT 1,
            last_run_at      REAL,
            missed_count     INTEGER NOT NULL DEFAULT 0,
            no_change_streak INTEGER NOT NULL DEFAULT 0,
            created_at       REAL NOT NULL,
            updated_at       REAL NOT NULL
        )
    """)
    # no_change_streak：L07 自适应扫描用（连续无变化 → 间隔退避），本课恒 0
    conn.execute("CREATE INDEX IF NOT EXISTS idx_schedules_next ON schedules(enabled, next_run_at)")
    conn.commit()
    return conn


def _row_to_dict(row) -> dict:
    return {
        "schedule_id": row[0], "topic": row[1], "interval_seconds": row[2],
        "next_run_at": row[3], "enabled": bool(row[4]), "last_run_at": row[5],
        "missed_count": row[6], "no_change_streak": row[7],
        "created_at": row[8], "updated_at": row[9],
    }


_COLS = ("schedule_id, topic, interval_seconds, next_run_at, enabled, "
         "last_run_at, missed_count, no_change_streak, created_at, updated_at")


def add_schedule(
    topic: str,
    interval_seconds: float,
    *,
    clock: Clock | None = None,
    first_run_at: float | None = None,
    schedule_id: str | None = None,
) -> dict:
    """注册一个盯梢调度。

    first_run_at 缺省 = 现在（注册即到期，下一次 tick 立即触发首班——
    盯梢任务注册后先建仓，比「等一整个周期才开始」符合直觉）。
    """
    if interval_seconds <= 0:
        raise ValueError(f"interval_seconds 必须为正数，得到 {interval_seconds}")
    now = (clock or Clock()).now()
    sid = schedule_id or f"sch-{uuid.uuid4().hex[:8]}"
    first = first_run_at if first_run_at is not None else now
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO schedules (schedule_id, topic, interval_seconds, next_run_at, "
            "enabled, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
            (sid, topic, float(interval_seconds), float(first), now, now),
        )
        conn.commit()
    finally:
        conn.close()
    log.info(f"注册调度 {sid}（topic={topic}, interval={interval_seconds}s）")
    return get_schedule(sid)  # type: ignore[return-value]


def get_schedule(schedule_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT {_COLS} FROM schedules WHERE schedule_id = ?", (schedule_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_schedules(enabled_only: bool = False) -> list[dict]:
    conn = _connect()
    try:
        sql = f"SELECT {_COLS} FROM schedules"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY next_run_at"
        return [_row_to_dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def set_enabled(schedule_id: str, enabled: bool):
    """暂停/恢复调度（暂停期间不触发也不累计 missed——是「主动停」不是「缺勤」）。"""
    conn = _connect()
    try:
        conn.execute(
            "UPDATE schedules SET enabled = ?, updated_at = ? WHERE schedule_id = ?",
            (1 if enabled else 0, time.time(), schedule_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_interval(schedule_id: str, interval_seconds: float):
    """改扫描间隔。只影响之后的班次计算，已排定的 next_run_at 不动（最小惊讶）。"""
    if interval_seconds <= 0:
        raise ValueError(f"interval_seconds 必须为正数，得到 {interval_seconds}")
    conn = _connect()
    try:
        conn.execute(
            "UPDATE schedules SET interval_seconds = ?, updated_at = ? WHERE schedule_id = ?",
            (float(interval_seconds), time.time(), schedule_id),
        )
        conn.commit()
    finally:
        conn.close()


def due_schedules(now: float) -> list[dict]:
    """到期未触发的启用调度（enabled 且 next_run_at <= now）。"""
    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT {_COLS} FROM schedules WHERE enabled = 1 AND next_run_at <= ? "
            "ORDER BY next_run_at", (now,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def mark_fired(schedule_id: str, now: float, missed: int = 0) -> dict:
    """记一次触发：last_run_at=now，下一班按固定网格排，累计 missed。

    固定班次网格：next = 旧 next + (missed+1)×interval。
    即使这次触发晚了 3 小时，下一班仍在原网格上——不漂移。
    """
    sch = get_schedule(schedule_id)
    if sch is None:
        raise KeyError(f"调度不存在：{schedule_id}")
    new_next = sch["next_run_at"] + (missed + 1) * sch["interval_seconds"]
    conn = _connect()
    try:
        conn.execute(
            "UPDATE schedules SET last_run_at = ?, next_run_at = ?, "
            "missed_count = missed_count + ?, updated_at = ? WHERE schedule_id = ?",
            (now, new_next, missed, time.time(), schedule_id),
        )
        conn.commit()
    finally:
        conn.close()
    return get_schedule(schedule_id)  # type: ignore[return-value]


class Scheduler:
    """轮询调度器：tick() 单步驱动（测试/演示手动 tick，daemon（L06）循环 tick）。

    dispatch：触发后干什么。缺省 None = 只返回触发记录（纯调度语义）；
    落地传 make_job_dispatch()（登记 pending job，执行交给 daemon）。
    """

    def __init__(self, clock: Clock | None = None,
                 dispatch: Callable[[dict], Any] | None = None):
        self._clock = clock or Clock()
        self._dispatch = dispatch

    def tick(self) -> list[dict]:
        """单步：触发所有到期调度，返回触发记录。

        missed 语义：now 已越过 next_run_at 几个完整周期，就算错过几班
        （本次只触发一次，错过的班次数记档——补跑策略是 L06 的 catch-up）。
        """
        now = self._clock.now()
        fired: list[dict] = []
        for sch in due_schedules(now):
            missed = int((now - sch["next_run_at"]) // sch["interval_seconds"])
            updated = mark_fired(sch["schedule_id"], now=now, missed=missed)
            record = {
                "schedule_id": sch["schedule_id"], "topic": sch["topic"],
                "fired_at": now, "missed": missed,
                "next_run_at": updated["next_run_at"],
            }
            if self._dispatch is not None:
                record["dispatch_result"] = self._dispatch(sch)
            if missed:
                log.warning(f"调度 {sch['schedule_id']} 错过 {missed} 班（缺勤补记，本次只触发一次）")
            fired.append(record)
        return fired


def make_job_dispatch() -> Callable[[dict], dict]:
    """默认 dispatch：触发 = 登记一个 pending 研究任务（复用 jobs 注册表）。

    调度器只管叫醒，不管跑——执行/崩溃恢复语义完全复用 jobs + checkpoint
    （agent-ops L06 资产），不另造运行记录。
    """
    from . import jobs

    def dispatch(sch: dict) -> dict:
        return jobs.submit_job(topic=sch["topic"])

    return dispatch


def set_db_path_for_test(path: str):
    """测试用：覆盖调度表路径（隔离）。"""
    global _DB_PATH
    _DB_PATH = path


if __name__ == "__main__":  # pragma: no cover
    # 极简管理入口：PYTHONPATH=src python -m research_assistant.schedules list
    import argparse
    import sys as _sys
    try:
        _sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="盯梢调度管理（Ambient L01）")
    sub = p.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add", help="注册调度")
    p_add.add_argument("--topic", required=True)
    p_add.add_argument("--interval-hours", type=float, default=24.0)
    sub.add_parser("list", help="列出调度")
    p_tick = sub.add_parser("tick", help="手动驱动一次（触发到期调度）")
    args = p.parse_args()
    if args.cmd == "add":
        print(add_schedule(args.topic, args.interval_hours * 3600))
    elif args.cmd == "list":
        for s in list_schedules():
            print(s)
    elif args.cmd == "tick":
        for r in Scheduler(dispatch=make_job_dispatch()).tick():
            print(r)
