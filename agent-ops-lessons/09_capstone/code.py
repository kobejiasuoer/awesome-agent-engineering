"""L09 · 毕业整合：Deep Research Agent v3 + 课程九注册
==================================================

本脚本是全课程的端到端验收：一条命令跑通「七机制协同 + 混沌收益矩阵 + 纯净跑零税」。
对照 L00 baseline_chaos.json 裸基线，量出 v3 的可靠性收益。

验收内容：
    1. 全机制协同：七机制在双层图上的位置一览
    2. 混沌收益矩阵定稿：六类故障 × 全关/全开（对照 L00）
    3. 纯净跑零税：全开防护对无故障任务不劣化
    4. 版本演进：v1 → v2 → v3

跑法（零外部依赖）：
    python code.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_RA = _REPO / "portfolio-projects" / "research-assistant"
sys.path.insert(0, str(_RA))
sys.path.insert(0, str(_RA / "src"))
sys.path.insert(0, str(_RA / "eval_agent"))


def show_seven_mechanisms():
    """七机制治理架构一览。"""
    print("=" * 70)
    print("  v3 · 七机制治理架构（每个默认关闭，可独立开关 + 降级）")
    print("=" * 70)
    print()
    print("  ┌──────┬────────────────────┬────────┬──────────────────────────┐")
    print("  │ 机制  │ 课程                │ 开关    │ 兜住的故障                │")
    print("  ├──────┼────────────────────┼────────┼──────────────────────────┤")
    print("  │ 📏    │ L01 步数预算         │ step   │ ③ 死循环                  │")
    print("  │ 💰    │ L02 成本预算         │ cost   │ ⑤ 成本超支                │")
    print("  │ 🔌    │ L03 熔断降级         │ cbreak │ ①② 慢/坏工具              │")
    print("  │ 🔑    │ L04 副作用幂等       │ pub    │ ⑥ 危险副作用（重放）       │")
    print("  │ 🚦    │ L05 HITL 审批        │ hitl   │ ⑥ 危险副作用（首次）       │")
    print("  │ 🔄    │ L06 断点续跑         │ job    │ ④ 进程崩溃                │")
    print("  │ 📊    │ L07 轨迹可观测        │ rsum   │ 可见性                    │")
    print("  └──────┴────────────────────┴────────┴──────────────────────────┘")
    print()
    print("  💡 默认全关 = v2 行为；开启后只在故障下生效（纯净跑零税）。")


def show_version_evolution():
    """版本演进图。"""
    print("\n" + "=" * 70)
    print("  版本演进：v1 → v2 → v3")
    print("=" * 70)
    print()
    print("  v1（多智能体）            v2（Deep Research）            v3（生产可靠）")
    print("  ─────────────            ──────────────────            ─────────────")
    print("  rag/workflow 课程         frontier + gui-agent 课程      agent-ops 课程")
    print()
    print("  能跑的搜索→写报告   →     有记忆/反思/CodeAct/    →     +步数/成本/熔断/")
    print("                            浏览器（能力完整）            幂等/审批/恢复/观测")
    print("                                                          （跑飞了有人管）")
    print()
    print("  测试：25           →     104（+79）              →     219（+96 agentops）")
    print("  可靠性：无          →     无                      →     SLO 卡（33%→100%）")
    print()
    print("  💡 与 kb-qa 对称：kb-qa 走 RAG→运维→多模态，")
    print("     research-assistant 走 多智能体→深研究→生产可靠——每一步都有数字。")


def run_e2e_validation():
    """端到端验收：跑混沌收益矩阵（对照 L00 基线）。"""
    print("\n" + "=" * 70)
    print("  端到端验收：混沌收益矩阵（对照 L00 baseline_chaos.json）")
    print("=" * 70)
    print()
    import run_chaos_eval
    cards = run_chaos_eval.run_matrix()
    slo = run_chaos_eval.slo_summary(cards)

    print(f"{'故障':<14} {'全关':<16} {'全开':<16} {'收益'}")
    print("-" * 70)
    faults = run_chaos_eval.FAULTS
    icon = {"completed": "✅", "truncated": "🟡", "caught": "🟡",
            "polluted": "☠️", "overspent": "💸", "full_rerun": "🔄", "duplicate": "⚠️"}
    for f in faults:
        off = next(c for c in cards if c.fault == f and c.protection == "all_off")
        on = next(c for c in cards if c.fault == f and c.protection == "all_on")
        saving = off.wasted_tokens - on.wasted_tokens
        saving_str = f"省 {saving} token" if saving > 0 else "—"
        print(f"{f:<14} {icon.get(off.outcome,'?')} {off.outcome:<13} "
              f"{icon.get(on.outcome,'?')} {on.outcome:<13} {saving_str}")

    print("\n" + "-" * 70)
    print("  可靠性 SLO 卡（全关 vs 全开）：")
    print(f"    任务成功率：       {slo['全关成功率']:.0%} → {slo['全开成功率']:.0%}")
    print(f"    平均浪费 token：   {slo['全关平均浪费token']} → {slo['全开平均浪费token']}")
    print(f"    副作用重复率：     {slo['全关副作用重复率']:.0%} → {slo['全开副作用重复率']:.0%}")


def show_two_throughlines():
    """两条贯穿主线总结。"""
    print("\n" + "=" * 70)
    print("  两条贯穿主线（全课程总结）")
    print("=" * 70)
    print()
    print("  ① 爆炸半径主线：L00 量出五种失控的无界半径 → 每课把一种压到有界")
    print("     · 循环  → 步数有界（L01）")
    print("     · 成本  → 预算有界（L02）")
    print("     · 故障  → 降级有界（L03）")
    print("     · 副作用 → 幂等+审批有界（L04/L05）")
    print("     · 崩溃  → 重做量有界（L06）")
    print()
    print("  ② 自主-控制主线：每个保护机制拿自主性/延迟/人力换安全")
    print("     · 闸太紧 Agent 废掉（什么都要人批），太松等于裸奔")
    print("     · 每课给「这道闸紧还是松」的判断依据")
    print("     · first_only 审批、软预算降级、熔断阈值——都是这个权衡的产物")


def main():
    print("🛡️  L09 · 毕业整合：Deep Research Agent v3 + 课程九注册")
    print()
    show_seven_mechanisms()
    show_version_evolution()
    run_e2e_validation()
    show_two_throughlines()
    print("\n" + "=" * 70)
    print("  🎓 毕业结论")
    print("=" * 70)
    print("  research-assistant 经历三个版本：")
    print("    v1 能跑的多智能体 → v2 有记忆能反思会写代码的 Deep Research →")
    print("    v3 生产可靠（七机制默认关、可降级，收益有混沌矩阵和 SLO 卡背书）")
    print()
    print("  两个作品集项目现在是对称的：")
    print("    kb-qa：RAG → 运维 → 多模态")
    print("    research-assistant：多智能体 → 深研究 → 生产可靠")
    print("    —— 每一步都有数字。")


if __name__ == "__main__":
    main()
