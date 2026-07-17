"""L02 · 信源与变化检测：世界变了什么
==================================================

本脚本演示两件事：
    Part 1（对照实验）：同一份 Day1→Day2 信源，「全文 diff」 vs 「item 级
        内容哈希」两种变化检测的分岔——全文 diff 报「变了一半」（误报），
        哈希法报「零变化」（正确）；Day3 哈希法精确指出「哪一条是新的」。
    Part 2（真实落地模块）：驱动 research_assistant.watcher 扫 5 个模拟日，
        逐日打印 ChangeSet——重点看 Day5：信源故障返回 ok=False，
        快照原封不动，恢复后不误报「全部消失又全部新增」。

两条纪律（本课灵魂）：
    ① 「没有变化」是一等公民结果（空变化集 → 这一轮不进研究图，不花钱）
    ② 「没能看到」≠「没有变化」（failed 绝不冒充空变化集）

跑法（零外部依赖、零联网、零等待）：
    python code.py
"""
from __future__ import annotations

import difflib
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

from eval_agent.ambient_timeline import (  # noqa: E402
    AmbientTimeline, SourceUnavailableError, DAY_EXPECTATIONS,
)
from research_assistant.watcher import content_hash  # noqa: E402


# ════════════════════════════════════════════════════════════
# Part 1 · 对照实验：全文 diff vs item 级内容哈希
# ════════════════════════════════════════════════════════════

def fulltext_view(items) -> str:
    """把当日信源拼成一篇全文（「全文 diff 流派」看到的世界）。"""
    return "\n".join(f"{it.title}：{it.content}" for it in items)


def demo_diff_vs_hash():
    print("─" * 72)
    print("Part 1 · 全文 diff vs item 级哈希（同一份 Day1→Day2→Day3 信源）")
    print("─" * 72)
    tl = AmbientTimeline()
    d1, d2, d3 = tl.fetch_items(1), tl.fetch_items(2), tl.fetch_items(3)

    # 流派 A：全文 diff（顺序敏感、空白敏感）
    sim12 = difflib.SequenceMatcher(None, fulltext_view(d1), fulltext_view(d2)).ratio()
    sim23 = difflib.SequenceMatcher(None, fulltext_view(d2), fulltext_view(d3)).ratio()

    # 流派 B：item 级内容哈希（seen-set 对比）
    def hash_diff(prev_items, cur_items):
        prev = {it.item_id: content_hash(it) for it in prev_items}
        new = [it.item_id for it in cur_items if it.item_id not in prev]
        changed = [it.item_id for it in cur_items
                   if it.item_id in prev and content_hash(it) != prev[it.item_id]]
        return new, changed

    new12, chg12 = hash_diff(d1, d2)
    new23, chg23 = hash_diff(d2, d3)

    print(f"\n  Day1→Day2（世界没变，仅顺序打乱+空白微调）：")
    print(f"    全文 diff  ：相似度 {sim12:.0%} → 会报「内容变了 {1-sim12:.0%}」（误报！）")
    print(f"    item 哈希  ：新增 {new12} 变更 {chg12} → 零变化（正确）")
    print(f"\n  Day2→Day3（真的多了一条 item-e）：")
    print(f"    全文 diff  ：相似度 {sim23:.0%} → 只知道「变了一点」，不知道是哪条")
    print(f"    item 哈希  ：新增 {new23} 变更 {chg23} → 精确指认（增量研究的输入就有了）")
    print()
    print("  🎯 粒度对了，「哪一条变了」是免费得到的——这正是 L03 增量研究的原料。")
    print("     哈希法的盲区：真正的措辞改写会被判「变更」，算不算实质变化留给 L04 语义判级。")
    print()


# ════════════════════════════════════════════════════════════
# Part 2 · 真实落地模块：5 日扫描 + Day5 故障纪律
# ════════════════════════════════════════════════════════════

def demo_real_watcher():
    import logging
    logging.getLogger().setLevel(logging.ERROR)

    from research_assistant import watcher
    from research_assistant.watcher import scan_source

    tmp = tempfile.mkdtemp(prefix="ambient_l02_")
    watcher.set_db_path_for_test(str(Path(tmp) / "snapshots.db"))

    print("─" * 72)
    print("Part 2 · 真实模块：逐日扫描 5 日时间线")
    print("─" * 72)
    tl = AmbientTimeline()

    for day in range(1, 6):
        cs = scan_source("timeline", lambda d=day: tl.fetch_items(d))
        print(f"  Day{day}: {cs.summary_line()}")
        print(f"        期望：{DAY_EXPECTATIONS[day]}")
        if day == 5:
            print(f"        快照条数：{watcher.snapshot_count('timeline')}（故障期原封不动）")

    # 恢复演示：Day5 故障后信源恢复（内容≈Day4），不误报「全部消失又新增」
    cs = scan_source("timeline", lambda: tl.fetch_items(4))
    print(f"  恢复:  {cs.summary_line()}  ← 与「最后一次看清的世界」对比，无误报")
    print()
    print("  🎯 对照 L00 基线：Day2 现状全量重研烧了 1053 token——现在机械层")
    print("     一次哈希对比就说「确认无变化」，研究图根本不用进。")
    print("     Day5 现状把失败字符串写进报告——现在 ok=False 显式呈现，")
    print("     「没能看到」和「没有变化」在数据结构上就是两种东西。")
    print()


def main():
    print("=" * 72)
    print("  L02 · 信源与变化检测：世界变了什么")
    print("=" * 72)
    print()
    print("L00 基线的第②环缺口：每次研究都当世界是全新的（Day2 纯浪费）。")
    print("本课给 Agent 装「醒来先看世界变没变」的机械层——五毛钱的哈希对比，")
    print("挡住最贵的那一步（全量研究）。")
    print()
    demo_diff_vs_hash()
    demo_real_watcher()
    print("=" * 72)
    print("  本课小结")
    print("=" * 72)
    print("  ① 变化检测的正确粒度是 item 级：哪条新增/变更/消失，免费得到")
    print("  ② 「没有变化」是一等公民：空变化集 → 不进研究图（Day2 浪费归零）")
    print("  ③ 「没能看到」≠「没有变化」：failed 显式呈现 + 快照不动（Day5 纪律）")
    print("  ④ 机械层不判断「重不重要」：那是 L04 语义判级的事（便宜的先跑，贵的兜底）")


if __name__ == "__main__":
    main()
