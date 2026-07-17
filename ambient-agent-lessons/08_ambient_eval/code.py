"""L08 · 常驻评估：收益矩阵
==================================================

本脚本是 eval_agent/run_ambient_eval.py 的课程入口：
    跑五档配置 × 5 日时间线 + 崩溃探针 → 打印六指标收益矩阵
    → 存档 eval_agent/AMBIENT_REPORT.md。

六指标的设计逻辑（为什么是这六个）：
    增量召回率 × 打扰精确率  —— 开口决策的查全/查准（漏了没？烦了没？）
    疲劳指数                —— 精确率的绝对值补充（100% 精确×一天 20 次也是骚扰）
    静默失败                —— L02 纪律的终检（「没看到」被报成「没变化」吗）
    5 日 token              —— 钱的账（对照 L00 基线的 5000）
    缺勤检出                —— L07 心跳的终检（daemon 死了有人知道吗）

跑法（零 API、零联网、零等待）：
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
_REPO = _HERE.parent.parent
_PROJ = _REPO / "portfolio-projects" / "research-assistant"
sys.path.insert(0, str(_PROJ / "src"))
sys.path.insert(0, str(_PROJ))

import logging  # noqa: E402
logging.disable(logging.WARNING)

from eval_agent.run_ambient_eval import render_report, run_matrix  # noqa: E402


async def main():
    print("=" * 72)
    print("  L08 · 常驻评估：逐机制开关 × 5 日时间线 = 收益矩阵")
    print("=" * 72)
    print()
    print("评估传统的第三次延续：frontier-L09 的 harness 量机制收益、")
    print("agent-ops-L08 的混沌矩阵量故障生存——本课量「常驻价值」：")
    print("该说的说了没（召回）、说的值不值（精确）、钱花对没（token）、")
    print("谎撒了没（静默失败）、死了有人知道没（缺勤检出）。")
    print()

    rows = await run_matrix()
    report = render_report(rows)
    print(report)

    out = _PROJ / "eval_agent" / "AMBIENT_REPORT.md"
    out.write_text(report, encoding="utf-8")
    print(f"📦 收益矩阵已存：{out}")
    print()
    print("=" * 72)
    print("  本课小结")
    print("=" * 72)
    print("  ① cron 档与 baseline 六指标全同——cron 只买到出勤，买不到判断")
    print("    （这就是 L00 流派对比里「cron+全量脚本」不够的数字证明）")
    print("  ② watcher 是性价比之王：token -79%、召回 0→3/3、静默失败修复")
    print("  ③ judge 管注意力：打扰 5→1 且正中重大日（精确率 100%）")
    print("  ④ full 补最后一块：缺勤可检出；退避的代价（E1 晚一天）诚实入报告")
    print("  ⑤ 确定性：同一时间线跑两遍逐格一致（FakeClock+mock 的承诺，可回归）")


if __name__ == "__main__":
    asyncio.run(main())
