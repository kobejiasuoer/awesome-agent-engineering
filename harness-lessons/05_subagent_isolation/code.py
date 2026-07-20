"""L05 · 子代理：过程隔离，结论回传
==================================================

本脚本做四件事：
    1. 微观演示隔离契约：满窗口的原文进子代理，回传物里只有结论与数字。
    2. 长途任务主秀：压缩档（L02，主窗峰值 5,272）vs 隔离档（主窗 ~700）
       ——注意力杠杆的账本证明；隔离档甚至不再需要压缩。
    3. 失败隔离：子窗 1200 装不下三篇超长文档——结构化失败，主流程不陪葬，
       报告里「没干成」与「没内容」可区分。
    4. 机制组合（L04×L05）：子窗内先整形——完赛无失败，但深埋事实丢失
       有显式声明。两种诚实（拒绝干完 vs 干完但声明没读深处）各自成立。

诚实标注：
    - worker 的「提炼」为剧本代演（probe 命中即收录事实原句）——判断交给
      模型，本课交付的是隔离机制与失败契约，不是提炼质量。
    - v4 的 researcher 在窗口层面已隐式做对「回传结论不回传过程」（map-reduce
      的礼物）；本课把它变成显式契约并补齐：子窗物理预算、结构化 failed、
      账本份额。

跑法（零外部依赖、零联网、零真实等待）：
    python code.py
"""
from __future__ import annotations

import logging
import sys
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

from eval_agent.harness_runs import (  # noqa: E402
    run_compacted_longhaul, run_isolated_longhaul,
)
from research_assistant.context_ledger import FakeTokenizer  # noqa: E402
from research_assistant.subagent import SubagentRunner  # noqa: E402


def hr(title: str) -> None:
    print(f"\n{'═' * 62}\n{title}\n{'═' * 62}")


def part1_contract() -> None:
    hr("Part 1 · 隔离契约：回传结论，不回传过程")

    def worker(subject, payload, ledger):
        ledger.measure("sub-study", system="研读指令", tool_results=payload)
        return f"[{subject}] 结论：方案对比完成，推荐 B（依据 3 条，见引用）", (subject,)

    runner = SubagentRunner(worker, window_tokens=4000, tokenizer=FakeTokenizer())
    payload = "（这里是 2000 token 的原文材料与中间推演……）" * 200
    r = runner.run("S09", payload)
    print(f"子代理拿到的材料：{FakeTokenizer().count(payload):,} token")
    print(f"回传主窗口的全部内容（{FakeTokenizer().count(r.brief())} token）：")
    print(f"  「{r.brief()}」")
    print(f"随行诊断数字：子窗峰值 {r.window_peak:,}，子窗计费 {r.tokens_billed:,}")
    print("→ 过程的「账」回传，过程本身不回传——杠杆 ≈ "
          f"{r.window_peak // max(1, FakeTokenizer().count(r.brief()))} 倍。")


def part2_leverage() -> None:
    hr("Part 2 · 注意力杠杆：压缩档 vs 隔离档")
    comp = run_compacted_longhaul(register_pins=True)
    iso = run_isolated_longhaul(sub_window_tokens=4000)
    print("\n| 配置 | 完成 | 主窗峰值 | 子窗峰值 | 压缩次数 | 在场率 | 计费token |")
    print("|---|---|---|---|---|---|---|")
    print(f"| L02 压缩档 | 30/30 | {comp['peak_window_tokens']:,} | —（无子窗） "
          f"| {comp['compactions']} | {comp['presence']} | {comp['tokens_billed']:,} |")
    print(f"| **L05 隔离档** | 30/30 | **{iso['main_peak_tokens']:,}** "
          f"| {iso['sub_peak_tokens']:,} | {iso['compactions']} | {iso['presence']} "
          f"| {iso['tokens_billed']:,} |")
    print("\n解读：")
    print(f"  ①主窗峰值 {comp['peak_window_tokens']:,} → {iso['main_peak_tokens']:,}：")
    print("    压缩管住了「留下的」，管不住「路过的」——每篇全文仍要过主窗一次；")
    print("    隔离让全文根本不进主窗，主窗只涨结论。")
    print("  ②压缩次数 10 → 0：主窗低到不需要收房——隔离在源头消灭了压缩的必要性")
    print("    （能外置的别压缩，本课是这句话的第一次全量兑现）。")
    print(f"  ③计费 {comp['tokens_billed']:,} → {iso['tokens_billed']:,}：主窗每步")
    print("    重付的「历史」从全文变成了结论行——租金结构性下降。")
    print(f"  ④过程泄漏探针：{'❌ 泄漏' if iso['process_leaked'] else '✅ 无'}"
          "（原文片段未出现在合成窗口——契约有测试锁死）。")


def part3_failure_isolation() -> None:
    hr("Part 3 · 失败隔离：子代理死自己，主流程不陪葬")
    r = run_isolated_longhaul(sub_window_tokens=1200)
    print(f"子窗预算压到 1,200 token：三篇超长文档（2,800–3,400）装不下——")
    print(f"  结构化失败：{r['failed_sources']}（完成 {r['completed_sources']}/30）")
    print(f"  在场率 {r['presence']}（失败源的两条深埋事实 {r['missing_facts']} 同去）")
    print("  主窗口收到的失败注记形如：")
    print("  「⛔ [S17] 子代理失败：子窗口越限（预算 1200 token）——不等于该源无内容」")
    print("→ 三条纪律在场：①失败 ≠ 空结论（报告能区分「没内容」和「没干成」）；")
    print("  ②一个子代理溢出不拖垮其余 27 个；③尸检数字回传（峰值/计费）。")


def part4_composition() -> None:
    hr("Part 4 · 机制组合（L04×L05）：两种诚实")
    a = run_isolated_longhaul(sub_window_tokens=1200)
    b = run_isolated_longhaul(sub_window_tokens=1200, shape_in_sub=True)
    print("| 策略 | 完成 | 失败 | 在场率 | 说法 |")
    print("|---|---|---|---|---|")
    print(f"| 只隔离 | {a['completed_sources']}/30 | {len(a['failed_sources'])} "
          f"| {a['presence']} | 「三篇没干成」（显式失败） |")
    print(f"| 隔离+整形 | {b['completed_sources']}/30 | {len(b['failed_sources'])} "
          f"| {b['presence']} | 「都干完了，但三篇只读了截断版」（显式声明） |")
    print("\n两行在场率相同（18/20，丢的都是 F05/F19），但失败形态不同：")
    print("  拒绝干完（越限即死）vs 干完但声明没读深处（截断标记随结论回传）。")
    print("  没有对错，只有取舍——关键是两种都**显式**：静默才是唯一的错误答案。")


def main() -> None:
    part1_contract()
    part2_leverage()
    part3_failure_isolation()
    part4_composition()
    hr("两条主线的位置（L05）")
    print("窗口经济：子代理是注意力杠杆——过程在子窗烧、主窗只付结论的钱；")
    print("         份额思维（L01）落地成子窗物理预算，超了结构化失败。")
    print("外置化：  「过程」这块最大的临时内容被搬出主窗（虚拟内存图的进程隔离）；")
    print("         警示同样在场：需要全局上下文的判断不下放（Cognition 教训）。")


if __name__ == "__main__":
    main()
