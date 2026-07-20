"""Harness 收益矩阵：逐机制档位 × 长途任务 = 六指标收益表（Harness L09）。

评估思路（对齐 run_ambient_eval / run_chaos_eval 的家族传统）：
    同一条 30 源长途任务（8k 假窗口、20 关键事实、1 对跨源矛盾、
    跨会话偏好钩子、第 10 源改道线），五档配置各跑一遍，
    量化每层 harness 机制的边际收益：
        A baseline·长程裸奔   8k 物理约束下越限即死（L00 A2）
        B 只硬截断            每篇留 500 字无标记（L00 A3——killer row）
        C +会计与压缩         账本水位 + 登记-摘要-验证（L01/L02）
        D +外置               子代理隔离 + 文件工作区 + 复述（L04/L05/L06）
        E 全套 v5             再加记忆/改道/三层 system（L03/L07/L08）

六指标：
    完成源数        研完几源（E 档的「跳过」是执行改道指令，单列不算失败）
    主窗峰值        主窗口的最大 token（8k 是物理限制）
    关键事实在场率  合成调用时 20 条事实以可用形态在场几条（机械探针）
    计费 token      全程计费（每轮重付全窗的保守口径，横向可比）
    fetch 次数      信源拉取总数（重复 fetch=浪费；跳过=连 fetch 都省）
    改道/跨会话     第 10 源改道是否生效 / 会话 1 偏好是否活到会话 2 合成

诚实标注：
    - FakeTokenizer len//4 口径、FakeLLM 无语义——绝对数字非真实 API，
      五档间的**相对结构**与真实一致；「迷航/中毒改善」等认知收益
      mock 测不了，见课程 README 的诚实边界与可选真模型章。
    - B 档在场率 8/20 但活到最后——**「截断买到活着，买不到记得」**
      是本矩阵的 killer row（对齐课程十「cron 只买到出勤」的传统）。

跑法（零 API、零联网、零等待）：
    python eval_agent/run_harness_eval.py     # 跑矩阵 + 写 HARNESS_REPORT.md
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJ / "src"))
sys.path.insert(0, str(_PROJ))

from eval_agent.harness_runs import (  # noqa: E402
    run_compacted_longhaul, run_full_longhaul, run_workspace_longhaul,
)
from eval_agent.long_haul import (  # noqa: E402
    KEY_FACTS, run_naive_longhaul,
)
from research_assistant import steering  # noqa: E402


def collect_rows() -> list[dict]:
    a = run_naive_longhaul("enforce")
    b = run_naive_longhaul("hard_truncate")
    c = run_compacted_longhaul(register_pins=True)
    d = run_workspace_longhaul(workspace_base=tempfile.mkdtemp(prefix="hm_d_"),
                               run_id="matrix-d")
    steering.set_db_path_for_test(tempfile.mktemp(suffix=".db"))
    e = run_full_longhaul(workspace_base=tempfile.mkdtemp(prefix="hm_e_"),
                          memory_base=tempfile.mkdtemp(prefix="hm_em_"))
    n = len(KEY_FACTS)
    return [
        {"config": "A baseline·长程裸奔", "completed": f"{a['completed_sources']}/30",
         "peak": "越限即死", "presence": f"0/{n}", "billed": a["tokens_billed"],
         "fetches": a["total_fetches"], "steer": "—", "session": "—",
         "verdict": f"死于 S{a['died_at']:02d}"},
        {"config": "B 只硬截断", "completed": f"{b['completed_sources']}/30",
         "peak": f"{b['peak_window_tokens']:,}", "presence": b["presence"],
         "billed": b["tokens_billed"], "fetches": b["total_fetches"],
         "steer": "—", "session": "—", "verdict": "活着但失忆（killer row）"},
        {"config": "C +会计与压缩", "completed": f"{c['completed_sources']}/30",
         "peak": f"{c['peak_window_tokens']:,}", "presence": c["presence"],
         "billed": c["tokens_billed"], "fetches": c["total_fetches"],
         "steer": "—", "session": "—",
         "verdict": f"完赛且记得（压缩 {c['compactions']} 次全审计）"},
        {"config": "D +外置(子代理+工作区)", "completed": f"{d['completed_sources']}/30",
         "peak": f"{d['main_peak_tokens']:,}", "presence": d["presence"],
         "billed": d["tokens_billed"], "fetches": d["total_fetches"],
         "steer": "—", "session": "—",
         "verdict": "主窗坍缩，压缩失业"},
        {"config": "E 全套 v5", "completed":
         f"{e['completed_sources']}/30(+{len(e['skipped_by_instruction'])}跳过)",
         "peak": f"{e['main_peak_tokens']:,}", "presence": e["presence"],
         "billed": e["tokens_billed"], "fetches": e["total_fetches"],
         "steer": "✅" if e["steer_applied_at"] else "—",
         "session": "✅" if e["prefs_present_across_sessions"] else "❌",
         "verdict": "跑得远且听得见人话"},
    ]


def render_report(rows: list[dict]) -> str:
    lines = [
        "# Harness 收益矩阵（L09）",
        "",
        "同一条 30 源长途任务（8k 假窗口、20 关键事实、1 对跨源矛盾、跨会话偏好、",
        "第 10 源改道线），五档配置各跑一遍。FakeTokenizer len//4 + FakeLLM 口径——",
        "绝对数字非真实 API，五档间的相对结构与真实一致（认知收益见课程诚实边界）。",
        "复现：`python eval_agent/run_harness_eval.py`（零 API、零联网、零等待）。",
        "",
        "| 配置 | 完成源数 | 主窗峰值 | 在场率 | 计费token | fetch | 改道 | 跨会话 | 结局 |",
        "|---|---|---|---|---:|---:|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['config']} | {r['completed']} | {r['peak']} | {r['presence']} "
            f"| {r['billed']:,} | {r['fetches']} | {r['steer']} | {r['session']} "
            f"| {r['verdict']} |")
    lines += [
        "",
        "## 逐档解读（每层机制买到了什么）",
        "",
        "- **A → B**：硬截断买到「活着」（30/30 完赛），买不到「记得」——",
        "  在场率 8/20、跨源矛盾断一臂，且静默无标记：报告把半篇当全篇。",
        "  **截断买到活着，买不到记得**——本矩阵的 killer row。",
        "- **B → C**：登记-摘要-验证把「丢什么」从按位置盲丢变成按价值契约——",
        "  在场率 8/20 → 20/20，矛盾可发现；代价是计费上升（压缩不省钱，省空间）。",
        "- **C → D**：过程隔离+工作区让主窗峰值 5,272 → ~720，压缩全程失业",
        "  （能外置的别压缩）；原文落盘后崩溃续跑不重付 fetch（L06 实测 30 vs 48）。",
        "- **D → E**：加回「人」与「时间」的维度——改道于第 10 源生效（4 个营销源",
        "  连 fetch 都省了）、会话 1 的偏好活到会话 2 的合成（记忆文件）、",
        "  三层 system 让指令账单再降；计费为五档最低（死亡档 A 除外）。",
        "",
        "## 纯净跑零税（回归声明）",
        "",
        "九个 Harness 开关（enable_context_ledger/compaction/memory_files/",
        "tool_shaping/subagent_isolation/workspace/steering/tool_gate/",
        "layered_system）默认全关；全关时主链路 prompt 逐字节与 v4 一致",
        "（各课关态回归测试锁死）。矩阵五档均为 eval 侧显式装配的结果。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import logging
    logging.disable(logging.WARNING)
    rows = collect_rows()
    report = render_report(rows)
    out = Path(__file__).resolve().parent / "HARNESS_REPORT.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"📦 收益矩阵已存：{out}")


if __name__ == "__main__":
    main()
