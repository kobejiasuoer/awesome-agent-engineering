"""Ambient L02 测试：信源与变化检测（watcher）。

测试原则（对齐 conftest.py）：
    - 信源全 mock（5 日时间线 / 内存条目 / tmp 目录），零联网
    - 快照库用 tmp_path 隔离
    - 灵魂用例：failed ≠ 空变化集（「没能看到」不冒充「没有变化」）
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from research_assistant import watcher
from research_assistant.clock import FakeClock
from research_assistant.watcher import (
    WatchItem, content_hash, make_dir_fetch, normalize, scan_source,
)

# 时间线在 eval_agent 下（conftest 已把项目根加进 sys.path）
from eval_agent.ambient_timeline import AmbientTimeline, SourceUnavailableError


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, "_DB_PATH", str(tmp_path / "snapshots.db"))
    yield


def _tl_fetch(day: int):
    """时间线适配器：把 Day N 的信源变成 fetch callable（鸭子类型直接可用）。"""
    tl = AmbientTimeline()
    return lambda: tl.fetch_items(day)


# ── 规范化与指纹 ─────────────────────────────────────────────

def test_normalize_kills_whitespace_noise():
    assert normalize("a b\nc  d") == normalize("ab\tcd")
    assert normalize("内容，  并计划 ") == normalize("内容，并计划")


def test_content_hash_ignores_whitespace_but_not_rewording():
    a = WatchItem("x", "标题", "内容一样")
    b = WatchItem("x", "标题", "内容 一样  ")     # 空白微调 → 同指纹
    c = WatchItem("x", "标题", "内容不一样了")     # 真改写 → 不同指纹
    assert content_hash(a) == content_hash(b)
    assert content_hash(a) != content_hash(c)


# ── 5 日时间线逐日语义（贯穿硬任务）─────────────────────────

def test_day1_first_scan_is_baseline_not_alarm():
    cs = scan_source("tl", _tl_fetch(1))
    assert cs.ok and cs.first_scan
    assert len(cs.new_items) == 4
    assert watcher.snapshot_count("tl") == 4


def test_day2_shuffle_and_whitespace_is_no_change():
    """Day2：顺序打乱+空白微调 → 空变化集（L00 里文本 diff 误报 51% 的场景）。"""
    scan_source("tl", _tl_fetch(1))
    cs = scan_source("tl", _tl_fetch(2))
    assert cs.ok and not cs.first_scan
    assert cs.is_no_change()
    assert not cs.has_changes()


def test_day3_detects_exactly_the_new_item():
    scan_source("tl", _tl_fetch(1))
    scan_source("tl", _tl_fetch(2))
    cs = scan_source("tl", _tl_fetch(3))
    assert [it.item_id for it in cs.new_items] == ["item-e"]
    assert cs.changed_items == [] and cs.gone_item_ids == []


def test_day4_detects_new_and_changed():
    """Day4：重磅新增 item-f + item-c 内容反转（变更）。"""
    for d in (1, 2, 3):
        scan_source("tl", _tl_fetch(d))
    cs = scan_source("tl", _tl_fetch(4))
    assert [it.item_id for it in cs.new_items] == ["item-f"]
    assert [it.item_id for it in cs.changed_items] == ["item-c"]


def test_day5_failure_is_failed_not_empty():
    """灵魂用例：信源故障 → ok=False；绝不产出「空变化集」冒充无变化。"""
    scan_source("tl", _tl_fetch(1))
    cs = scan_source("tl", _tl_fetch(5))
    assert cs.ok is False
    assert "SourceUnavailableError" in cs.error
    assert not cs.is_no_change()          # failed 没资格说「确认无变化」
    assert not cs.has_changes()


def test_failed_scan_leaves_snapshot_intact():
    """故障期快照不动：恢复后与「最后一次看清的世界」对比，不误报全量新增。"""
    scan_source("tl", _tl_fetch(1))
    assert watcher.snapshot_count("tl") == 4
    scan_source("tl", _tl_fetch(5))       # 故障
    assert watcher.snapshot_count("tl") == 4   # 快照原封不动
    cs = scan_source("tl", _tl_fetch(2))  # 恢复（内容仍与 Day1 一致）
    assert cs.ok and cs.is_no_change()    # 不会把故障期误判成「全部消失又新增」


# ── gone 语义 ────────────────────────────────────────────────

def test_gone_reported_once_then_reappear_as_new():
    items_ab = [WatchItem("a", "A", "甲"), WatchItem("b", "B", "乙")]
    items_a = [WatchItem("a", "A", "甲")]
    scan_source("s", lambda: items_ab)
    cs = scan_source("s", lambda: items_a)
    assert cs.gone_item_ids == ["b"]
    cs2 = scan_source("s", lambda: items_a)      # 再扫：不重复报 gone
    assert cs2.is_no_change()
    cs3 = scan_source("s", lambda: items_ab)     # b 回来了 → 按 new 报
    assert [it.item_id for it in cs3.new_items] == ["b"]


# ── 多信源隔离 / 时钟注入 ────────────────────────────────────

def test_sources_are_isolated_by_source_id():
    scan_source("s1", lambda: [WatchItem("a", "A", "甲")])
    cs = scan_source("s2", lambda: [WatchItem("a", "A", "甲")])
    assert cs.first_scan                     # s2 有自己的快照空间


def test_scanned_at_uses_injected_clock():
    clock = FakeClock(start=123456.0)
    cs = scan_source("s", lambda: [], clock=clock)
    assert cs.scanned_at == 123456.0


# ── 目录适配器（离线真实信源）───────────────────────────────

def test_dir_fetch_adapter(tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    (d / "a.md").write_text("# 甲", encoding="utf-8")
    fetch = make_dir_fetch(d)
    cs = scan_source("dir", fetch)
    assert cs.first_scan and len(cs.new_items) == 1

    (d / "a.md").write_text("# 甲改", encoding="utf-8")     # 改内容 → changed
    (d / "b.txt").write_text("乙", encoding="utf-8")        # 新文件 → new
    cs2 = scan_source("dir", fetch)
    assert [it.item_id for it in cs2.changed_items] == ["a.md"]
    assert [it.item_id for it in cs2.new_items] == ["b.txt"]


def test_dir_fetch_missing_dir_is_failed(tmp_path):
    cs = scan_source("dir", make_dir_fetch(tmp_path / "nope"))
    assert cs.ok is False and "FileNotFoundError" in cs.error
