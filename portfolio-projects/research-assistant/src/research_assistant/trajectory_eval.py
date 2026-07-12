"""轨迹评估器：评过程，不只评答案（Frontier L08）。

与 ragas（单步问答评估）的本质区别：
    - ragas 评「答案对不对」（一次问答）
    - 轨迹评估评「过程好不好」（一整条 Agent 决策链）

评估主线在此闭环：
    L01-L07 每个机制的收益都要能在这些指标上显形——
    "加了记忆更好"从感觉变成表格里的数字。

指标卡（混合策略：规则 + LLM judge）：
    - 任务成功率（终态 judge）
    - 步数效率（同样成功谁步数少）
    - 工具调用正确率（该用没用/不该用乱用）
    - 循环检测（原地打转）
    - 失败归因（错在规划/检索/生成哪一环）

轨迹格式（对齐 L00 baseline_trace.jsonl）：
    每行一条 {run, step, node, input, output, ts}
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .logging_config import get_logger

log = get_logger("trajectory_eval")


@dataclass
class MetricCard:
    """轨迹评估指标卡。"""
    run_id: str = ""
    # ── 核心指标 ──
    success: bool = False           # 任务是否成功（终态 judge）
    total_steps: int = 0            # 总步数
    node_count: int = 0             # 节点数（去重）
    # ── 效率指标 ──
    steps_efficiency: float = 0.0   # 步数效率（成功/步数，越高越好）
    # ── 工具指标 ──
    tool_calls: int = 0             # 工具调用次数
    tool_success_rate: float = 0.0  # 工具调用成功率
    # ── 质量指标 ──
    has_memory_recall: bool = False    # 是否触发了记忆召回（L01）
    has_reflection: bool = False       # 是否有反思（L04）
    has_conflict_correction: bool = False  # 是否有冲突修正（L05）
    has_code_execution: bool = False   # 是否有代码执行（L07）
    # ── 问题检测 ──
    loops_detected: int = 0         # 循环次数（原地打转）
    loop_nodes: list[str] = field(default_factory=list)  # 哪些节点在打转
    # ── 归因 ──
    failure_attribution: str = ""   # 失败归因（规划/检索/生成/无）


class TrajectoryEvaluator:
    """轨迹评估器：输入轨迹 jsonl → 输出指标卡。

    混合策略（规则 + LLM judge）：
        - 步数/循环/工具调用：规则计算（确定性、零成本）
        - 成功率/归因：LLM judge（需 LLM）或规则降级
    """

    def __init__(self, llm=None):
        """Args: llm 用于 judge（可选，None 时降级为规则判断）。"""
        self.llm = llm

    def evaluate(self, trace: list[dict], run_id: str = "") -> MetricCard:
        """评估一条轨迹，返回指标卡。"""
        card = MetricCard(run_id=run_id or (trace[0].get("run", "") if trace else ""))

        if not trace:
            return card

        # ── 步数 ──
        card.total_steps = len(trace)
        nodes = [s.get("node", "") for s in trace]
        card.node_count = len(set(nodes))

        # ── 循环检测 ──
        card.loops_detected, card.loop_nodes = self._detect_loops(trace)

        # ── 工具调用 ──
        card.tool_calls, card.tool_success_rate = self._eval_tool_calls(trace)

        # ── 机制检测（L01-L07 各机制的触发情况）──
        card.has_memory_recall = self._check_memory_recall(trace)
        card.has_reflection = self._check_reflection(trace)
        card.has_conflict_correction = self._check_conflict_correction(trace)
        card.has_code_execution = self._check_code_execution(trace)

        # ── 任务成功率 ──
        card.success = self._judge_success(trace)

        # ── 步数效率 ──
        if card.success and card.total_steps > 0:
            card.steps_efficiency = 1.0 / card.total_steps  # 步越少效率越高

        # ── 失败归因 ──
        if not card.success:
            card.failure_attribution = self._attribute_failure(trace)

        log.info(f"评估完成 {run_id}: success={card.success}, steps={card.total_steps}, "
                 f"loops={card.loops_detected}, tools={card.tool_calls}")
        return card

    def _detect_loops(self, trace: list[dict]) -> tuple[int, list[str]]:
        """循环检测：同一节点连续出现 3+ 次且输出相似 → 打转。

        策略：滑动窗口看连续相同节点，输出文本相似度（字符重叠）。
        """
        loops = 0
        loop_nodes = []
        # 按节点分组连续段
        segments = []
        prev_node = None
        current = []
        for s in trace:
            node = s.get("node", "")
            if node != prev_node and current:
                segments.append((prev_node, current))
                current = []
            current.append(s)
            prev_node = node
        if current:
            segments.append((prev_node, current))

        # 连续 3+ 次同节点且输出高度相似 → 循环
        for node, steps in segments:
            if len(steps) >= 3:
                outputs = [s.get("output", "")[:50] for s in steps]
                # 简单判断：输出高度重复
                if len(set(outputs)) <= 2:  # 只有 1-2 种不同输出
                    loops += 1
                    loop_nodes.append(node)
        return loops, loop_nodes

    def _eval_tool_calls(self, trace: list[dict]) -> tuple[int, float]:
        """工具调用统计：次数 + 成功率。"""
        tool_nodes = {"researcher", "split"}  # 涉及工具调用的节点
        tool_steps = [s for s in trace if s.get("node") in tool_nodes]
        if not tool_steps:
            return 0, 0.0
        # 成功 = 输出不含失败信号
        success_count = sum(
            1 for s in tool_steps
            if "失败" not in s.get("output", "") and "超时" not in s.get("output", "")
            and "没有返回结果" not in s.get("output", "")
        )
        rate = success_count / len(tool_steps) if tool_steps else 0.0
        return len(tool_steps), rate

    def _check_memory_recall(self, trace: list[dict]) -> bool:
        """是否触发了记忆召回（L01）。"""
        for s in trace:
            text = (s.get("input", "") + s.get("output", "")).lower()
            if any(kw in text for kw in ["记忆命中", "recall", "旧记忆", "旧结论"]):
                return True
        return False

    def _check_reflection(self, trace: list[dict]) -> bool:
        """是否有反思（L04）。"""
        for s in trace:
            text = s.get("output", "").lower()
            if any(kw in text for kw in ["反思", "reflection", "教训", "下次"]):
                return True
        return False

    def _check_conflict_correction(self, trace: list[dict]) -> bool:
        """是否有冲突修正（L05）。"""
        for s in trace:
            text = s.get("output", "") + s.get("input", "")
            if any(kw in text for kw in ["冲突", "修正", "re_research", "矛盾"]):
                return True
        return False

    def _check_code_execution(self, trace: list[dict]) -> bool:
        """是否有代码执行（L07）。"""
        for s in trace:
            text = s.get("output", "")
            if any(kw in text for kw in ["代码计算", "附录", "```python", "可复算"]):
                return True
        return False

    def _judge_success(self, trace: list[dict]) -> bool:
        """判断任务是否成功。

        LLM judge（有 LLM 时）：看最终输出是否完成了任务。
        规则降级（无 LLM）：最后一步是 writer/reviewer 且输出非空 → 成功。
        """
        if not trace:
            return False

        if self.llm is not None:
            try:
                last_outputs = [s.get("output", "")[:200] for s in trace[-3:]]
                resp = self.llm.invoke(
                    f"判断以下 Agent 轨迹的最终输出是否完成了研究任务，"
                    f"只回复：成功 或 失败。\n{'; '.join(last_outputs)}"
                )
                return "成功" in resp.content
            except Exception:
                pass

        # 规则降级：最后几步有 writer/reviewer 且有内容
        last_nodes = [s.get("node", "") for s in trace[-3:]]
        last_outputs = [s.get("output", "") for s in trace[-3:]]
        has_writer = any(n in ("writer", "reviewer") for n in last_nodes)
        # reviewer 的 "pass" 也算成功；writer 的报告 > 20 字
        has_content = any(
            len(o) > 20 or "pass" in o.lower() or "通过" in o
            for o in last_outputs
        )
        return has_writer and has_content

    def _attribute_failure(self, trace: list[dict]) -> str:
        """失败归因：错在规划/检索/生成哪一环。

        规则降级版：
        - split 步异常 → 规划问题
        - researcher 步失败多 → 检索问题
        - writer 步异常 → 生成问题
        """
        node_failures = {}
        for s in trace:
            node = s.get("node", "?")
            output = s.get("output", "")
            is_fail = any(kw in output for kw in ["失败", "超时", "错误", "没有返回"])
            if is_fail:
                node_failures[node] = node_failures.get(node, 0) + 1

        if not node_failures:
            return "未知"

        # 归因映射
        if node_failures.get("split", 0) > 0:
            return "规划（子问题拆解失败）"
        if node_failures.get("researcher", 0) > 0:
            return "检索（搜索/知识获取失败）"
        if node_failures.get("writer", 0) > 0:
            return "生成（报告撰写失败）"
        return f"其他（{node_failures}）"

    def evaluate_file(self, trace_path: str) -> list[MetricCard]:
        """评估一个轨迹文件（jsonl），按 run 分组评估。"""
        path = Path(trace_path)
        if not path.exists():
            log.warning(f"轨迹文件不存在：{trace_path}")
            return []

        # 按 run 分组
        runs: dict[str, list[dict]] = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    run = str(rec.get("run", "default"))
                    runs.setdefault(run, []).append(rec)
                except json.JSONDecodeError:
                    continue

        cards = []
        for run_id, trace in sorted(runs.items()):
            card = self.evaluate(trace, run_id=run_id)
            cards.append(card)
        return cards

    def format_card(self, card: MetricCard) -> str:
        """格式化指标卡为可读文本。"""
        lines = [f"┌── 指标卡: run {card.run_id} ──" ]
        lines.append(f"│ 任务成功: {'✅' if card.success else '❌'}")
        lines.append(f"│ 总步数: {card.total_steps}（{card.node_count} 个节点）")
        lines.append(f"│ 步数效率: {card.steps_efficiency:.3f}（越高越好）")
        lines.append(f"│ 工具调用: {card.tool_calls} 次，成功率 {card.tool_success_rate:.0%}")
        lines.append(f"│ 记忆召回: {'✅' if card.has_memory_recall else '—'}")
        lines.append(f"│ 反思: {'✅' if card.has_reflection else '—'}")
        lines.append(f"│ 冲突修正: {'✅' if card.has_conflict_correction else '—'}")
        lines.append(f"│ 代码执行: {'✅' if card.has_code_execution else '—'}")
        lines.append(f"│ 循环检测: {card.loops_detected} 次{'（节点: '+','.join(card.loop_nodes)+'）' if card.loop_nodes else ''}")
        if card.failure_attribution:
            lines.append(f"│ 失败归因: {card.failure_attribution}")
        lines.append("└────────────────────────────")
        return "\n".join(lines)
