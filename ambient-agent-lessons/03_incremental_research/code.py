"""L03 · 增量研究回路：只研究变化，不重研全量
==================================================

本脚本演示两件事：
    Part 1（成本对比）：Day3 只多了一条小更新——全量重研 vs 增量研究的
        token 对比（简化轨迹模型，估算口径与 L00 基线一致，可直接对照）。
    Part 2（真实落地模块）：watcher 扫 5 日时间线 → run_incremental 三分支
        （没能看到 / 确认无变化 / 增量研究）→ TaskLedger 增量简报。
        重点看 Day4：item-c 反转被标 ✏️ 修正，而不是静默覆盖旧结论。

诚实标注：
    Part 2 的「研究」步骤用确定性 mock（离线硬约束：真实图要 API key）；
    变化检测、焦点构造、账本记账、增量简报全部走真实落地模块。
    结构性结论（增量省钱、矛盾显式标注）与真实 LLM 一致。

跑法（零外部依赖、零联网、零等待）：
    python code.py
"""
from __future__ import annotations

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
sys.path.insert(0, str(_PROJ / "src"))
sys.path.insert(0, str(_PROJ))

from eval_agent.ambient_timeline import AmbientTimeline, TOPIC  # noqa: E402


def estimate_tokens(text: str) -> int:
    """与 L00 基线同口径：token ≈ 字符数/4（估算，诚实标注）。"""
    return max(1, len(text) // 4)


# ════════════════════════════════════════════════════════════
# Part 1 · Day3 成本对比：全量重研 vs 增量研究（简化轨迹模型）
# ════════════════════════════════════════════════════════════

def mock_research_cost(subtopics: list[str], material_per_topic: str) -> int:
    """一次研究的 token 估算：每个子题 搜索材料+提炼，再汇总+写报告。"""
    tokens = 0
    findings = []
    for sub in subtopics:
        tokens += estimate_tokens(sub) + estimate_tokens(material_per_topic)
        finding = f"【{sub[:30]}】发现：{material_per_topic[:80]}"
        tokens += estimate_tokens(finding)
        findings.append(finding)
    material = "\n".join(findings)
    tokens += estimate_tokens(material) * 2   # summarize + writer 各读一遍
    return tokens


def demo_cost_compare():
    print("─" * 72)
    print("Part 1 · Day3 成本对比：只多了一条小更新（item-e 框架Y补丁）")
    print("─" * 72)
    tl = AmbientTimeline()
    day3_material = tl.as_search_text("q", 3)

    # before：全量重研（现状——3 个 LLM 拆的子题，每个都重扫全部材料）
    full_subs = [f"{TOPIC}·子题{i+1}" for i in range(3)]
    full_cost = mock_research_cost(full_subs, day3_material)
    full_cost += estimate_tokens(TOPIC) * 2   # split 的 LLM 拆题调用

    # after：增量研究（焦点=1 条变化，split 跳过 LLM，材料只有新条目）
    new_item_text = "[框架 Y 发布 0.3.2 补丁] 修复长会话内存泄漏与 Windows 路径兼容问题，无新特性。"
    inc_subs = [f"【新增】框架 Y 发布 0.3.2 补丁：{new_item_text[:60]}"]
    inc_cost = mock_research_cost(inc_subs, new_item_text)

    print(f"  before 全量重研：{full_subs and 3} 子题 × 全量材料 → {full_cost} token（估）")
    print(f"  after  增量研究：1 焦点子题 × 仅新条目   → {inc_cost} token（估）")
    print(f"  节省：{(1 - inc_cost / full_cost):.0%}（split 还省了一次 LLM 拆题调用）")
    print()
    print("  🎯 增量的本质：研究面由「主题」缩到「变化」。变化越小省得越多——")
    print("     而 L02 已证明大多数日子变化为零（那天连这 1 条焦点都不会有）。")
    print()


# ════════════════════════════════════════════════════════════
# Part 2 · 真实落地模块：5 日三分支 + ✏️ 修正简报
# ════════════════════════════════════════════════════════════

def mock_research_findings(focus: list[str]) -> list[str]:
    """确定性 mock「研究」：真实系统里这一步是 invoke 研究图。

    模拟 researcher 遵守 prior_instr 约定：变更条目的发现以「更正：」开头。
    """
    findings = []
    for f in focus:
        if f.startswith("【内容变更】"):
            findings.append(f"更正：{f[6:60]}……此前结论已不成立，需以最新公告为准")
        else:
            findings.append(f"{f[4:60]}……（已核实新条目内容与影响）")
    return findings


def demo_real_incremental():
    import asyncio
    import logging
    logging.disable(logging.WARNING)  # 演示输出干净些（INFO/WARNING 流水不看）

    from research_assistant import config, watcher
    from research_assistant import task_ledger as tl_mod
    from research_assistant.incremental import (
        build_incremental_focus, record_and_brief, run_incremental,
    )
    from research_assistant.watcher import scan_source

    tmp = tempfile.mkdtemp(prefix="ambient_l03_")
    watcher.set_db_path_for_test(str(Path(tmp) / "snapshots.db"))
    config.settings.__dict__["enable_ledger"] = True
    config.settings.__dict__["enable_incremental_run"] = True
    config.settings.__dict__["ledger_db_path"] = str(Path(tmp) / "ledger.db")
    tl_mod._ledger = None   # 重置单例，用演示库

    print("─" * 72)
    print("Part 2 · 真实模块：5 日三分支 + 账本闭环（研究步骤 mock，其余真实）")
    print("─" * 72)
    tl = AmbientTimeline()

    for day in range(1, 6):
        cs = scan_source("timeline", lambda d=day: tl.fetch_items(d))
        if not cs.ok or cs.is_no_change():
            # 三分支的前两支走真实 run_incremental（不进图，无需 mock）
            out = asyncio.run(run_incremental(TOPIC, cs))
            print(f"\n  Day{day} [{out['status']}]：{out['brief']}")
            continue
        # 第三支：真实系统走 run_incremental → invoke 研究图；
        # 离线演示把「研究」换成确定性 mock，路由/账本/简报保持真实
        focus = build_incremental_focus(cs)
        findings = mock_research_findings(focus)
        brief = record_and_brief(TOPIC, cs, findings)
        print(f"\n  Day{day} [researched]：焦点 {len(focus)} 条（split 直用，不重拆题）")
        for line in brief.splitlines():
            if line.strip():
                print(f"      {line}")

    print()
    print("  🎯 对照 L00 基线 Day4：现状矛盾被静默覆盖；现在旧结论仍在场（➡️），")
    print("     反转显式标注（✏️ 修正）——读者一眼看到「世界观变了哪一块」。")
    print()


def main():
    print("=" * 72)
    print("  L03 · 增量研究回路：只研究变化，不重研全量")
    print("=" * 72)
    print()
    print("L00 基线的第③环缺口：增量靠人肉 diff（新东西埋在全量报告里）。")
    print("本课把 watcher 的变化集接进研究图：变化条目 → 焦点子题 → 只研究这些；")
    print("旧结论注入 prompt「只补新的」；产出走 TaskLedger 增量简报（🆕/✏️/➡️）。")
    print()
    demo_cost_compare()
    demo_real_incremental()
    print("=" * 72)
    print("  本课小结")
    print("=" * 72)
    print("  ① 焦点即子题：变化集已指认「研究什么」，split 跳过 LLM 拆题")
    print("  ② 旧结论注入：ledger 已确认项进 prompt，「已知这些，只补新的」")
    print("  ③ 矛盾走 ✏️：变更条目要求与旧结论对照，「更正：」开头触发修正标注")
    print("  ④ 账本闭环：世界增量（watcher）→ 研究 → 工作增量（ledger）→ 下次的「已知」")
    print("  ⑤ 漂移风险诚实标注：增量久了会与全局脱节——定期全量校准（L07 练习）")


if __name__ == "__main__":
    main()
