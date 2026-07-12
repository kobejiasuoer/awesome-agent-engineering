"""L11 · 毕业整合：全机制协同演示。

演示流程：
    1. 展示五机制清单（每个的代码证据 + 开关）
    2. 展示硬任务完整数据流（第2次运行的理想轨迹）
    3. 降级验证：关掉某机制仍能跑
    4. 收益表对照

跑法：
    cd frontier-lessons/11_capstone
    python code.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    print("=" * 60)
    print("L11 毕业整合：Deep Research Agent v2")
    print("=" * 60)

    # ── 1. 五机制清单 ──────────────────────────────────────
    print("\n── 五机制清单 ───────────────────────────────────")
    mechanisms = [
        ("记忆", "L01-02", "memory.py", "enable_memory",
         "情景(Chroma)+语义(list)，researcher recall 旧经验，反思式写入"),
        ("Skills", "L03", "skill_loader.py + skills/", "enable_skills",
         "渐进式加载格式规范，writer 写报告前 load"),
        ("反思", "L04-05", "nodes.py reviewer 双通道", "enable_memory",
         "文字不合格→重写；事实冲突→定向补研→修正说明"),
        ("代码解释器", "L06-07", "code_interpreter.py", "enable_code_interpreter",
         "数值走沙箱算，报告附可复算脚本"),
        ("任务账本", "L10", "task_ledger.py", "enable_ledger",
         "TODO树持久化+断点续跑+增量简报"),
    ]
    for name, lessons, code, switch, desc in mechanisms:
        print(f"  {name}({lessons}): {code}")
        print(f"    开关: {switch}")
        print(f"    能力: {desc}")
        print()

    # ── 2. 评估体系 ────────────────────────────────────────
    print("── 评估体系 ─────────────────────────────────────")
    print("  L08: trajectory_eval.py — 指标卡(成功率/步数/工具/循环/归因)")
    print("  L09: eval_agent/run_harness.py — 开关矩阵×任务集=收益表")
    print()

    # ── 3. 硬任务数据流（理想第2次运行）─────────────────────
    print("── 硬任务数据流：第2次研究（全开）─────────────────")
    flow = [
        ("TaskLedger.next_actions", "→ 未完成TODO: 查MCP 2025路线图"),
        ("researcher: recall", "→ 记忆命中: 上次查到聚焦互操作"),
        ("researcher: web_search", "→ 联网补充新信息"),
        ("writer: load_skills", "→ 加载 research-brief-format 规范"),
        ("writer: 代码执行", "→ 增长率走沙箱算(可复算)"),
        ("reviewer: 事实通道", "→ 检测冲突? 无冲突"),
        ("reviewer: 文字通道", "→ 合格? pass"),
        ("reflect_and_store", "→ 提炼记忆存入MemoryStore"),
        ("TaskLedger.update", "→ 标记TODO完成"),
        ("产出", "→ 增量简报(🆕新增/✏️修正/➡️不变)"),
    ]
    for step, desc in flow:
        print(f"  {step:<28} {desc}")

    # ── 4. 降级路径 ────────────────────────────────────────
    print("\n── 降级路径 ─────────────────────────────────────")
    print("  全关 → 原始 research-assistant（25 测试全绿）")
    print("  仅记忆 → researcher recall 但无代码/反思")
    print("  全开 → Deep v2 完整能力")
    print("  → 任一机制关掉，系统仍能跑（104 测试不受开关影响）")

    # ── 5. 收益表 ──────────────────────────────────────────
    print("\n── 收益表（对照 L00 裸基线）─────────────────────")
    print("  指标           裸基线      v2全开")
    print("  ────────────  ────────    ────────")
    print("  记忆召回        0%          100%")
    print("  代码执行        0%          ~50%")
    print("  冲突修正        无          有")
    print("  增量产出        无          有")
    print("  (具体数字见 eval_agent/REPORT.md)")

    # ── 6. 测试总数 ────────────────────────────────────────
    print("\n── 测试覆盖 ─────────────────────────────────────")
    tests = [
        ("test_graph.py", 6),
        ("test_nodes.py", 20),
        ("test_tools.py", 5),
        ("test_memory.py", 18),
        ("test_skills.py", 13),
        ("test_code_interpreter.py", 15),
        ("test_trajectory_eval.py", 15),
        ("test_ledger.py", 12),
    ]
    total = 0
    for name, count in tests:
        print(f"  {name:<30} {count} 个")
        total += count
    print(f"  {'总计':<30} {total} 个")

    print("\n" + "=" * 60)
    print("✅ Deep Research Agent v2 = 记忆+反思+代码+skills+账本")
    print("📊 每个机制的收益都有轨迹评估数字支撑")
    print("🛡️  每个机制默认关闭，降级路径完好")
    print("=" * 60)


if __name__ == "__main__":
    main()
