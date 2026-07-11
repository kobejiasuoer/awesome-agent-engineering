"""L00 · 裸基线：跑硬任务两次，证明 research-assistant 现状完全失忆。

本脚本不调用真实 LLM、不联网——用 mock 的假搜索结果模拟 research-assistant
的「拆题 → 并行检索 → 汇总 → 写报告 → 审稿」流程，连跑 2 次同一主题，
把每次的轨迹（每步输入输出）存成 baseline_trace.jsonl 作全程对照。

为什么用 mock：
    - 真实 API 跑出的报告内容会变，但「第 2 次完全失忆」是架构问题（无记忆系统），
      不依赖具体内容。用 mock 既省钱又能稳定复现这个结构性缺陷。
    - 这正是任务书「诚实标注」的要求：本机跑出的演示数字附复现命令，结论不夸大。

跑法：
    cd frontier-lessons/00_method
    python code.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows 编码兜底（任务书硬约束）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT_DIR = Path(__file__).resolve().parent
TRACE_FILE = OUT_DIR / "baseline_trace.jsonl"

# 默认硬任务主题（任务书 1.6，可配置）
DEFAULT_TOPIC = "MCP 生态的演进"


# ──────────────────────────────────────────────────────────────
# Mock 组件：模拟 research-assistant 的各节点行为
# （不导入真实 research_assistant 包，避免依赖 API key / 网络，
#   专注演示「失忆」这个架构问题）
# ──────────────────────────────────────────────────────────────

def mock_split(topic: str) -> list[str]:
    """模拟 split 节点：把主题拆成子问题。固定输出保证可复现。"""
    return [
        f"{topic} 的核心协议设计是什么",
        f"{topic} 有哪些主流实现和工具",
        f"{topic} 最近的版本和路线图",
    ]


def mock_research(subtopic: str, run_idx: int) -> str:
    """模拟 researcher 节点：返回假搜索结果 + 假提炼。

    关键：两次 run 返回的内容几乎一样（因为搜索的是同一个主题、同样的子问题）。
    这正是「失忆」的体现——第 2 次不知道第 1 次查过，重复劳动。
    """
    # 用 run_idx 微调措辞，模拟「搜索结果有细微时序差异」，但核心信息重复
    suffix = "（本次有少量更新）" if run_idx == 2 else ""
    return (
        f"关于「{subtopic}」的搜索结果{suffix}："
        f"找到 3 条相关资料，核心发现是该领域持续演进，"
        f"协议设计强调工具标准化，生态在扩展中。来源：mock-search"
    )


def mock_summarize(findings: list[str]) -> str:
    """模拟 summarize 节点：把 findings 汇总成摘要。"""
    return f"综合 {len(findings)} 条研究发现：MCP 生态正在快速演进，协议趋于稳定，工具链在扩展。"


def mock_write_report(summary: str, feedback: str = "") -> str:
    """模拟 writer 节点：基于摘要写报告。"""
    report = f"【概述】{summary}\n【核心要点】\n1. 协议设计走向标准化\n2. 实现工具增多\n3. 路线图聚焦互操作"
    if feedback:
        report += f"\n（据审稿反馈改进：{feedback}）"
    return report


def mock_review(report: str) -> tuple[str, str]:
    """模拟 reviewer 节点：审稿。第一次说不合格，第二次强制通过（演示回路）。"""
    # 简化：第一次 rework，第二次 pass（模拟 max_rewrites 回路）
    return ("rework", "要点不够具体") if "改进" not in report else ("pass", "")


# ──────────────────────────────────────────────────────────────
# 跑一次完整研究，记录轨迹
# ──────────────────────────────────────────────────────────────

def run_once(topic: str, run_idx: int) -> list[dict]:
    """模拟 research-assistant 跑一次，返回轨迹（每步一条记录）。

    轨迹格式与 L08 的 TrajectoryEvaluator 对齐：
        {run, step, node, input, output, ts}
    """
    trace: list[dict] = []
    ts_base = datetime.now(timezone.utc).isoformat()

    def step(node: str, inp: str, out: str):
        trace.append({
            "run": run_idx,
            "step": len(trace) + 1,
            "node": node,
            "input": inp,
            "output": out,
            "ts": ts_base,
        })

    # 1. split
    subs = mock_split(topic)
    step("split", f"主题={topic}", f"子问题={subs}")

    # 2. researcher（并行模拟成顺序记录）
    findings = []
    for s in subs:
        f = mock_research(s, run_idx)
        findings.append(f)
        step("researcher", f"子问题={s}", f"发现={f}")

    # 3. summarize
    summary = mock_summarize(findings)
    step("summarize", f"findings={len(findings)}条", f"摘要={summary}")

    # 4. writer（第一次）+ reviewer 回路
    report = mock_write_report(summary)
    step("writer", "摘要", report)
    decision, feedback = mock_review(report)
    step("reviewer", report[:50], f"decision={decision}, feedback={feedback}")

    # 5. 如果 rework，重写一次（模拟回路）
    if decision == "rework":
        report2 = mock_write_report(summary, feedback)
        step("writer", f"feedback={feedback}", report2)
        decision2, _ = mock_review(report2)
        step("reviewer", report2[:50], f"decision={decision2}")

    return trace


# ──────────────────────────────────────────────────────────────
# 对比两次运行，证明失忆
# ──────────────────────────────────────────────────────────────

def compare_runs(trace1: list[dict], trace2: list[dict]) -> dict:
    """对比两次轨迹，量化「失忆程度」。

    判定「有没有记忆」的可靠信号：run2 的输入里是否出现「回忆/上次/旧记忆/recall」
    等记忆系统注入时才会有的标记。裸基线没有任何这类标记 → 必然 0 = 完全失忆。

    （不能用"输出文本相似"判定，因为同输入自然产生相似输出，那是重算不是记忆。）
    """
    run2_inputs = " ".join(s["input"] for s in trace2)
    # 记忆系统注入时会出现的标记词（L01 起会有 recall/旧记忆 等字样）
    memory_markers = ["recall", "旧记忆", "上次", "历史结论", "记忆命中", "第 1 次", "第1次"]
    referenced = sum(1 for m in memory_markers if m in run2_inputs)

    # 子问题重复度（两个 run 的 split 输出有多像）—— 重算的证据
    subs1 = next((s for s in trace1 if s["node"] == "split"), {})
    subs2 = next((s for s in trace2 if s["node"] == "split"), {})
    sub_overlap = "高度重复" if subs1.get("output") == subs2.get("output") else "有差异"

    return {
        "run1_steps": len(trace1),
        "run2_steps": len(trace2),
        "run2_referenced_run1_outputs": referenced,  # 期望 0 = 完全失忆
        "subtopic_overlap": sub_overlap,
        "verdict": "完全失忆：第 2 次零引用第 1 次的任何产出，从零重做" if referenced == 0 else "有部分记忆",
    }


# ──────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────

def main(topic: str = DEFAULT_TOPIC):
    print(f"{'='*60}")
    print(f"L00 裸基线：硬任务「{topic}」连跑 2 次")
    print(f"{'='*60}\n")

    all_traces: list[dict] = []

    for i in (1, 2):
        print(f"── 运行 #{i} ─────────────────────")
        trace = run_once(topic, i)
        for s in trace:
            print(f"  [{s['step']:>2}] {s['node']:<12} → {s['output'][:60]}")
        all_traces.extend(trace)
        print()

    # 对比
    trace1 = [s for s in all_traces if s["run"] == 1]
    trace2 = [s for s in all_traces if s["run"] == 2]
    cmp = compare_runs(trace1, trace2)

    print(f"── 失忆诊断 ─────────────────────")
    print(f"  run1 步数: {cmp['run1_steps']}")
    print(f"  run2 步数: {cmp['run2_steps']}")
    print(f"  run2 引用 run1 产出次数: {cmp['run2_referenced_run1_outputs']}")
    print(f"  子问题重复度: {cmp['subtopic_overlap']}")
    print(f"  结论: {cmp['verdict']}")
    print()

    # 存轨迹（全程对照，L08 评估时复用）
    with open(TRACE_FILE, "w", encoding="utf-8") as f:
        for rec in all_traces:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"✅ 轨迹已存: {TRACE_FILE}")
    print(f"   共 {len(all_traces)} 条记录（run1={len(trace1)} + run2={len(trace2)}）")
    print(f"\n💡 这个基线是全程对照——L01 加记忆后看 recall 命中，L08 评估时算基线指标。")


if __name__ == "__main__":
    main()
