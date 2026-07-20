"""改道与权限门测试（Harness 课程 L07）。

锁死四类契约：
    1. 改道队列：投递/拉取/合并留痕/历史审计（sqlite 隔离）
    2. 安全点语义：协商不抢占——只在安全点合并；cancel 受理即软停
    3. 权限门红线：写出工作区/网络写/超阈花费 100% needs_approval，判定留痕
    4. 长途跑法：改道后源序可见改变+三态标注；软停出诚实半程声明
"""
from __future__ import annotations

import pytest

from research_assistant import steering
from research_assistant.config import settings
from research_assistant.steering import ToolAction, gate_tool


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    steering.set_db_path_for_test(str(tmp_path / "steering.db"))
    monkeypatch.setitem(settings.__dict__, "enable_steering", False)
    monkeypatch.setitem(settings.__dict__, "enable_tool_gate", False)
    monkeypatch.setitem(settings.__dict__, "tool_gate_cost_threshold", 10000)
    monkeypatch.setitem(settings.__dict__, "workspace_dir", str(tmp_path / "ws"))
    yield


# ── 改道队列 ─────────────────────────────────────────────────
def test_queue_submit_pending_apply_history():
    i1 = steering.submit_instruction("优先 safety 类")
    steering.submit_instruction("尽快收尾", kind=steering.KIND_CANCEL)
    assert [p["id"] for p in steering.pending_instructions()] == [i1, i1 + 1]
    steering.mark_applied(i1, "于第 10 源后合并")
    assert [p["id"] for p in steering.pending_instructions()] == [i1 + 1]
    h = steering.history()
    assert h[0]["applied"] and "第 10 源" in h[0]["merge_note"]
    assert not h[1]["applied"]


def test_poll_safepoint_merges_with_trace():
    """安全点合并：计划尾部带改道记录，指令标记已应用（留痕铁律）。"""
    steering.submit_instruction("跳过 marketing 类")
    plan, applied, cancel = steering.poll_safepoint("目标：全量研究。", "第 5 源完成后")
    assert len(applied) == 1 and not cancel
    assert "改道记录（第 5 源完成后）" in plan and "跳过 marketing" in plan
    assert steering.pending_instructions() == []       # 已应用不再 pending


def test_poll_safepoint_detects_cancel():
    steering.submit_instruction("收尾吧", kind=steering.KIND_CANCEL)
    plan, applied, cancel = steering.poll_safepoint("目标。", "第 3 源完成后")
    assert cancel and plan == "目标。"                  # cancel 不改计划，只请求软停


def test_poll_safepoint_noop_when_empty():
    plan, applied, cancel = steering.poll_safepoint("原计划。", "第 1 源完成后")
    assert plan == "原计划。" and applied == [] and not cancel


# ── 权限门 ───────────────────────────────────────────────────
def test_gate_allows_workspace_write(tmp_path):
    ws_root = tmp_path / "ws"
    v, _ = gate_tool(ToolAction("write_file", str(ws_root / "run1" / "draft.md")),
                     workspace_root=ws_root)
    assert v == "allow"


def test_gate_blocks_dangerous_100_percent(tmp_path):
    """红线：三类危险动作 100% needs_approval（逐条锁死）。"""
    ws_root = tmp_path / "ws"
    dangerous = [
        ToolAction("write_file", "C:/Windows/system32/hosts"),        # 写出工作区
        ToolAction("delete_file", str(tmp_path / "outside.txt")),     # 删出工作区
        ToolAction("http", "https://api.example.com/publish", method="POST"),
        ToolAction("http", "https://api.example.com/x", method="DELETE"),
        ToolAction("web_search", "", cost_tokens=99999),              # 花费超阈
    ]
    for a in dangerous:
        v, reason = gate_tool(a, workspace_root=ws_root)
        assert v == "needs_approval", f"{a} 未被拦截"
        assert reason


def test_gate_allows_reads_and_cheap_calls():
    v1, _ = gate_tool(ToolAction("http", "https://a.com", method="GET"))
    v2, _ = gate_tool(ToolAction("web_search", "查询", cost_tokens=500))
    assert v1 == "allow" and v2 == "allow"


def test_gate_log_records_all_verdicts(tmp_path):
    """放行与拦截同样留痕——「拦过什么」与「放过什么」都可审计。"""
    gate_tool(ToolAction("web_search", "q", cost_tokens=10))
    gate_tool(ToolAction("http", "https://x.com/p", method="POST"))
    logrows = steering.gate_log()
    assert [r["verdict"] for r in logrows] == ["allow", "needs_approval"]


# ── 长途跑法 ─────────────────────────────────────────────────
def test_steered_longhaul_reroutes(tmp_path):
    """改道线：第 10 源后指令 → 安全点合并 → safety 提前、marketing 跳过。"""
    from eval_agent.harness_runs import run_steered_longhaul
    r = run_steered_longhaul(workspace_base=tmp_path, run_id="s", steer_after=10)
    assert r["steer_applied_at"] == 10                       # 安全点=下一个源间隙
    assert r["skipped_by_instruction"] == ["S12", "S19", "S24", "S29"]
    assert r["order_after_steer"][:4] == ["S13", "S16", "S22", "S27"]  # safety 提前
    assert r["completed_sources"] == 26
    assert r["presence_hits"] == 20                          # 营销源零事实：跳过无损
    assert "改道记录" in r["plan_final"]                     # 计划留痕
    assert any(h["applied"] for h in r["steering_history"])
    assert "不是失败" in r["honest_stop_note"]               # 跳过≠失败（三态可区分）


def test_steered_longhaul_cancel(tmp_path):
    """软停线：cancel 指令于安全点受理——完成当前源即止，诚实半程声明。"""
    from eval_agent.harness_runs import run_steered_longhaul
    r = run_steered_longhaul(workspace_base=tmp_path, run_id="c",
                             steer_after=None, cancel_after=12)
    assert r["cancelled_at"] == 12 and r["completed_sources"] == 12
    assert "已研 12/30" in r["honest_stop_note"]
    assert 0 < r["presence_hits"] < 20                       # 半程产物也是产物


def test_steered_longhaul_no_instructions_is_plain(tmp_path):
    """不投指令=行为与 L06 工作区档一致（驾驶舱静默时零介入）。"""
    from eval_agent.harness_runs import run_steered_longhaul
    r = run_steered_longhaul(workspace_base=tmp_path, run_id="p",
                             steer_after=None, cancel_after=None)
    assert r["completed_sources"] == 30 and r["skipped_by_instruction"] == []
    assert r["steer_applied_at"] is None and r["presence_hits"] == 20


def test_steered_longhaul_deterministic(tmp_path):
    import json
    from eval_agent.harness_runs import run_steered_longhaul
    stable = ("completed_sources", "skipped_by_instruction", "order_after_steer",
              "presence", "plan_final", "main_peak_tokens", "total_fetches")

    def run(tag):
        steering.set_db_path_for_test(str(tmp_path / f"{tag}.db"))
        r = run_steered_longhaul(workspace_base=tmp_path / tag, run_id="d",
                                 steer_after=10)
        return json.dumps({k: r[k] for k in stable}, ensure_ascii=False, sort_keys=True)

    assert run("a") == run("b")
