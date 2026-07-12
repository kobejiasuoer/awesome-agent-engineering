"""L09 · Eval Harness 演示：机制开关矩阵 × 轨迹评估。

演示流程：
    1. 展示开关矩阵（4 种配置）
    2. 展示任务变体集（8 个任务）
    3. mock 模式跑 harness，出机制收益表
    4. 解读收益表：每个机制的边际收益

跑法：
    cd frontier-lessons/09_eval_harness
    python code.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_RA_ROOT = _HERE.parents[1] / "portfolio-projects" / "research-assistant"
sys.path.insert(0, str(_RA_ROOT / "src"))
sys.path.insert(0, str(_RA_ROOT / "eval_agent"))


def main():
    print("=" * 60)
    print("L09 Eval Harness：让每个机制的收益有数字")
    print("=" * 60)

    # ── 1. 开关矩阵 ────────────────────────────────────────
    print("\n── 开关矩阵 ─────────────────────────────────────")
    print("  配置           memory  skills  code")
    print("  ─────────────  ──────  ──────  ────")
    print("  全关（基线）     ❌      ❌      ❌")
    print("  全开（v2）       ✅      ✅      ✅")
    print("  仅记忆           ✅      ❌      ❌")
    print("  仅代码           ❌      ❌      ✅")

    # ── 2. 任务集 ──────────────────────────────────────────
    print("\n── 任务变体集（8 个）────────────────────────────")
    import json
    tasks = json.loads((_RA_ROOT / "eval_agent" / "task_set.json").read_text(encoding="utf-8"))
    for t in tasks:
        print(f"  {t['id']}: {t['topic']:<30} 测: {t['tests_mechanism']}")

    # ── 3. 跑 harness ──────────────────────────────────────
    print("\n── 跑 harness（mock 模式）──────────────────────")
    print("  （mock 不烧 API，演示流程；真实数字需 --real）\n")

    from run_harness import run_harness
    asyncio.run(run_harness(real=False))

    # ── 4. 解读收益表 ──────────────────────────────────────
    print("\n── 解读收益表 ───────────────────────────────────")
    print("  全关 → 仅记忆：记忆的边际收益（recall 从 0→100%）")
    print("  全关 → 仅代码：代码的边际收益（code execution 从 0→50%）")
    print("  仅记忆 → 全开：加上 skills+code 的边际收益")
    print("  → 每个机制的价值可隔离量化，不再是感觉")

    print("\n" + "=" * 60)
    print("✅ Eval Harness = 机制收益量化，回归式评估")
    print("📊 开关矩阵 × 任务集 × 轨迹评估 = 收益表")
    print("⚠️  mock 数字是演示，真实数字需 --real 模式")
    print("=" * 60)


if __name__ == "__main__":
    main()
