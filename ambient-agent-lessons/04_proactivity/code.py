"""L04 · 打扰决策：值得说吗、现在说吗
==================================================

本脚本演示三件事：
    Part 1（判级）：Day2/Day3/Day4 三份简报的 major/minor/none 判级
        （mock LLM judge）+ 解析失败降级 minor（宁攒勿丢）。
    Part 2（配额）：突发日 4 个 major——前 2 个立即通知，后 2 个配额尽
        降 digest（quota_exhausted 可审计）；次日配额恢复。
    Part 3（三政策对比）：同一条 5 日时间线，all / threshold / digest_only
        三种政策的打扰次数与打扰精确率——量化「何时开口」的价值。

为什么判级要用 LLM 而配额用 sqlite：
    「这条变化重不重要」是内容理解问题（规则只能兜底）；
    「今天还剩几次打扰」是确定性记账问题（LLM 不该碰）。
    各用各的工具——判断交给模型，纪律交给代码。

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

import logging  # noqa: E402
logging.disable(logging.WARNING)

from research_assistant import proactivity  # noqa: E402
from research_assistant.clock import FakeClock, DAY_SECONDS  # noqa: E402
from research_assistant.proactivity import (  # noqa: E402
    Judgement, classify_change, decide,
)


class MockJudgeLLM:
    """mock 判级 LLM：按简报关键内容返回预设级别（真实系统用 glm-4-flash）。"""

    def invoke(self, prompt: str):
        class _R:
            def __init__(self, c):
                self.content = c
        if "✏️" in prompt or "撤回" in prompt:
            return _R("major\n结论反转（撤回 AGUI 支持），直接影响技术选型")
        if "🆕" in prompt or "补丁" in prompt:
            return _R("minor\n例行补丁更新，有信息量但不紧急")
        if "无变化" in prompt:
            return _R("none\n无实质内容")
        return _R("说不好，感觉还行吧")   # 演示解析失败路径


# 5 日简报（L03 的产出形态，浓缩版）
DAY_BRIEFS = {
    1: "# 增量简报\n## 首次研究\n- 🆕 LangGraph 1.2 稳定版\n- 🆕 MCP registry 上线\n- 🆕 框架X支持AGUI\n- 🆕 TrajBench v1",
    2: "✅ 确认无变化：今日无需研究",
    3: "# 增量简报\n- 🆕 新增: 框架Y 0.3.2 补丁（修复内存泄漏）",
    4: "# 增量简报\n- 🆕 新增: 重磅：框架X撤回AGUI支持转投A2A\n- ✏️ 修正: 框架X支持AGUI……此前结论已不成立",
    5: None,   # source_failed：不判级（走 L07 健康告警通道，不占内容判级）
}


def demo_classify():
    print("─" * 72)
    print("Part 1 · 判级：major / minor / none（mock LLM judge）")
    print("─" * 72)
    llm = MockJudgeLLM()
    for day in (2, 3, 4):
        j = classify_change(DAY_BRIEFS[day], llm=llm)
        print(f"  Day{day}: {j.level:<6} ← {j.reason}")
    # 解析失败演示
    j = classify_change("一份格式奇怪的简报", llm=llm)
    print(f"  解析失败: {j.level:<6} ← {j.reason}（degraded={j.degraded}）")
    print()
    print("  🎯 宁攒勿丢：判不出来就进 digest，绝不 stay_silent——")
    print("     宁可摘要多一条平庸条目，不可静默丢一条可能重要的变化。")
    print()


def demo_quota():
    tmp = tempfile.mkdtemp(prefix="ambient_l04_")
    proactivity.set_db_path_for_test(str(Path(tmp) / "quota.db"))

    print("─" * 72)
    print("Part 2 · 打扰配额：突发日 4 个 major（配额=2/天）")
    print("─" * 72)
    clock = FakeClock()
    for i in range(1, 5):
        out = decide(Judgement("major", f"重大变化 #{i}"), clock=clock,
                     policy="threshold", quota_limit=2)
        tag = "⚡ 立即通知" if out["decision"] == "notify_now" else \
              f"📥 降入摘要（配额尽 {out['quota_used']}/{out['quota_limit']}）"
        print(f"  major #{i}: {tag}")
    clock.advance(DAY_SECONDS)
    out = decide(Judgement("major", "次日的重大变化"), clock=clock,
                 policy="threshold", quota_limit=2)
    print(f"  次日 major: {'⚡ 立即通知（配额已恢复）' if out['decision'] == 'notify_now' else '?'}")
    print()
    print("  🎯 配额是「自主-控制」的阀门：即使判级全对，一天 8 次打扰也等于骚扰。")
    print("     配额尽的 major 不丢——降 digest 且记 quota_exhausted，日报可审计")
    print("     （「今天有 2 条 major 没能立即通知你」本身就是重要信息）。")
    print()


def demo_policies():
    print("─" * 72)
    print("Part 3 · 三政策 5 日对比：打扰次数与打扰精确率")
    print("─" * 72)
    llm = MockJudgeLLM()

    results = {}
    for policy in ("all", "threshold", "digest_only"):
        tmp = tempfile.mkdtemp(prefix=f"ambient_l04_{policy}_")
        proactivity.set_db_path_for_test(str(Path(tmp) / "quota.db"))
        clock = FakeClock()
        interrupts, digests, silents, major_interrupts = 0, 0, 0, 0
        for day in range(1, 6):
            brief = DAY_BRIEFS[day]
            if brief is None:
                continue    # Day5 信源故障：走健康告警通道，不进内容判级
            j = classify_change(brief, llm=llm)
            out = decide(j, clock=clock, policy=policy, quota_limit=2)
            if out["decision"] == "notify_now":
                interrupts += 1
                if j.level == "major":
                    major_interrupts += 1
            elif out["decision"] == "add_to_digest":
                digests += 1
            else:
                silents += 1
            clock.advance(DAY_SECONDS)
        precision = major_interrupts / interrupts if interrupts else None
        results[policy] = (interrupts, digests, silents, precision)

    print(f"\n  {'政策':<14} {'立即打扰':>8} {'进摘要':>7} {'沉默':>5} {'打扰精确率':>10}")
    print("  " + "-" * 52)
    for policy, (i, d, s, p) in results.items():
        p_str = f"{p:.0%}" if p is not None else "—（零打扰）"
        print(f"  {policy:<14} {i:>8} {d:>7} {s:>5} {p_str:>10}")
    print()
    print("  解读：")
    print("  · all：只要判级非 none 就推——3 次打扰只有 1 次值得（33%）。")
    print("    注意它仍好于 L00 裸基线（基线连判级都没有，Day2 空产出也推，5 推 1 值 20%）")
    print("  · threshold：1 次打扰正中 Day4 重大反转（100%）——minor 攒进摘要不丢")
    print("  · digest_only：零打扰，但 Day4 重大反转也要等日报——紧急性没了")
    print()
    print("  🎯 打扰精确率（值得的打扰/总打扰）是 L08 收益矩阵的核心指标之一；")
    print("     它和「增量召回率」（该说的说了没）构成打扰决策的查准/查全。")
    print()


def main():
    print("=" * 72)
    print("  L04 · 打扰决策：值得说吗、现在说吗")
    print("=" * 72)
    print()
    print("L00 基线的第④环缺口：有产出就全量推送（Day2 没新东西也打扰）。")
    print("本课给 Agent 装「开口的判断力」：判级（LLM）→ 政策+配额（代码）→")
    print("notify_now / add_to_digest / stay_silent 三选一。")
    print()
    demo_classify()
    demo_quota()
    demo_policies()
    print("=" * 72)
    print("  本课小结")
    print("=" * 72)
    print("  ① 判断交给模型，纪律交给代码：判级用 LLM，配额用 sqlite")
    print("  ② 宁攒勿丢：解析失败降级 minor 进摘要，绝不静默丢弃")
    print("  ③ 配额刹车：major 也不能无限打扰；降级可审计（quota_exhausted）")
    print("  ④ 三政策是紧松旋钮：all 疲劳 / threshold 平衡 / digest_only 失去紧急性")
    print("  ⑤ 信源故障不进内容判级：那是健康告警（L07），通道语义不同")


if __name__ == "__main__":
    main()
