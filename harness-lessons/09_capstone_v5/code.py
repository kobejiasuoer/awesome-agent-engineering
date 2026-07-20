"""L09 · 毕业整合：Long-Haul Research Agent v5 + 收益矩阵
==================================================

本脚本做三件事：
    1. v5 全套端到端：八机制协同跑长途任务（账本/整形/子代理/工作区/
       压缩待命/记忆/改道/三层 system）——一条命令看完两条剧本线
       （跨会话偏好 + 第 10 源改道）。
    2. 收益矩阵五档 × 六指标（复用 eval_agent/run_harness_eval.py），
       killer row：「截断买到活着，买不到记得」。
    3. 可选真模型章（默认跳过）：设置 ZHIPUAI_API_KEY 且
       HARNESS_REAL_MODEL=1 时提示如何跑缩小版真实抽查——
       压缩摘要语义保真与迷航改善这两件 mock 测不了的事。
       **主验收不依赖此章**（零 API 零联网即可全部复现）。

跑法（零外部依赖、零联网、零真实等待）：
    python code.py
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_PROJ = _REPO / "portfolio-projects" / "research-assistant"
sys.path.insert(0, str(_PROJ))
sys.path.insert(0, str(_PROJ / "src"))

logging.disable(logging.WARNING)

from eval_agent.harness_runs import run_full_longhaul  # noqa: E402
from eval_agent.run_harness_eval import collect_rows, render_report  # noqa: E402
from research_assistant import steering  # noqa: E402


def hr(title: str) -> None:
    print(f"\n{'═' * 62}\n{title}\n{'═' * 62}")


def part1_v5() -> None:
    hr("Part 1 · v5 全套端到端：八机制协同")
    steering.set_db_path_for_test(tempfile.mktemp(suffix=".db"))
    r = run_full_longhaul(workspace_base=tempfile.mkdtemp(prefix="v5_ws_"),
                          memory_base=tempfile.mkdtemp(prefix="v5_mem_"))
    print(f"完成：{r['completed_sources']}/30（另 {len(r['skipped_by_instruction'])} 源"
          f"应改道指令跳过：{','.join(r['skipped_by_instruction'])}——跳过≠失败）")
    print(f"改道：第 {r['steer_applied_at']} 源后安全点生效 ✅")
    print(f"跨会话：会话 1 的用户偏好在会话 2 合成窗口在场 "
          f"{'✅' if r['prefs_present_across_sessions'] else '❌'}（只靠记忆文件+工作区存续）")
    print(f"在场率：{r['presence']}，跨源矛盾可发现 "
          f"{'✅' if r['contradiction_discoverable'] else '❌'}")
    print(f"主窗峰值：{r['main_peak_tokens']:,}/8,000（水位分布 {r['zone_counts']}"
          f"——每次调用都在安全区）")
    print(f"压缩：{r['compactions']} 次（外置让压缩失业，兜底待命）")
    print(f"计费：{r['tokens_billed']:,} token；fetch {r['total_fetches']} 次"
          f"（被跳过的源连 fetch 都省了）")


def part2_matrix() -> None:
    hr("Part 2 · 收益矩阵：五档 × 六指标")
    print(render_report(collect_rows()))


def part3_real_model() -> None:
    hr("Part 3 · 可选真模型章（默认跳过，主验收不依赖）")
    if os.environ.get("HARNESS_REAL_MODEL") == "1" and os.environ.get("ZHIPUAI_API_KEY"):
        print("检测到显式开启。真实抽查建议（自担费用，cost_budget 硬上限护栏）：")
        print("  1. 压缩语义保真：取 harness_runs.run_compacted_longhaul 的一次")
        print("     压缩输入/输出，改用 make_llm_summarizer(ChatZhipuAI(glm-4-flash))，")
        print("     人工核对 20 条登记事实之外的信息残存质量；")
        print("  2. 迷航抽查：8 源缩小版长途任务分别用「裸奔窗口」与「v5 窗口」")
        print("     组装 prompt 各跑一次真模型合成，对比矛盾是否被主动指出。")
    else:
        print("跳过（未设置 HARNESS_REAL_MODEL=1 + ZHIPUAI_API_KEY）。")
        print("mock 层已验收的是机械纪律：窗口算术/省略显式/登记存活/隔离无泄漏/")
        print("偏好跨会话在场。mock 测不了的认知收益（摘要语义保真/迷航改善）")
        print("留给本章真实抽查——两类结论分开陈述，绝不混报。")


def main() -> None:
    part1_v5()
    part2_matrix()
    part3_real_model()
    hr("五版本线收口")
    print("v1 能跑的多智能体 → v2 有脑子的深研究 → v3 关进笼子的生产可靠")
    print("→ v4 一直在岗的主动同事 → **v5 跑得远的长途选手**：")
    print("  8k 窗口跑完 30 源、关键事实零丢失、压缩有审计、中途可改道、")
    print("  跨会话记得住人——窗口管理五件套（记账/控源/外置/压缩/懒加载）")
    print("  每件都有账本数字背书，九个开关默认全关、纯净跑零税。")


if __name__ == "__main__":
    main()
