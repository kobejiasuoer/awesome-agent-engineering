"""L07 · 代码解释器落地演示：研究助手的可复算报告。

演示流程：
    1. 模拟研究摘要（含数值对比信号）
    2. 路由判断：should_use_code → True
    3. LLM 生成分析代码（用 Mock 演示，真实用 ChatZhipuAI）
    4. 沙箱执行代码
    5. 报告附代码计算结果 + 可复算附录
    6. 对比：LLM 口算 vs 代码计算的可信度

跑法：
    cd frontier-lessons/07_code_interpreter
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
_RA_SRC = _HERE.parents[1] / "portfolio-projects" / "research-assistant" / "src"
sys.path.insert(0, str(_RA_SRC))


def main():
    from research_assistant.code_interpreter import (
        should_use_code, execute_code, run_code_for_research,
        format_code_appendix, reset_executed_codes,
    )

    print("=" * 60)
    print("L07 代码解释器：研究助手的可复算报告")
    print("=" * 60)

    # ── 1. 路由判断 ────────────────────────────────────────
    print("\n── 路由判断：什么任务走代码 ─────────────────────")
    summaries = [
        "MCP 生态在 2024 年快速增长，对比各年份数量分布",
        "概述 MCP 协议的设计理念和核心概念",
        "统计主流 MCP server 覆盖的场景占比",
        "介绍 MCP SDK 支持的编程语言",
    ]
    for s in summaries:
        use_code = should_use_code(s)
        print(f"  {'📊 走代码' if use_code else '✍️  LLM直出'}: {s[:40]}")

    # ── 2. 模拟研究场景 ────────────────────────────────────
    print("\n── 模拟研究：对比 MCP 各年份工具数量 ────────────")
    reset_executed_codes()

    # 模拟 LLM 生成的分析代码
    analysis_code = """
# MCP 生态各年份工具数量对比
data = {
    "2023": 8,
    "2024": 24,
    "2025": 35,
}
total = sum(data.values())
print("年份 | 工具数 | 占比 | 柱状图")
print("-----|--------|------|--------")
for year, count in sorted(data.items()):
    pct = count / total * 100
    bar = "█" * (count // 2)
    print(f"{year} | {count:>6} | {pct:>4.1f}% | {bar}")
print(f"总计 | {total:>6} | 100% |")
growth_2024 = (data["2024"] - data["2023"]) / data["2023"] * 100
print(f"\\n2024年增长率: {growth_2024:.1f}%")
""".strip()

    print(f"\n  📝 LLM 生成的分析代码：")
    for line in analysis_code.split("\n"):
        print(f"     {line}")

    # ── 3. 沙箱执行 ────────────────────────────────────────
    print(f"\n  🛡️ 沙箱执行中（import白名单+超时+截断）...")
    result = run_code_for_research(analysis_code)
    print(f"  {'✅ 执行成功' if result.success else '❌ 执行失败'}")
    if result.success:
        print(f"  📤 计算结果：")
        for line in result.output.split("\n"):
            print(f"     {line}")

    # ── 4. 报告附代码 ──────────────────────────────────────
    print(f"\n── 报告附可复算脚本 ─────────────────────────────")
    appendix = format_code_appendix()
    print(f"  （报告末尾附代码附录，读者可复算）")
    print(f"  附录预览（前 200 字符）：")
    print(f"  {appendix[:200]}...")

    # ── 5. 对比可信度 ──────────────────────────────────────
    print(f"\n── 对比：LLM 口算 vs 代码计算 ───────────────────")
    print(f"  [LLM 口算] '2024年增长约60%' → 🚫 哪来的？不可验证，可能幻觉")
    print(f"  [代码计算] '2024年增长率: 200.0%' → ✅ 附脚本，跑一遍就能验证")
    print(f"  → 代码解释器让数字从'口算'变'可复算'，可信度质变")

    # ── 6. 安全演示 ────────────────────────────────────────
    print(f"\n── 安全：越权 import 被拒 ────────────────────────")
    dangerous = "import os\nprint(os.listdir('.'))"
    result = execute_code(dangerous)
    print(f"  代码：{dangerous}")
    print(f"  结果：{'🚫 ' + result.error if not result.success else '✅ 执行'}")

    print("\n" + "=" * 60)
    print("✅ 代码解释器 = 数值结论可复算，报告可信度质变")
    print("🛡️ 沙箱安全：白名单(json/statistics/collections) + 超时 + 截断")
    print("📊 路由：对比/统计→走代码，观点/语言→LLM直出")
    print("=" * 60)


if __name__ == "__main__":
    main()
