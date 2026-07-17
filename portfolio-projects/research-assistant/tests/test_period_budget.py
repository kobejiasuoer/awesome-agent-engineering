"""Ambient L07 测试：时段预算与常驻可观测。

测试原则（对齐 conftest.py）：
    - 全库 tmp_path 隔离 + FakeClock 拨表（跨日/缺勤零等待）
    - 灵魂用例：pause 挡下一班不打断进行中 / failed 不动退避 streak /
      缺勤与首次启动可区分
"""
from __future__ import annotations

import asyncio

import pytest

from research_assistant import (
    config, inbox, jobs, period_budget, proactivity, schedules, watcher,
)
from research_assistant.clock import DAY_SECONDS, FakeClock
from research_assistant.daemon import AmbientDaemon
from research_assistant.period_budget import (
    STATE_DEGRADE, STATE_OK, STATE_PAUSE,
    add_usage, beat, build_daily_report, check_absence, check_budget,
    last_beat, note_scan_result, period_usage,
)
from research_assistant.proactivity import day_key

DAY = DAY_SECONDS

FLAGS = ("enable_period_budget", "enable_adaptive_scan", "enable_heartbeat",
         "enable_inbox", "enable_source_watch", "enable_proactivity")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(period_budget, "_DB_PATH", str(tmp_path / "period.db"))
    monkeypatch.setattr(schedules, "_DB_PATH", str(tmp_path / "schedules.db"))
    monkeypatch.setattr(jobs, "_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(inbox, "_DB_PATH", str(tmp_path / "inbox.db"))
    monkeypatch.setattr(watcher, "_DB_PATH", str(tmp_path / "snapshots.db"))
    monkeypatch.setattr(proactivity, "_DB_PATH", str(tmp_path / "quota.db"))
    for f in FLAGS:
        config.settings.__dict__[f] = False
    config.settings.__dict__["period_budget_tokens"] = 10_000
    config.settings.__dict__["period_soft_ratio"] = 0.8
    config.settings.__dict__["absence_alert_hours"] = 6.0
    config.settings.__dict__["adaptive_backoff_cap"] = 8
    yield
    for f in FLAGS:
        config.settings.__dict__[f] = False


# ── ① 时段钱包 ───────────────────────────────────────────────

def test_usage_accumulates_across_runs():
    clock = FakeClock()
    add_usage(3000, clock=clock)
    add_usage(2000, clock=clock)
    u = period_usage(day_key(clock.now()))
    assert u["tokens"] == 5000 and u["runs"] == 2


def test_usage_separated_by_day():
    clock = FakeClock()
    add_usage(3000, clock=clock)
    clock.advance(DAY)
    add_usage(100, clock=clock)
    assert period_usage(day_key(clock.now()))["tokens"] == 100


def test_check_budget_three_states():
    clock = FakeClock()
    assert check_budget(clock=clock)["state"] == STATE_OK
    add_usage(8_000, clock=clock)                      # 80% → 软线
    assert check_budget(clock=clock)["state"] == STATE_DEGRADE
    add_usage(2_000, clock=clock)                      # 100% → 硬线
    b = check_budget(clock=clock)
    assert b["state"] == STATE_PAUSE and b["used"] == 10_000


# ── ② 自适应扫描 ─────────────────────────────────────────────

def test_no_change_streak_backs_off_on_grid():
    clock = FakeClock()
    s = schedules.add_schedule("主题", DAY, clock=clock)
    schedules.mark_fired(s["schedule_id"], now=clock.now())    # 跑了一班
    r1 = note_scan_result(s["schedule_id"], had_changes=False, clock=clock)
    assert r1["streak"] == 1 and r1["multiplier"] == 2
    assert r1["next_run_at"] == clock.now() + 2 * DAY          # last_run + 2×base
    r2 = note_scan_result(s["schedule_id"], had_changes=False, clock=clock)
    assert r2["streak"] == 2 and r2["multiplier"] == 4


def test_backoff_capped():
    clock = FakeClock()
    s = schedules.add_schedule("主题", DAY, clock=clock)
    schedules.mark_fired(s["schedule_id"], now=clock.now())
    for _ in range(6):
        r = note_scan_result(s["schedule_id"], had_changes=False, clock=clock)
    assert r["multiplier"] == 8            # cap=8：最长 8 天一扫，不会退到无穷


def test_change_resets_streak_to_base_grid():
    clock = FakeClock()
    s = schedules.add_schedule("主题", DAY, clock=clock)
    schedules.mark_fired(s["schedule_id"], now=clock.now())
    note_scan_result(s["schedule_id"], had_changes=False, clock=clock)
    grid_next = schedules.get_schedule(s["schedule_id"])
    r = note_scan_result(s["schedule_id"], had_changes=True, clock=clock)
    assert r["streak"] == 0 and r["multiplier"] == 1
    assert schedules.get_schedule(s["schedule_id"])["no_change_streak"] == 0


# ── ③ 心跳与缺勤 ─────────────────────────────────────────────

def test_beat_and_tick_count():
    clock = FakeClock()
    beat(clock=clock)
    beat(clock=clock)
    hb = last_beat()
    assert hb["tick_count"] == 2 and hb["last_beat"] == clock.now()


def test_first_startup_is_not_absence():
    """首次启动无心跳历史——没上过班谈不上旷工。"""
    a = check_absence(clock=FakeClock())
    assert a["absent"] is False and a["gap_hours"] is None


def test_absence_detected_after_gap():
    clock = FakeClock()
    beat(clock=clock)
    clock.advance(7 * 3600)                # 7h > 阈值 6h
    a = check_absence(clock=clock)
    assert a["absent"] is True and a["gap_hours"] == 7.0


def test_recent_beat_is_not_absence():
    clock = FakeClock()
    beat(clock=clock)
    clock.advance(3600)
    assert check_absence(clock=clock)["absent"] is False


# ── ④ 日报 ───────────────────────────────────────────────────

def test_daily_report_aggregates():
    clock = FakeClock()
    j = jobs.submit_job("主题", "t1")
    jobs.update_status(j["task_id"], jobs.STATUS_DONE)
    add_usage(1234, clock=clock)
    inbox.add_entry(inbox.KIND_NOTIFY, "主题", "n", clock=clock)
    inbox.add_entry(inbox.KIND_DIGEST, "主题", "d", clock=clock)
    beat(clock=clock)
    # jobs.updated_at 用真实 time.time()——把日报的 day 对齐到真实今天
    import time as _t
    report = build_daily_report(day_key(_t.time()), clock=clock)
    assert "1成/0败" in report and "✅" in report


def test_daily_report_flags_failures():
    import time as _t
    j = jobs.submit_job("主题", "t1")
    jobs.update_status(j["task_id"], jobs.STATUS_FAILED, error="x")
    report = build_daily_report(day_key(_t.time()), clock=FakeClock())
    assert "1败" in report and "⚠️" in report


# ── daemon 集成 ──────────────────────────────────────────────

def _mock_research(status="researched", brief="🆕 x"):
    async def run(topic, change_set, thread_id):
        out = {"status": status, "brief": brief}
        if status == "researched":
            out["result"] = {"report": "", "token_usage": 4000}
        return out
    return run


def test_daemon_pause_skips_next_cycle_but_not_running():
    """pause 挡下一班：预算烧尽后 run_cycle 直接返回 budget_paused，不进研究。"""
    config.settings.__dict__["enable_period_budget"] = True
    clock = FakeClock()
    add_usage(10_000, clock=clock)         # 烧尽
    d = AmbientDaemon(clock=clock, run_research=_mock_research())
    out = asyncio.run(d.run_cycle("主题"))
    assert out["status"] == "budget_paused"
    assert jobs.list_jobs() == []          # 连 job 都没开（挡在门口）


def test_daemon_records_usage_after_cycle():
    config.settings.__dict__["enable_period_budget"] = True
    clock = FakeClock()
    d = AmbientDaemon(clock=clock, run_research=_mock_research())
    asyncio.run(d.run_cycle("主题"))
    assert period_usage(day_key(clock.now()))["tokens"] == 4000


def test_daemon_heartbeat_per_tick_and_next_day_resumes():
    config.settings.__dict__["enable_period_budget"] = True
    config.settings.__dict__["enable_heartbeat"] = True
    clock = FakeClock()
    add_usage(10_000, clock=clock)
    schedules.add_schedule("主题", DAY, clock=clock)
    d = AmbientDaemon(clock=clock, run_research=_mock_research())
    rep = asyncio.run(d.step())
    assert rep["ran"][0]["status"] == "budget_paused"
    assert last_beat()["tick_count"] == 1          # 暂停的班次也有心跳
    clock.advance(DAY)                             # 次日预算恢复
    rep2 = asyncio.run(d.step())
    assert rep2["ran"][0]["status"] == "researched"


def test_daemon_startup_absence_alert():
    config.settings.__dict__["enable_heartbeat"] = True
    config.settings.__dict__["enable_inbox"] = True
    clock = FakeClock()
    beat(clock=clock)                      # 上次活着
    clock.advance(2 * DAY)                 # 死了两天
    d = AmbientDaemon(clock=clock, run_research=_mock_research())
    rep = asyncio.run(d.startup())
    assert rep["absence"]["absent"] is True
    assert inbox.unread_count(inbox.KIND_ALERT) == 1


def test_daemon_adaptive_scan_backs_off_but_failed_does_not():
    """no_change 退避；source_failed 不动 streak（没看到 ≠ 世界安静）。"""
    config.settings.__dict__["enable_adaptive_scan"] = True
    clock = FakeClock()
    s = schedules.add_schedule("主题", DAY, clock=clock)

    d1 = AmbientDaemon(clock=clock, run_research=_mock_research("no_change", "✅"))
    asyncio.run(d1.step())
    assert schedules.get_schedule(s["schedule_id"])["no_change_streak"] == 1

    # 拨到退避后的下一班（2 天后），这班信源故障 → streak 保持 1
    clock.advance(2 * DAY)
    d2 = AmbientDaemon(clock=clock, run_research=_mock_research("source_failed", "⚠️"))
    asyncio.run(d2.step())
    assert schedules.get_schedule(s["schedule_id"])["no_change_streak"] == 1
