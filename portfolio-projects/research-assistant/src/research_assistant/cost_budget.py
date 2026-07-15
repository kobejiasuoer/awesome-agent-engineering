"""轨迹级成本预算：一次运行的 token 钱包（AgentOps L02）。

为什么需要它（现状缺口）：
    ops-L12 的静态选型管「单价」（选 glm-4 还是 flash），但管不了「总量」——
    Agent 的成本是涌现的：步数 × 每步消耗都不确定，一次运行烧多少钱事前不知道。
    现状没有任何成本刹车，开了 enable_* 越多吞金兽越多，烧到多少都不会停。

本模块给一次运行一个钱包：
    - token 计量：从 LLM 响应的 usage_metadata 取真实 token（取不到按字符/4 估算）
    - 软预算（80%）：进入「节俭模式」——剩余子题降级用 flash（便宜模型）
    - 硬预算（100%）：触发 L01 的诚实收尾路径（带部分结果退出）
    - 分节点成本分摊：哪个节点是吞金兽（预期 researcher×N 并行是大头）

与 ops-L12 静态选型的分工：
    静态选型管单价（事前），轨迹预算管总量（运行时）——两层都要。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import settings
from .logging_config import get_logger

log = get_logger("cost_budget")


def extract_usage(llm_response: Any) -> dict:
    """从 LLM 响应提取 token 用量。

    优先级：
        1. response.usage_metadata（ChatZhipuAI / langchain 标准字段，实测可用）
           字段：input_tokens / output_tokens / total_tokens
        2. 估算：按字符数/4（中英混合粗略），诚实标注 estimated=True

    诚实标注：估算的数字结构与真实不同（绝对值差），但「有无预算刹车」的结构性
    结论一致——这就是为什么 mock 测试也能演示成本失控。
    """
    usage = getattr(llm_response, "usage_metadata", None)
    if isinstance(usage, dict) and usage:
        return {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("total_tokens",
                                       usage.get("input_tokens", 0) + usage.get("output_tokens", 0)),
            "estimated": False,
        }
    # 降级：字符估算
    content = getattr(llm_response, "content", str(llm_response))
    est = max(1, len(str(content)) // 4)
    return {"input_tokens": est, "output_tokens": 0, "total_tokens": est, "estimated": True}


@dataclass
class NodeCostTracker:
    """分节点成本累计器（本模块内累加，结束时 dump 进 state 做分摊报表）。"""
    by_node: dict[str, dict] = field(default_factory=dict)

    def add(self, node: str, usage: dict):
        """记一笔某节点的 token 消耗。"""
        cur = self.by_node.setdefault(node, {"total_tokens": 0, "calls": 0, "estimated": usage.get("estimated", False)})
        cur["total_tokens"] += usage.get("total_tokens", 0)
        cur["calls"] += 1
        cur["estimated"] = cur["estimated"] or usage.get("estimated", False)

    def total(self) -> int:
        return sum(v["total_tokens"] for v in self.by_node.values())

    def report(self) -> str:
        """分节点成本分摊报表（哪个节点是吞金兽）。"""
        if not self.by_node:
            return "（无 token 记录）"
        total = self.total()
        lines = [f"总 token：{total}"]
        for node, v in sorted(self.by_node.items(), key=lambda x: -x[1]["total_tokens"]):
            pct = v["total_tokens"] / total * 100 if total else 0
            tag = "（估算）" if v["estimated"] else ""
            lines.append(f"  {node:<16} {v['total_tokens']:>8} token  {pct:5.1f}%  "
                         f"({v['calls']} 次调用){tag}")
        return "\n".join(lines)


# 模块级单例：一次运行共享一个 tracker（service 层每次 invoke 重置）
_current_tracker: NodeCostTracker | None = None


def reset_tracker():
    """开始一次新运行时重置 tracker。"""
    global _current_tracker
    _current_tracker = NodeCostTracker()


def get_tracker() -> NodeCostTracker | None:
    return _current_tracker


def record_call(node: str, llm_response: Any):
    """节点调完 LLM 后记一笔（自动取 usage 或估算）。"""
    global _current_tracker
    if _current_tracker is None:
        _current_tracker = NodeCostTracker()
    usage = extract_usage(llm_response)
    _current_tracker.add(node, usage)
    return usage


def token_delta(node: str, llm_response: Any) -> dict:
    """节点的 token 增量 delta（合并进节点返回值）。

    返回 {"token_usage": this_call_tokens, "cost_mode": "..."}：
        token_usage 是「本次调用的增量」，被 add_int reducer 累加进 state 总量
        cost_mode 是基于「tracker 累计总量」判出的模式（normal/frugal/over_budget）

    关键：返回增量而非累计——因为 state.token_usage 用 add_int reducer，
    返回累计会重复计数。增量由 reducer 自动累加。
    """
    usage = record_call(node, llm_response)
    # cost_mode 基于 tracker 的累计总量判断（tracker 在模块内累加，state 只是镜像）
    total = _current_tracker.total() if _current_tracker else usage["total_tokens"]
    mode = _decide_cost_mode(total)
    return {"token_usage": usage["total_tokens"], "cost_mode": mode}


def _decide_cost_mode(total_tokens: int) -> str:
    """根据当前累计 token 决定成本模式。

    - "normal"：未到软预算
    - "frugal"：软预算（80%）触发 → 剩余子题降级 flash
    - "over_budget"：硬预算（100%）触发 → 该走诚实收尾

    开关关时永远 normal（现状行为）。
    """
    if not settings.enable_cost_budget:
        return "normal"
    budget = settings.max_budget_tokens
    if budget <= 0:
        return "normal"
    if total_tokens >= budget:
        return "over_budget"
    if total_tokens >= int(budget * 0.8):
        return "frugal"
    return "normal"


def should_truncate_for_cost(state: dict) -> tuple[bool, str]:
    """硬预算检查：token 超过 max_budget_tokens → 该诚实收尾。

    与 L01 的 should_truncate 互补：L01 管步数，本函数管成本。
    service/reviewer 可以把两者「或」起来判断。
    """
    if not settings.enable_cost_budget:
        return False, ""
    total = state.get("token_usage", 0) or 0
    budget = settings.max_budget_tokens
    if budget > 0 and total >= budget:
        return True, f"成本预算超限（{total}/{budget} token）"
    return False, ""


def pick_model_for_mode(normal_model: str, frugal_model: str, mode: str) -> str:
    """根据成本模式选模型名（节俭模式降级到 frugal_model）。

    供「运行中换模型」用：researcher 看到 cost_mode=frugal 时，
    后续子题改用 frugal_model（通常是 flash）。"""
    if mode == "frugal" or mode == "over_budget":
        return frugal_model
    return normal_model
