"""文件工作区测试（Harness 课程 L06）。

锁死四类契约：
    1. 工作区结构与指针协议：无损落盘/一行指针/人机共读目录树
    2. recitation：现读 plan.md（改了计划复述立刻变——文件是事实源）
    3. 双恢复（工作区半边）：attach 挂载 + 「有笔记=已研完」进度事实源
    4. 长途跑法：崩溃续跑 fetch 不重付（30 vs 无工作区 48）；指针 vs 全文
"""
from __future__ import annotations

import json

import pytest

from research_assistant.config import settings
from research_assistant.workspace import Workspace


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setitem(settings.__dict__, "workspace_dir", str(tmp_path / "ws"))
    monkeypatch.setitem(settings.__dict__, "enable_workspace", False)
    yield


# ── 结构与指针 ───────────────────────────────────────────────
def test_workspace_layout_and_tree():
    ws = Workspace("run-1")
    ws.write_plan("目标：完成调研。")
    ws.save_source("S01", "原文" * 100)
    ws.add_note("S01", "[S01] 结论")
    ws.write_draft("草稿")
    tree = ws.tree()
    assert "plan.md" in tree and "sources/" in tree and "notes/" in tree
    assert "S01.txt" in tree and "S01.md" in tree and "draft.md" in tree


def test_source_roundtrip_lossless():
    """原文无损落盘——被压缩/截断丢掉的，都能从这里回来。"""
    ws = Workspace("run-1")
    text = "完整原文，包含深埋事实：采用向量时钟。" * 50
    ws.save_source("S28", text)
    assert ws.read("sources/S28.txt") == text
    assert ws.has_source("S28") and not ws.has_source("S99")


def test_pointer_is_one_cheap_line():
    """指针协议：路径+体积+开头，一行、便宜（窗口里只住这一行）。"""
    ws = Workspace("run-1")
    ws.save_source("S17", "超长全文" * 2000)
    ptr = ws.pointer("sources/S17.txt")
    assert "sources/S17.txt" in ptr and "8,000 字" in ptr
    assert "\n" not in ptr and len(ptr) < 150
    assert "不存在" in ws.pointer("sources/S99.txt")


# ── recitation ───────────────────────────────────────────────
def test_recitation_reads_plan_fresh():
    """重读胜于记住：plan.md 改了，复述立刻跟着变（文件是事实源）。"""
    ws = Workspace("run-1")
    ws.write_plan("目标 A：全量研究。")
    assert "目标 A" in ws.recitation_block()
    ws.write_plan("目标 B：只研究 safety 类。")       # 改道（L07）改了计划
    block = ws.recitation_block()
    assert "目标 B" in block and "目标 A" not in block
    assert "现读自 plan.md" in block


def test_recitation_empty_without_plan():
    assert Workspace("run-2").recitation_block() == ""


# ── 双恢复（工作区半边）─────────────────────────────────────
def test_attach_sees_previous_process_files():
    """新进程 attach 同一 run_id：上个进程的工作集全部可见。"""
    ws1 = Workspace("run-x")
    ws1.save_source("S01", "原文")
    ws1.add_note("S01", "结论")
    ws2 = Workspace.attach("run-x")
    assert ws2.has_source("S01") and ws2.note_names() == ["S01"]


def test_note_names_are_progress_source_of_truth():
    """「有笔记=已研完」——断点续跑跳过依据（排序确定）。"""
    ws = Workspace("run-1")
    for d in ("S03", "S01", "S02"):
        ws.add_note(d, "done")
    assert ws.note_names() == ["S01", "S02", "S03"]


def test_workspace_dir_from_settings(monkeypatch, tmp_path):
    monkeypatch.setitem(settings.__dict__, "workspace_dir", str(tmp_path / "custom"))
    ws = Workspace("run-1")
    assert str(tmp_path / "custom") in str(ws.root)


# ── 长途跑法 ─────────────────────────────────────────────────
def test_workspace_longhaul_hero(tmp_path):
    """主角行：30/30、20/20、fetch 恰 30、后半程复述、指针远小于全文。"""
    from eval_agent.harness_runs import run_workspace_longhaul
    r = run_workspace_longhaul(workspace_base=tmp_path, run_id="hero")
    assert r["completed_sources"] == 30 and r["presence_hits"] == 20
    assert r["total_fetches"] == 30
    assert r["recitations"] == 15                    # 恰为后半程（S16–S30）
    assert r["pointer_chars"] * 20 < r["full_chars"]  # 指针 vs 全文 ≥20 倍差
    assert r["main_peak_tokens"] < 1200


def test_workspace_longhaul_crash_resume(tmp_path):
    """崩溃续跑：S18 后进程死亡 → attach 续跑——fetch 仍 30（前功不弃）。"""
    from eval_agent.harness_runs import run_workspace_longhaul
    r = run_workspace_longhaul(workspace_base=tmp_path, run_id="crash",
                               crash_at=18)
    assert r["crashed_and_resumed"] and r["completed_sources"] == 30
    assert r["total_fetches"] == 30                  # 已落盘的不重 fetch
    assert r["refetch_waste_without_ws"] == 48       # 无工作区重启=18+30（结构性推算）
    assert r["presence_hits"] == 20


def test_workspace_longhaul_deterministic(tmp_path):
    from eval_agent.harness_runs import run_workspace_longhaul
    a = run_workspace_longhaul(workspace_base=tmp_path / "a", run_id="d")
    b = run_workspace_longhaul(workspace_base=tmp_path / "b", run_id="d")
    ka = json.dumps({k: v for k, v in a.items() if k != "workspace_tree"},
                    ensure_ascii=False, sort_keys=True)
    kb = json.dumps({k: v for k, v in b.items() if k != "workspace_tree"},
                    ensure_ascii=False, sort_keys=True)
    assert ka == kb
