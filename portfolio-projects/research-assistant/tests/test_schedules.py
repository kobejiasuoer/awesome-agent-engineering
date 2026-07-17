"""Ambient L01 测试：调度器（触发与调度）。

测试原则（对齐 conftest.py）：
    - 时间全部走 FakeClock：快进 5「天」零真实等待（本课命根子）
    - 调度表 / jobs 注册表用 tmp_path 隔离
    - 不碰研究图：调度器只管叫醒（dispatch 登记 job），不管跑
"""
from __future__ import annotations

import pytest

from research_assistant import jobs, schedules
from research_assistant.clock import FakeClock, DAY_SECONDS
from research_assistant.schedules import Scheduler, make_job_dispatch

DAY = DAY_SECONDS


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """每个测试用独立的调度表 + jobs 注册表。"""
    monkeypatch.setattr(schedules, "_DB_PATH", str(tmp_path / "schedules.db"))
    monkeypatch.setattr(jobs, "_DB_PATH", str(tmp_path / "jobs.db"))
    yield


# ── add / get / list ─────────────────────────────────────────

def test_add_and_get_schedule():
    clock = FakeClock()
    s = schedules.add_schedule("盯梢主题", DAY, clock=clock)
    assert s["schedule_id"].startswith("sch-")
    assert s["topic"] == "盯梢主题"
    assert s["interval_seconds"] == DAY
    assert s["enabled"] is True
    assert s["missed_count"] == 0
    # first_run_at 缺省 = 现在（注册即到期：先建仓）
    assert s["next_run_at"] == clock.now()


def test_add_schedule_rejects_bad_interval():
    with pytest.raises(ValueError):
        schedules.add_schedule("主题", 0)
    with pytest.raises(ValueError):
        schedules.add_schedule("主题", -3600)


def test_list_schedules_enabled_filter():
    clock = FakeClock()
    a = schedules.add_schedule("A", DAY, clock=clock)
    b = schedules.add_schedule("B", DAY, clock=clock)
    schedules.set_enabled(b["schedule_id"], False)
    all_ids = {s["schedule_id"] for s in schedules.list_schedules()}
    on_ids = {s["schedule_id"] for s in schedules.list_schedules(enabled_only=True)}
    assert all_ids == {a["schedule_id"], b["schedule_id"]}
    assert on_ids == {a["schedule_id"]}


# ── due / tick 基本语义 ──────────────────────────────────────

def test_not_due_before_time():
    clock = FakeClock()
    schedules.add_schedule("主题", DAY, clock=clock,
                           first_run_at=clock.now() + DAY)
    assert schedules.due_schedules(clock.now()) == []
    fired = Scheduler(clock=clock).tick()
    assert fired == []


def test_tick_fires_when_due():
    clock = FakeClock()
    s = schedules.add_schedule("主题", DAY, clock=clock)  # 注册即到期
    fired = Scheduler(clock=clock).tick()
    assert len(fired) == 1
    assert fired[0]["schedule_id"] == s["schedule_id"]
    assert fired[0]["missed"] == 0
    # 下一班 = 本班 + interval（固定网格）
    assert fired[0]["next_run_at"] == s["next_run_at"] + DAY


def test_tick_twice_same_moment_fires_once():
    clock = FakeClock()
    schedules.add_schedule("主题", DAY, clock=clock)
    sch = Scheduler(clock=clock)
    assert len(sch.tick()) == 1
    assert sch.tick() == []  # 同一时刻再 tick：下一班还没到


def test_disabled_schedule_not_fired():
    clock = FakeClock()
    s = schedules.add_schedule("主题", DAY, clock=clock)
    schedules.set_enabled(s["schedule_id"], False)
    assert Scheduler(clock=clock).tick() == []
    # 恢复后可触发
    schedules.set_enabled(s["schedule_id"], True)
    assert len(Scheduler(clock=clock).tick()) == 1


def test_five_day_fastforward_fires_five_times():
    """5 天调度行为在测试里秒级跑完（可注入时钟 = 本课命根子）。"""
    clock = FakeClock()
    schedules.add_schedule("盯梢", DAY, clock=clock)
    sch = Scheduler(clock=clock)
    total = []
    for _ in range(5):
        total.extend(sch.tick())
        clock.advance_days(1)
    assert len(total) == 5
    assert all(f["missed"] == 0 for f in total)


# ── missed / 固定班次网格 ────────────────────────────────────

def test_missed_counting_when_late():
    """3.5 个周期没 tick → 本次只触发一次，missed=3，下一班仍在网格上。"""
    clock = FakeClock()
    s = schedules.add_schedule("主题", DAY, clock=clock)
    grid0 = s["next_run_at"]
    clock.advance(3.5 * DAY)
    fired = Scheduler(clock=clock).tick()
    assert len(fired) == 1
    assert fired[0]["missed"] == 3
    # 固定网格：next = grid0 + (3+1)×interval（在 now 之后的第一班）
    assert fired[0]["next_run_at"] == grid0 + 4 * DAY
    assert fired[0]["next_run_at"] > clock.now()
    assert schedules.get_schedule(s["schedule_id"])["missed_count"] == 3


def test_fixed_grid_does_not_drift():
    """晚触发不让班次后漂：每次都晚 6 小时 tick，班次仍按天对齐。"""
    clock = FakeClock()
    s = schedules.add_schedule("主题", DAY, clock=clock)
    grid0 = s["next_run_at"]
    sch = Scheduler(clock=clock)
    for k in range(1, 4):
        clock.advance(DAY if k > 1 else 0.25 * DAY)  # 首班晚 6h 触发
        fired = sch.tick()
        assert len(fired) == 1
        # 第 k 班的 next 永远是 grid0 + k×DAY（不受触发晚点影响）
        assert fired[0]["next_run_at"] == grid0 + k * DAY


def test_set_interval_only_affects_future():
    clock = FakeClock()
    s = schedules.add_schedule("主题", DAY, clock=clock)
    next_before = schedules.get_schedule(s["schedule_id"])["next_run_at"]
    schedules.set_interval(s["schedule_id"], 2 * DAY)
    # 已排定的 next_run_at 不动（最小惊讶）
    assert schedules.get_schedule(s["schedule_id"])["next_run_at"] == next_before
    # 触发后按新间隔排班
    fired = Scheduler(clock=clock).tick()
    assert fired[0]["next_run_at"] == next_before + 2 * DAY


# ── dispatch：调度器只管叫醒，不管跑 ─────────────────────────

def test_dispatch_registers_pending_job():
    clock = FakeClock()
    schedules.add_schedule("盯梢主题", DAY, clock=clock)
    fired = Scheduler(clock=clock, dispatch=make_job_dispatch()).tick()
    job = fired[0]["dispatch_result"]
    assert job["status"] == jobs.STATUS_PENDING
    assert job["topic"] == "盯梢主题"
    # 注册表里真的有这条（执行留给 daemon，调度器不 invoke 图）
    assert jobs.get_job(job["task_id"])["status"] == jobs.STATUS_PENDING


def test_dispatch_exception_does_not_lose_fire_record():
    """dispatch 抛错不吞触发：班次已 mark_fired（不会重复触发同一班）。"""
    clock = FakeClock()
    s = schedules.add_schedule("主题", DAY, clock=clock)

    def bad_dispatch(_sch):
        raise RuntimeError("下游炸了")

    sch = Scheduler(clock=clock, dispatch=bad_dispatch)
    with pytest.raises(RuntimeError):
        sch.tick()
    # mark_fired 先于 dispatch：这一班已记账，不会因 dispatch 失败被重复触发
    assert schedules.get_schedule(s["schedule_id"])["next_run_at"] > clock.now()
