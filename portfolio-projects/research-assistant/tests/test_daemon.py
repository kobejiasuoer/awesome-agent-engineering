"""Ambient L06 测试：常驻守护进程（daemon）。

测试原则（对齐 conftest.py）：
    - 全依赖注入：FakeClock + mock run_research + tmp 库（schedules/jobs/inbox/
      watcher/proactivity）——零真实等待、零 API、零联网
    - 灵魂用例：单轮失败不倒 daemon / overlap 跳过 / 孤儿恢复 / 5 天秒级跑完
"""
from __future__ import annotations

import asyncio

import pytest

from research_assistant import config, inbox, jobs, proactivity, schedules, watcher
from research_assistant.clock import DAY_SECONDS, FakeClock
from research_assistant.daemon import AmbientDaemon
from research_assistant.watcher import WatchItem

DAY = DAY_SECONDS

FLAGS = ("enable_source_watch", "enable_incremental_run", "enable_proactivity",
         "enable_inbox", "enable_hitl", "enable_schedules")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(schedules, "_DB_PATH", str(tmp_path / "schedules.db"))
    monkeypatch.setattr(jobs, "_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(inbox, "_DB_PATH", str(tmp_path / "inbox.db"))
    monkeypatch.setattr(watcher, "_DB_PATH", str(tmp_path / "snapshots.db"))
    monkeypatch.setattr(proactivity, "_DB_PATH", str(tmp_path / "quota.db"))
    for f in FLAGS:
        config.settings.__dict__[f] = False
    yield
    for f in FLAGS:
        config.settings.__dict__[f] = False


def _mock_research(status="researched", brief="🆕 新增: 有个新条目", report="报告"):
    calls = []

    async def run(topic, change_set, thread_id):
        calls.append({"topic": topic, "change_set": change_set,
                      "thread_id": thread_id})
        out = {"status": status, "brief": brief, "thread_id": thread_id}
        if status == "researched":
            out["result"] = {"report": report}
        return out

    run.calls = calls
    return run


def _daemon(clock, research, **kw):
    return AmbientDaemon(clock=clock, run_research=research, **kw)


# ── step / tick 基本语义 ─────────────────────────────────────

def test_step_without_due_schedule_does_nothing():
    clock = FakeClock()
    research = _mock_research()
    schedules.add_schedule("主题", DAY, clock=clock, first_run_at=clock.now() + DAY)
    report = asyncio.run(_daemon(clock, research).step())
    assert report["fired"] == 0 and research.calls == []


def test_step_fires_and_runs_cycle_with_job_bookkeeping():
    clock = FakeClock()
    research = _mock_research(status="no_change", brief="✅ 确认无变化")
    schedules.add_schedule("盯梢主题", DAY, clock=clock)
    report = asyncio.run(_daemon(clock, research).step())
    assert report["fired"] == 1 and len(report["ran"]) == 1
    assert report["ran"][0]["status"] == "no_change"
    done = jobs.list_jobs(status=jobs.STATUS_DONE)
    assert len(done) == 1 and done[0]["topic"] == "盯梢主题"


def test_overlap_skips_when_previous_run_still_running():
    clock = FakeClock()
    research = _mock_research()
    schedules.add_schedule("主题", DAY, clock=clock)
    # 模拟上一轮还在跑：同主题一个 running job
    j = jobs.submit_job("主题", "t-old")
    jobs.update_status(j["task_id"], jobs.STATUS_RUNNING)
    report = asyncio.run(_daemon(clock, research).step())
    assert report["skipped"] == [{"topic": "主题", "reason": "overlap"}]
    assert research.calls == []          # 本班没跑
    # 班次已 mark_fired：下一班在网格上（不会积压重放）
    assert schedules.list_schedules()[0]["next_run_at"] > clock.now()


def test_catchup_missed_recorded():
    clock = FakeClock()
    research = _mock_research(status="no_change")
    schedules.add_schedule("主题", DAY, clock=clock)
    clock.advance(3.5 * DAY)             # daemon 死了 3.5 天
    report = asyncio.run(_daemon(clock, research).step())
    assert report["caught_up_missed"] == 3
    assert len(report["ran"]) == 1       # 补跑一班，不逐班重放


# ── cycle：投递矩阵 ──────────────────────────────────────────

def test_cycle_researched_delivers_via_proactivity():
    config.settings.__dict__["enable_inbox"] = True
    config.settings.__dict__["enable_proactivity"] = True
    clock = FakeClock()
    research = _mock_research(brief="✏️ 修正: 结论已反转")   # 规则判级 major
    out = asyncio.run(_daemon(clock, research).run_cycle("主题"))
    assert out["decision"]["decision"] == "notify_now"
    assert inbox.unread_count(inbox.KIND_NOTIFY) == 1


def test_cycle_no_change_stays_silent():
    config.settings.__dict__["enable_inbox"] = True
    config.settings.__dict__["enable_proactivity"] = True
    clock = FakeClock()
    research = _mock_research(status="no_change", brief="✅ 确认无变化")
    asyncio.run(_daemon(clock, research).run_cycle("主题"))
    assert inbox.unread_count() == 0     # 沉默：收件箱一条不进


def test_cycle_source_failed_goes_to_alert_channel():
    config.settings.__dict__["enable_inbox"] = True
    config.settings.__dict__["enable_proactivity"] = True
    clock = FakeClock()
    research = _mock_research(status="source_failed", brief="⚠️ 没能看到信源")
    asyncio.run(_daemon(clock, research).run_cycle("主题"))
    assert inbox.unread_count(inbox.KIND_ALERT) == 1
    assert inbox.unread_count(inbox.KIND_NOTIFY) == 0   # 不进内容判级通道


def test_cycle_without_proactivity_defaults_to_digest():
    """判级关：保守路径——产出全进 digest（不打扰也不丢）。"""
    config.settings.__dict__["enable_inbox"] = True
    clock = FakeClock()
    research = _mock_research(brief="任意产出")
    asyncio.run(_daemon(clock, research).run_cycle("主题"))
    assert inbox.unread_count(inbox.KIND_DIGEST) == 1


def test_cycle_watch_disabled_passes_none_change_set():
    clock = FakeClock()
    research = _mock_research(status="no_change")
    asyncio.run(_daemon(clock, research).run_cycle("主题"))
    assert research.calls[0]["change_set"] is None    # 全量语义


def test_cycle_watch_enabled_passes_change_set():
    config.settings.__dict__["enable_source_watch"] = True
    clock = FakeClock()
    research = _mock_research(status="no_change")
    fetch = lambda: [WatchItem("a", "A", "甲")]  # noqa: E731
    d = AmbientDaemon(clock=clock, run_research=research, fetch=fetch,
                      source_id="s1")
    asyncio.run(d.run_cycle("主题"))
    cs = research.calls[0]["change_set"]
    assert cs is not None and cs.first_scan


# ── 常驻纪律①：单轮失败不倒 daemon ──────────────────────────

def test_cycle_exception_marks_failed_and_daemon_survives():
    config.settings.__dict__["enable_inbox"] = True
    clock = FakeClock()

    async def boom(topic, change_set, thread_id):
        raise RuntimeError("研究图炸了")

    d = AmbientDaemon(clock=clock, run_research=boom)
    out = asyncio.run(d.run_cycle("主题"))          # 不抛
    assert out["status"] == "failed"
    assert jobs.list_jobs(status=jobs.STATUS_FAILED)
    assert inbox.unread_count(inbox.KIND_ALERT) == 1   # 失败有告警


# ── HITL 挂起 → 审批条目 ─────────────────────────────────────

def test_cycle_awaiting_approval_files_inbox_entry(monkeypatch):
    config.settings.__dict__["enable_inbox"] = True
    config.settings.__dict__["enable_hitl"] = True
    clock = FakeClock()
    research = _mock_research()
    monkeypatch.setattr("research_assistant.service.is_awaiting_approval",
                        lambda tid: {"question": "要发布吗"})
    out = asyncio.run(_daemon(clock, research).run_cycle("主题"))
    assert out["status"] == "awaiting_approval"
    assert len(inbox.pending_approvals()) == 1
    aw = jobs.list_jobs(status=jobs.STATUS_AWAITING_APPROVAL)
    assert len(aw) == 1


# ── 启动序列：孤儿恢复 ───────────────────────────────────────

def test_startup_recovers_orphans():
    clock = FakeClock()
    j = jobs.submit_job("主题", "t-orphan")
    jobs.update_status(j["task_id"], jobs.STATUS_RUNNING)   # 假装上次崩了
    resumed = []

    async def fake_resume(task_id):
        resumed.append(task_id)
        jobs.update_status(task_id, jobs.STATUS_DONE)
        return {}

    d = AmbientDaemon(clock=clock, run_research=_mock_research(),
                      resume_orphan=fake_resume)
    report = asyncio.run(d.startup())
    assert report["orphans_found"] == 1 and resumed == [j["task_id"]]


def test_startup_marks_unrecoverable_orphan_failed():
    clock = FakeClock()
    j = jobs.submit_job("主题", "t-orphan")
    jobs.update_status(j["task_id"], jobs.STATUS_RUNNING)

    async def bad_resume(task_id):
        raise RuntimeError("checkpoint 损坏")

    d = AmbientDaemon(clock=clock, run_research=_mock_research(),
                      resume_orphan=bad_resume)
    report = asyncio.run(d.startup())
    assert report["recover_failed"] == [j["task_id"]]
    assert jobs.get_job(j["task_id"])["status"] == jobs.STATUS_FAILED  # 不留僵尸


# ── 主循环：5 天秒级跑完 + 优雅退出 ──────────────────────────

def test_run_loop_five_days_in_milliseconds():
    """可注入时钟的收官验证：5 个模拟日的常驻运行，测试里毫秒级。"""
    clock = FakeClock()
    research = _mock_research(status="no_change")
    schedules.add_schedule("盯梢", DAY, clock=clock)
    d = _daemon(clock, research)
    asyncio.run(d.run_loop(poll_seconds=DAY, max_ticks=5))
    assert d.tick_count == 5
    assert len(research.calls) == 5      # 每天一班全跑到


def test_request_stop_exits_loop_gracefully():
    clock = FakeClock()
    research = _mock_research(status="no_change")
    d = _daemon(clock, research)

    stop_after_2 = {"n": 0}

    def on_tick():
        stop_after_2["n"] += 1
        if stop_after_2["n"] >= 2:
            d.request_stop()

    d._on_tick = on_tick
    asyncio.run(d.run_loop(poll_seconds=1.0, max_ticks=100))
    assert d.tick_count == 2             # 第 2 tick 后优雅退出，没跑满 100


def test_on_tick_exception_does_not_kill_loop():
    clock = FakeClock()
    research = _mock_research(status="no_change")

    def bad_hook():
        raise RuntimeError("心跳挂了")

    d = AmbientDaemon(clock=clock, run_research=research, on_tick=bad_hook)
    asyncio.run(d.run_loop(poll_seconds=1.0, max_ticks=3))
    assert d.tick_count == 3             # 钩子炸了主循环照常
