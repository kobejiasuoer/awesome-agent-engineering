"""State 定义：图的"数据形状"。

两层图，两个 State：
    - ResearchState：并行研究子图（map-reduce 的工作面）
    - SystemState：父图（对话 + 研究 + 报告 + 审稿）

共享字段 findings（同名 + 同 reducer）是子图结果回流父图的桥梁。
这是 workflow-L05「共享 State 通信」模式。
"""
from __future__ import annotations

import operator
from typing import Annotated, Any

from typing_extensions import TypedDict

from langgraph.graph.message import add_messages


def add_int(left: int, right: int) -> int:
    """整数累加 reducer（AgentOps L01）。

    为什么不用普通 int：rewrite_count/re_research_count 用裸 int 靠「节点返回全量新值」，
    一旦未来有并行节点写同一个计数器就会互相覆盖。step_count 用 reducer 让每个节点
    只报「我走了几步」，reducer 自动累加，并发安全。
    """
    return (left or 0) + (right or 0)


# ════════════════════════════════════════════════════════════
# 子图 State（并行研究子系统）
# ════════════════════════════════════════════════════════════
class ResearchState(TypedDict):
    """并行研究子图的 State。

    findings 用 reducer（operator.add）：多个并行 researcher 的返回自动拼接，
    不互相覆盖。这是 L04 并行写回 + L05 共享 State 的核心机制——
    没有这个 reducer，并行结果会丢失。
    """
    topic: str
    subtopics: list[str]
    # ⭐ reducer 合并并行结果（L04 map-reduce 关键）
    findings: Annotated[list[str], operator.add]
    research_summary: str


# ════════════════════════════════════════════════════════════
# 父图 State（完整研究系统）
# ════════════════════════════════════════════════════════════
class SystemState(TypedDict):
    """整个研究系统的 State（父图）。

    综合：
        - messages：对话历史（add_messages reducer，L01 supervisor 模式）
        - findings：从子图回流的研究发现（与 ResearchState.findings 同名 + 同 reducer）
        - research_summary：子图产出的研究摘要
        - report：最终报告
        - review_decision：审稿结论（阶段 2）
        - rewrite_count：已重写次数（阶段 2，防死循环）
        - feedback：审稿反馈（传给 writer 改进）
        - conflicts：事实冲突列表（Frontier L05，双通道 reviewer 的事实通道）
        - re_research_count：补研次数（Frontier L05，防死循环）
        - re_research_queries：定向补研问题（Frontier L05）
    """
    messages: Annotated[list[Any], add_messages]
    findings: Annotated[list[str], operator.add]
    research_summary: str
    report: str
    review_decision: str
    rewrite_count: int
    feedback: str
    # Frontier L05：双通道 reviewer 的事实修正通道
    conflicts: Annotated[list[str], operator.add]
    re_research_count: int
    re_research_queries: list[str]
    # AgentOps L01：全局步数预算 + 诚实收尾标志
    # step_count 用 add_int reducer：每个节点返回的增量自动累加（不怕并行写覆盖）。
    # truncated=true 表示本次运行因步数预算/循环检测被截断（writer 据此标注部分结果）。
    step_count: Annotated[int, add_int]
    truncated: bool
    # 动作签名历史（L01 循环检测）：每经过一个节点记一条「节点名:参数哈希」
    action_history: Annotated[list[str], operator.add]
    # AgentOps L02：轨迹级成本预算
    # token_usage 累计本次运行的总 token（取 usage_metadata，取不到按字符/4 估算）
    token_usage: Annotated[int, add_int]
    # cost_mode：normal / frugal（软预算80%降级flash）/ over_budget（硬预算触发收尾）
    cost_mode: str
