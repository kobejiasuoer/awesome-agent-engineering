"""Eval Harness：机制开关矩阵 × 轨迹评估 = 机制收益表（Frontier L09）。

按 config 开关矩阵（全关 vs 全开 vs 单开某机制）跑 task_set，
用 TrajectoryEvaluator 评估轨迹，输出 REPORT.md。

Agent 评估的特殊坑（本课处理）：
    - 非确定性：同 prompt 两次跑不一样 → 重复跑取分布（本课简化为单次+标注）
    - 评估集设计：任务要能区分"有记忆/无记忆"——task_set 的变体集
    - 成本控制：评估也烧 token → 无 API 时 mock 路径出流程演示

无 API 时：用 mock 模拟研究流程，产出演示性指标卡（诚实标注）。
有 API 时：跑真实研究，产出实测数字。

跑法：
    cd portfolio-projects/research-assistant
    python eval_agent/run_harness.py           # mock 演示模式
    python eval_agent/run_harness.py --real    # 真实 API 模式（需 key）
"""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 把 src 加到 path
_HERE = Path(__file__).resolve().parent
_RA_ROOT = _HERE.parent
sys.path.insert(0, str(_RA_ROOT / "src"))

TASK_SET = _HERE / "task_set.json"
REPORT = _HERE / "REPORT.md"


# ════════════════════════════════════════════════════════════
# 开关矩阵
# ════════════════════════════════════════════════════════════
SWITCH_MATRIX = {
    "全关（裸基线）": {
        "enable_memory": False,
        "enable_skills": False,
        "enable_code_interpreter": False,
    },
    "全开（Deep v2）": {
        "enable_memory": True,
        "enable_skills": True,
        "enable_code_interpreter": True,
    },
    "仅记忆": {
        "enable_memory": True,
        "enable_skills": False,
        "enable_code_interpreter": False,
    },
    "仅代码解释器": {
        "enable_memory": False,
        "enable_skills": False,
        "enable_code_interpreter": True,
    },
}


# ════════════════════════════════════════════════════════════
# Mock 研究（无 API 时的流程演示）
# ════════════════════════════════════════════════════════════
def mock_research(topic: str, switches: dict) -> list[dict]:
    """模拟一次研究流程，根据开关产出不同轨迹。

    这是 mock 演示——不是真实研究，只演示"开关不同→轨迹不同→指标不同"。
    真实数字需 --real 模式跑。
    """
    trace = []
    step = 0

    # split（总是有）
    step += 1
    trace.append({"step": step, "node": "split", "input": topic, "output": f"拆解{topic}"})

    # researcher
    step += 1
    recall_sig = ""
    if switches.get("enable_memory"):
        recall_sig = "记忆命中：旧结论。"
    trace.append({
        "step": step, "node": "researcher", "input": "子题",
        "output": f"{recall_sig}基于搜索的发现",
    })

    # 代码执行（如果开了）
    if switches.get("enable_code_interpreter") and any(
        kw in topic for kw in ["对比", "统计", "数量", "增长率"]
    ):
        step += 1
        trace.append({
            "step": step, "node": "writer", "input": "摘要",
            "output": "代码计算结果：42。附录：```python\nprint(42)\n```",
        })

    # writer + reviewer
    step += 1
    trace.append({"step": step, "node": "writer", "input": "摘要", "output": f"关于{topic}的报告"})
    step += 1
    trace.append({"step": step, "node": "reviewer", "input": "报告", "output": "pass"})

    return trace


async def real_research(topic: str, switches: dict) -> list[dict]:
    """真实研究（需要 API key）。从轨迹文件读取。"""
    import research_assistant.config as config
    for k, v in switches.items():
        config.settings.__dict__[k] = v

    from research_assistant.service import invoke
    # 跑真实研究
    result = await invoke(topic, f"eval_{topic[:10]}")
    # 从 traces/ 读最新轨迹（service.py 落盘的）
    traces_dir = _RA_ROOT / "traces"
    trace_files = sorted(traces_dir.glob("run_*.jsonl"), reverse=True)
    if trace_files:
        with open(trace_files[0], encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    return []


# ════════════════════════════════════════════════════════════
# Harness 主流程
# ════════════════════════════════════════════════════════════

async def run_harness(real: bool = False):
    """跑开关矩阵 × task_set，产出 REPORT.md。"""
    from research_assistant.trajectory_eval import TrajectoryEvaluator

    evaluator = TrajectoryEvaluator(llm=None)
    tasks = json.loads(TASK_SET.read_text(encoding="utf-8"))

    results: dict[str, list] = {}  # switch_name → [cards]

    for switch_name, switches in SWITCH_MATRIX.items():
        print(f"\n{'─'*50}")
        print(f"配置：{switch_name} {switches}")
        print(f"{'─'*50}")

        cards = []
        for task in tasks:
            topic = task["topic"]
            print(f"  任务 {task['id']}: {topic}")

            if real:
                trace = await real_research(topic, switches)
            else:
                trace = mock_research(topic, switches)

            card = evaluator.evaluate(trace, run_id=task["id"])
            cards.append((task, card))

        results[switch_name] = cards

    # 生成报告
    report = generate_report(results, real)
    REPORT.write_text(report, encoding="utf-8")
    print(f"\n✅ 报告已生成：{REPORT}")
    print(f"\n{report[:500]}...")


def generate_report(results: dict, real: bool) -> str:
    """生成 REPORT.md：机制收益表。"""
    mode_label = "实测（真实 API）" if real else "mock 演示（非真实数字，演示流程）"

    lines = [
        "# 机制收益表（Frontier L09 Eval Harness）\n",
        f"> 评估模式：**{mode_label}**\n",
        "> 生成时间：" + _now() + "\n",
        "## 任务集\n",
        f"共 {len(list(results.values())[0])} 个任务变体（详见 task_set.json），",
        "覆盖记忆/代码/冲突/技能各机制的可区分场景。\n",
        "## 机制收益对比\n",
        "| 配置 | 平均步数 | 平均成功率 | 记忆召回率 | 代码执行率 | 反思率 |",
        "|------|---------|-----------|-----------|-----------|--------|",
    ]

    for switch_name, cards in results.items():
        n = len(cards)
        avg_steps = sum(c.total_steps for _, c in cards) / n if n else 0
        success_rate = sum(1 for _, c in cards if c.success) / n if n else 0
        mem_rate = sum(1 for _, c in cards if c.has_memory_recall) / n if n else 0
        code_rate = sum(1 for _, c in cards if c.has_code_execution) / n if n else 0
        reflect_rate = sum(1 for _, c in cards if c.has_reflection) / n if n else 0
        lines.append(
            f"| {switch_name} | {avg_steps:.1f} | {success_rate:.0%} | "
            f"{mem_rate:.0%} | {code_rate:.0%} | {reflect_rate:.0%} |"
        )

    lines.append("\n## 关键发现\n")

    # 对比全关 vs 全开
    all_off = results.get("全关（裸基线）", [])
    all_on = results.get("全开（Deep v2）", [])
    if all_off and all_on:
        off_mem = sum(1 for _, c in all_off if c.has_memory_recall) / len(all_off)
        on_mem = sum(1 for _, c in all_on if c.has_memory_recall) / len(all_on)
        off_code = sum(1 for _, c in all_off if c.has_code_execution) / len(all_off)
        on_code = sum(1 for _, c in all_on if c.has_code_execution) / len(all_on)

        lines.append(f"- **记忆**：全关 {off_mem:.0%} → 全开 {on_mem:.0%}（记忆召回从无到有）")
        lines.append(f"- **代码**：全关 {off_code:.0%} → 全开 {on_code:.0%}（代码执行从无到有）")
        lines.append(f"- 全关轨迹特征：失忆、无反思、无代码——每次从零重做")
        lines.append(f"- 全开轨迹特征：有记忆、有代码——增量进化、可复算")

    lines.append("\n## 数字来源标注\n")
    if real:
        lines.append("- 以上数字为**真实 API 运行结果**（ChatZhipuAI + 真实搜索）。")
        lines.append("- 复现命令：`python eval_agent/run_harness.py --real`")
    else:
        lines.append("- 以上数字为 **mock 演示**——非真实 API 结果，只演示「开关不同→指标不同」的流程。")
        lines.append("- 真实数字需 `python eval_agent/run_harness.py --real`（需 ZHIPUAI_API_KEY）。")
        lines.append("- mock 下成功率/机制触发率是预设的，不代表真实模型能力。")

    lines.append("\n## 单任务指标卡示例\n")
    if all_on:
        task, card = all_on[0]
        lines.append(f"### {task['id']}: {task['topic']}（全开配置）\n")
        lines.append(f"```")
        lines.append(evaluator_format(card) if False else _format_card_text(card))
        lines.append(f"```")

    return "\n".join(lines)


def _format_card_text(card) -> str:
    """格式化指标卡（不依赖 evaluator 实例）。"""
    return (
        f"成功: {'✅' if card.success else '❌'}\n"
        f"步数: {card.total_steps}\n"
        f"记忆召回: {'✅' if card.has_memory_recall else '—'}\n"
        f"反思: {'✅' if card.has_reflection else '—'}\n"
        f"冲突修正: {'✅' if card.has_conflict_correction else '—'}\n"
        f"代码执行: {'✅' if card.has_code_execution else '—'}\n"
        f"循环: {card.loops_detected}"
    )


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    real = "--real" in sys.argv
    import asyncio
    if real:
        asyncio.run(run_harness(real=True))
    else:
        asyncio.run(run_harness(real=False))
