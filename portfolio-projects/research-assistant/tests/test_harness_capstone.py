"""L09 收官测试：v5 全套合体 + 收益矩阵 + 纯净回归。

锁死四类契约：
    1. v5 全套：八机制协同——26+4 跳、20/20、跨会话偏好在场、改道生效、
       主窗全程 safe 区
    2. 收益矩阵：五行形状 + killer row（B 档 8/20）+ E 档双 ✅
    3. 确定性：矩阵双跑逐字节一致（报告可复现）
    4. 纯净回归：九个 Harness 开关默认全关（零税声明的机械锁）
"""
from __future__ import annotations

import json

import pytest

from research_assistant import steering
from research_assistant.config import Settings


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    steering.set_db_path_for_test(str(tmp_path / "steer.db"))
    yield


def _run_full(tmp_path, tag: str):
    from eval_agent.harness_runs import run_full_longhaul
    steering.set_db_path_for_test(str(tmp_path / f"{tag}.db"))
    return run_full_longhaul(workspace_base=tmp_path / f"ws-{tag}",
                             memory_base=tmp_path / f"mem-{tag}",
                             run_id=f"cap-{tag}")


def test_v5_full_longhaul_hero(tmp_path):
    """收官主行：八机制协同的端到端验收（任务书 L09 逐条）。"""
    r = _run_full(tmp_path, "hero")
    assert r["completed_sources"] == 26                      # 30 - 4 营销源
    assert r["skipped_by_instruction"] == ["S12", "S19", "S24", "S29"]
    assert r["steer_applied_at"] == 10                       # 改道生效
    assert r["presence_hits"] == 20                          # 关键事实全在场
    assert r["contradiction_discoverable"]                   # 跨源矛盾可发现
    assert r["prefs_present_across_sessions"]                # 会话 1 偏好活到会话 2
    assert r["main_peak_tokens"] < 1500                      # 主窗全程低位
    assert set(r["zone_counts"]) == {"safe"}                 # 每次调用都在安全区
    assert r["compactions"] == 0                             # 外置让压缩失业
    assert r["total_fetches"] == 26                          # 跳过的源连 fetch 都省


def test_v5_full_longhaul_deterministic(tmp_path):
    a = json.dumps(_run_full(tmp_path, "d1"), ensure_ascii=False, sort_keys=True)
    b = json.dumps(_run_full(tmp_path, "d2"), ensure_ascii=False, sort_keys=True)
    assert a == b


def test_matrix_rows_and_killer_row(tmp_path):
    """矩阵五行形状 + killer row：B 档活着（30/30）但失忆（8/20）。"""
    from eval_agent.run_harness_eval import collect_rows
    rows = collect_rows()
    assert [r["config"][:1] for r in rows] == ["A", "B", "C", "D", "E"]
    a, b, c, d, e = rows
    assert a["presence"] == "0/20" and "死于" in a["verdict"]
    assert b["completed"] == "30/30" and b["presence"] == "8/20"   # killer row
    assert c["presence"] == "20/20" and d["presence"] == "20/20"
    assert e["steer"] == "✅" and e["session"] == "✅"
    assert e["presence"] == "20/20"


def test_matrix_report_deterministic():
    """报告双跑逐字节一致（收益矩阵可复现的最终锁）。"""
    from eval_agent.run_harness_eval import collect_rows, render_report
    r1 = render_report(collect_rows())
    r2 = render_report(collect_rows())
    assert r1 == r2
    assert "截断买到活着，买不到记得" in r1
    assert "纯净跑零税" in r1


def test_all_harness_flags_default_off():
    """纯净回归的机械锁：九个 Harness 开关出厂默认全关。"""
    s = Settings(zhipuai_api_key="test")
    for flag in ("enable_context_ledger", "enable_compaction",
                 "enable_memory_files", "enable_tool_shaping",
                 "enable_subagent_isolation", "enable_workspace",
                 "enable_steering", "enable_tool_gate",
                 "enable_layered_system"):
        assert getattr(s, flag) is False, f"{flag} 出厂必须为 False"
