"""L03 · 超时、熔断与诚实降级
==================================================

本脚本演示故障①②（慢/坏工具）的 before/after：
    - before（裸奔）：web_search 超时返回「搜索超时」字符串混进材料被当事实（污染）；
      持续故障下每个请求都等满超时 × 重试 = 雪崩。
    - after（开熔断 + 诚实降级）：结构化结果（ok/degraded/failed），degraded 不混进材料；
      连续失败 → 熔断快速失败不再等超时；报告里声明「N 个子题检索失败」。

演示三件事：
    1. 熔断器三态状态机（closed→open→half_open→closed）
    2. 结构化降级协议 vs 字符串降级（污染证据）
    3. 不同故障形态用什么策略（重试 vs 熔断）

跑法（零外部依赖）：
    python code.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO / "portfolio-projects" / "research-assistant" / "src"))

from research_assistant.breaker import (  # noqa: E402
    CircuitBreaker, CircuitState, call_with_breaker,
)


# ────────────────────────────────────────────────────────────
# Part 1 · 熔断器状态机演示
# ────────────────────────────────────────────────────────────

async def demo_state_machine():
    print("=" * 64)
    print("  Part 1 · 熔断器三态状态机（closed→open→half_open→closed）")
    print("=" * 64)
    # cooldown=0 让半开试探立即可触发（演示用）
    b = CircuitBreaker(name="web_search", fail_threshold=3, cooldown=0.0)

    print(f"\n初始状态：{b.state.value}（放行所有调用）")
    print()

    # 连续 3 次失败 → 打开
    async def always_fail():
        raise ConnectionError("连接重置")

    for i in range(3):
        r = await call_with_breaker(b, always_fail)
        print(f"  调用 {i+1}（失败）→ {r['status']}  状态：{b.state.value}  失败计数：{b._fail_count}")
    print(f"\n  💡 连续 3 次失败 → 熔断打开（不再等超时，快速失败）")

    # 熔断打开后调用 → 快速失败（degraded）
    r = await call_with_breaker(b, always_fail)
    print(f"\n  调用 4（熔断打开）→ {r['status']}  原因：{r['reason']}")
    print(f"  快速失败计数：{b.total_fast_failures}（没等超时）")

    # 冷却结束 → 半开 → 试探成功 → 关闭
    async def succeed():
        return "恢复的结果"

    r = await call_with_breaker(b, succeed)
    print(f"\n  调用 5（半开试探成功）→ {r['status']}  状态：{b.state.value}")
    print(f"  💡 半开试探成功 → 熔断关闭（恢复正常放行）")


# ────────────────────────────────────────────────────────────
# Part 2 · 诚实降级 vs 字符串降级（污染证据）
# ────────────────────────────────────────────────────────────

async def demo_honest_vs_string():
    print("\n" + "=" * 64)
    print("  Part 2 · 诚实降级 vs 字符串降级（污染证据）")
    print("=" * 64)

    # 现状：web_search 超时返回字符串
    print("\n【现状 · 字符串降级】（不诚实）")
    print("  web_search 超时返回：搜索 '子题一' 超时（15s）。可换关键词或稍后重试。")
    findings_string = [
        "【子题一】\n  发现：搜索 '子题一' 超时（15s）。可换关键词或稍后重试。\n  来源：真实联网搜索",
        "【子题二】\n  发现：正常发现内容\n  来源：真实联网搜索",
    ]
    material = "\n".join(findings_string)
    polluted = "超时" in material or "失败（" in material
    print(f"  findings 里混入了超时字符串：{'是 ⚠️（被当事实）' if polluted else '否'}")
    print(f"  → LLM 会把「搜索超时」当成子题一的发现写进报告 ☠️")

    # L03：结构化降级
    print("\n【L03 · 结构化降级】（诚实）")
    structured_results = [
        {"status": "degraded", "content": "", "reason": "搜索超时（15s）"},
        {"status": "ok", "content": "正常搜索结果", "reason": ""},
    ]
    findings_structured = []
    failed = []
    for i, sr in enumerate(structured_results, 1):
        if sr["status"] == "ok":
            findings_structured.append(f"【子题{i}】正常发现")
        else:
            failed.append(f"子题{i}（{sr['reason']}）")
    material2 = "\n".join(findings_structured)
    polluted2 = "超时" in material2 or "失败" in material2
    print(f"  findings 里混入了失败信息：{'是' if polluted2 else '否 ✅'}")
    print(f"  failed_subtopics（上报给 writer 声明）：{failed}")
    print(f"  → 报告会声明「{len(failed)} 个子题检索失败」，不把超时当事实 ✅")


# ────────────────────────────────────────────────────────────
# Part 3 · 故障形态 × 策略判断表
# ────────────────────────────────────────────────────────────

async def demo_strategy_matrix():
    print("\n" + "=" * 64)
    print("  Part 3 · 故障形态 × 策略判断表")
    print("=" * 64)
    print()
    print("  什么故障用什么策略（核心区分）：")
    print()
    print("  ┌─────────────────┬──────────────┬───────────────────────────────┐")
    print("  │ 故障形态         │ 策略          │ 理由                          │")
    print("  ├─────────────────┼──────────────┼───────────────────────────────┤")
    print("  │ 偶发抖动（网络）  │ 重试+退避     │ 重试几次就好，不该熔断        │")
    print("  │ 限流（429）      │ 重试+退避     │ 退避等限流窗口过去            │")
    print("  │ 持续故障（挂了）  │ 熔断          │ 重试=雪崩放大器，要快速失败   │")
    print("  │ 慢工具（超时）   │ 超时+降级     │ 不等它，标注降级声明          │")
    print("  └─────────────────┴──────────────┴───────────────────────────────┘")
    print()
    print("  💡 雪崩放大器：无限重试遇到持续故障 = 每个请求等满超时×重试次数。")
    print("     熔断器就是阻断这个放大——连续失败N次快速失败，不再等超时。")


async def main():
    print("L03 · 超时、熔断与诚实降级 —— 故障①②慢/坏工具的 before/after")
    print()
    await demo_state_machine()
    await demo_honest_vs_string()
    await demo_strategy_matrix()
    print("\n" + "=" * 64)
    print("  结论")
    print("=" * 64)
    print("  · 诚实降级：工具返回结构化结果（ok/degraded/failed），degraded 不混进材料")
    print("  · 手写熔断器：治持续故障（连续N次失败→快速失败），重试治抖动")
    print("  · 降级链：browser 失败→退 web_search→再失败→跳过子题并声明（能力递减不中断）")


if __name__ == "__main__":
    asyncio.run(main())
