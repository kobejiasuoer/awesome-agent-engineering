"""L08 · 轨迹评估演示：评过程不只评答案。

演示流程：
    1. 用 L00 基线轨迹跑 TrajectoryEvaluator，出指标卡
    2. 构造一条"原地打转"假轨迹，验证循环检测
    3. 构造一条"机制全开"轨迹，看指标差异
    4. 对比：失忆基线 vs 有记忆/反思/代码的轨迹

跑法：
    cd frontier-lessons/08_trajectory_eval
    python code.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_RA_SRC = _HERE.parents[1] / "portfolio-projects" / "research-assistant" / "src"
sys.path.insert(0, str(_RA_SRC))

# L00 基线轨迹
L00_TRACE = _HERE.parents[1] / "frontier-lessons" / "00_method" / "baseline_trace.jsonl"


def main():
    from research_assistant.trajectory_eval import TrajectoryEvaluator

    print("=" * 60)
    print("L08 轨迹评估：评过程不只评答案")
    print("=" * 60)

    evaluator = TrajectoryEvaluator(llm=None)  # 规则降级模式

    # ── 1. 评估 L00 基线轨迹 ────────────────────────────────
    print("\n── 评估 L00 裸基线轨迹 ──────────────────────────")
    if L00_TRACE.exists():
        cards = evaluator.evaluate_file(str(L00_TRACE))
        for card in cards:
            print(evaluator.format_card(card))
            print()
        # 总结基线特征
        if cards:
            c = cards[0]
            print(f"  基线特征：{'失忆' if not c.has_memory_recall else '有记忆'}, "
                  f"{'无反思' if not c.has_reflection else '有反思'}, "
                  f"步数={c.total_steps}")
    else:
        print("  （L00 基线轨迹未找到，跳过）")

    # ── 2. 循环检测 ────────────────────────────────────────
    print("\n── 循环检测：构造原地打转轨迹 ────────────────────")
    loop_trace = [
        {"run": 1, "step": 1, "node": "researcher", "input": "q", "output": "同样的发现"},
        {"run": 1, "step": 2, "node": "researcher", "input": "q", "output": "同样的发现"},
        {"run": 1, "step": 3, "node": "researcher", "input": "q", "output": "同样的发现"},
        {"run": 1, "step": 4, "node": "researcher", "input": "q", "output": "同样的发现"},
    ]
    card = evaluator.evaluate(loop_trace, run_id="loop")
    print(f"  构造 4 步连续 researcher + 相同输出")
    print(f"  循环检测：{card.loops_detected} 次（节点: {card.loop_nodes}）")
    print(f"  {'✅ 抓到打转' if card.loops_detected > 0 else '❌ 漏检'}")

    # ── 3. 机制全开轨迹 ────────────────────────────────────
    print("\n── 机制全开轨迹（理想情况）──────────────────────")
    full_trace = [
        {"run": 1, "step": 1, "node": "researcher", "input": "主题",
         "output": "记忆命中：旧结论是X。新发现：Y（基于搜索）"},
        {"run": 1, "step": 2, "node": "researcher", "input": "子题",
         "output": "发现与旧结论冲突，触发re_research"},
        {"run": 1, "step": 3, "node": "researcher", "input": "补研",
         "output": "反思：上次搜索词太宽泛，这次加年份限定"},
        {"run": 1, "step": 4, "node": "writer", "input": "摘要",
         "output": "报告：修正说明。代码计算结果：42。附录：```python\nprint(42)\n```"},
    ]
    card = evaluator.evaluate(full_trace, run_id="full")
    print(evaluator.format_card(card))

    # ── 4. 对比总结 ────────────────────────────────────────
    print("\n── 对比总结 ─────────────────────────────────────")
    print("  L00 基线：  失忆/无反思/无冲突修正/无代码 → 从零重做")
    print("  机制全开：  有记忆/有反思/有冲突修正/有代码 → 增量进化")
    print("  → 每个机制的收益在指标卡上显形（布尔值 + 成功率）")

    print("\n" + "=" * 60)
    print("✅ 轨迹评估 = 评过程不只评答案，机制收益可量化")
    print("📊 指标卡：成功率/步数/工具/循环/归因 + 机制触发检测")
    print("=" * 60)


if __name__ == "__main__":
    main()
