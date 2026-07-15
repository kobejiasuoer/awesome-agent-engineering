"""L02 · 成本预算：轨迹级的钱包
==================================================

本脚本演示故障⑤（预算炸弹）的 before/after：
    - before（裸奔）：某子题返回超长文本，token 烧穿不停，无刹车。
    - after（开成本预算）：软预算（80%）降级模型 / 硬预算（100%）诚实收尾。
    还打印分节点成本分摊表（哪个节点是吞金兽）。

为什么用轨迹模型：
    真实图要 API key；这里演示「成本怎么失控 + 怎么刹车」的结构性结论。
    mock 下 token 为字符/4 估算（非 usage_metadata），但「有无预算刹车」的差异
    与真实 API 一致。

跑法（零外部依赖）：
    python code.py
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO / "portfolio-projects" / "research-assistant"))

from eval_agent.chaos import budget_bomb_search_factory  # noqa: E402


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class CostConfig:
    enable_cost_budget: bool = False
    max_budget_tokens: int = 5000   # 演示用小值
    soft_ratio: float = 0.8


@dataclass
class CostRun:
    label: str
    outcome: str            # "overspent" / "soft_downgrade" / "hard_truncate" / "normal"
    total_tokens: int
    final_model: str
    node_breakdown: dict    # 分节点成本
    notes: str


async def run_research_with_budget(cfg: CostConfig, bomb: bool) -> CostRun:
    """模拟一次研究，演示成本预算的软/硬两级刹车。"""
    node_tokens: dict[str, int] = {}
    total = 0
    final_model = "glm-4-flash"
    cost_mode = "normal"

    if bomb:
        search = budget_bomb_search_factory(None, bomb_chars=20000)  # 每子题 ~5000 token
    else:
        async def search(q, max_results=None):
            return f"[{q}] 正常搜索结果，约 200 字符。"

    # split
    split_out = "1. 子题一\n2. 子题二\n3. 子题三"
    total += estimate_tokens(split_out)
    node_tokens["split"] = estimate_tokens(split_out)

    # researcher×3（并行）
    subtopics = ["子题一", "子题二", "子题三"]
    findings = await asyncio.gather(*[search(s) for s in subtopics])
    for s, f in zip(subtopics, findings):
        # 软预算检查：进了 frugal 模式 → 后续子题降级
        if cfg.enable_cost_budget and total >= int(cfg.max_budget_tokens * cfg.soft_ratio):
            cost_mode = "frugal"
            final_model = "glm-4-flash"  # 已是 flash，演示降级语义
        t = estimate_tokens(f)
        total += t
        node_tokens["researcher"] = node_tokens.get("researcher", 0) + t
        # 硬预算检查：超 100% → 诚实收尾
        if cfg.enable_cost_budget and total >= cfg.max_budget_tokens:
            cost_mode = "over_budget"
            return CostRun(
                "预算炸弹" if bomb else "正常",
                "hard_truncate", total, final_model, dict(node_tokens),
                f"硬预算触发诚实收尾（{total}/{cfg.max_budget_tokens} token），带部分结果退出")

    # summarize
    summary = "研究摘要" * 20
    total += estimate_tokens(summary)
    node_tokens["summarize"] = estimate_tokens(summary)

    # writer
    report = "最终报告" * 30
    total += estimate_tokens(report)
    node_tokens["writer"] = estimate_tokens(report)

    if cost_mode == "frugal":
        outcome = "soft_downgrade"
        notes = f"软预算（80%）触发，后续降级 {final_model}，未超硬预算"
    elif bomb and not cfg.enable_cost_budget:
        outcome = "overspent"
        notes = f"无预算刹车，token 烧穿到 {total}（mock 估算，结构同真实）"
    else:
        outcome = "normal"
        notes = f"成本可控（{total}/{cfg.max_budget_tokens if cfg.enable_cost_budget else '∞'}）"

    return CostRun("预算炸弹" if bomb else "正常", outcome, total, final_model,
                   dict(node_tokens), notes)


def print_node_breakdown(run: CostRun):
    """打印分节点成本分摊表（吞金兽在前）。"""
    total = run.total_tokens
    print(f"    分节点成本分摊（总 {total} token）：")
    for node, t in sorted(run.node_breakdown.items(), key=lambda x: -x[1]):
        pct = t / total * 100 if total else 0
        print(f"      {node:<14} {t:>8} token  {pct:5.1f}%")


async def main():
    print("=" * 68)
    print("  L02 · 成本预算 —— 故障⑤预算炸弹的 before/after")
    print("=" * 68)
    print()
    print("演示：某子题返回超长文本（~5000 token），3 个子题 = ~15000 token")
    print("预算 max_budget_tokens=5000，软预算 80%=4000，硬预算 100%=5000")
    print()

    scenarios = [
        ("before：裸奔（预算炸弹）", CostConfig(enable_cost_budget=False), True),
        ("after：开预算（预算炸弹）", CostConfig(enable_cost_budget=True, max_budget_tokens=5000), True),
        ("对照：开预算（正常，无炸弹）", CostConfig(enable_cost_budget=True, max_budget_tokens=5000), False),
    ]

    for label, cfg, bomb in scenarios:
        run = await run_research_with_budget(cfg, bomb)
        icon = {"overspent": "💸", "soft_downgrade": "🟡", "hard_truncate": "✅", "normal": "✅"}[run.outcome]
        print(f"  {icon} {label}")
        print(f"     结局：{run.outcome}  总 token：{run.total_tokens}  最终模型：{run.final_model}")
        print(f"     {run.notes}")
        print_node_breakdown(run)
        print()

    print("=" * 68)
    print("  结论：两级刹车")
    print("=" * 68)
    print("  · 软预算（80%）：进节俭模式，剩余子题降级 flash（便宜模型）")
    print("  · 硬预算（100%）：诚实收尾（复用 L01 路径，带部分结果退出）")
    print("  · 分节点分摊表能指出吞金兽（预期 researcher×N 并行是大头）")
    print("  · 静态选型（ops-L12）管单价，轨迹预算（本课）管总量——两层都要")


if __name__ == "__main__":
    asyncio.run(main())
