"""Ambient L08 测试：收益矩阵评估。

测试原则：
    - 全离线（mock 研究 + FakeClock + 临时库），矩阵本体就是被测物
    - 灵魂用例：确定性（同一时间线跑两遍结果一致）+ 逐档边际收益方向正确
"""
from __future__ import annotations

import asyncio

import pytest

from eval_agent.run_ambient_eval import (
    ALL_FLAGS, EVENTS, baseline_row, render_report, run_matrix,
)
from research_assistant import config


@pytest.fixture(autouse=True)
def _restore_flags():
    yield
    for f in ALL_FLAGS:
        config.settings.__dict__[f] = False
    config.settings.__dict__["proactivity_policy"] = "threshold"


def _matrix():
    return asyncio.run(run_matrix())


def test_matrix_has_five_configs():
    rows = _matrix()
    assert len(rows) == 5
    assert rows[0]["config"].startswith("baseline")
    assert rows[-1]["config"].startswith("full")


def test_baseline_row_reflects_l00_gaps():
    b = baseline_row()
    assert b["recall"] == f"0/{len(EVENTS)}"
    assert b["interrupts"] == 5 and b["silent_failure"] == 1
    assert b["absence_detected"] == 0


def test_cron_only_buys_attendance():
    """cron 档六指标与 baseline 全同——出勤自动化了，判断一点没买到。"""
    rows = _matrix()
    base, cron = rows[0], rows[1]
    for k in ("recall", "interrupts", "precision", "silent_failure", "tokens_5d"):
        assert cron[k] == base[k], k


def test_watcher_fixes_recall_silence_and_cost():
    rows = _matrix()
    cron, w = rows[1], rows[2]
    assert w["recall"] == f"{len(EVENTS)}/{len(EVENTS)}"   # 变化被点名
    assert w["silent_failure"] == 0                        # Day5 走告警不冒充结论
    assert w["tokens_5d"] < cron["tokens_5d"] / 3          # 无变化日只花扫描钱


def test_judge_cuts_interrupts_to_one_precise():
    rows = _matrix()
    w, j = rows[2], rows[3]
    assert j["interrupts"] < w["interrupts"]
    assert j["interrupts"] == 1 and j["precision"] == 1.0  # 只打扰 Day4，正中


def test_full_adds_absence_detection():
    rows = _matrix()
    assert rows[3]["absence_detected"] == 0    # judge 档没心跳
    assert rows[4]["absence_detected"] == 1    # full 档崩溃被发现
    assert rows[4]["recall"] == f"{len(EVENTS)}/{len(EVENTS)}"


def test_matrix_is_deterministic():
    """同一条时间线跑两遍，六指标逐格一致（FakeClock + mock 的承诺）。"""
    assert _matrix() == _matrix()


def test_report_renders_table_and_zero_tax_note():
    report = render_report(_matrix())
    assert "| 配置 |" in report and "baseline·人肉盯梢" in report
    assert "纯净跑零税" in report
    assert "诚实代价" in report      # 退避的发现延迟被写进解读，不藏
