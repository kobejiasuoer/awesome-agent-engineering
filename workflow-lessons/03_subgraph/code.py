"""
Lesson 03 — 子图 Subgraph：模块化与复用
==========================================
本课把 L02 的 swarm 客服系统【封装成一个子图】，嵌入更大的父图。

核心问题：
    L01/L02 的系统都在一张图里。但真实项目里 Agent 越加越多，
    单图会变成蜘蛛网——读不懂、改不动、没法复用。
    子图 = 把一个编译好的图当作节点嵌入父图，实现【封装 + 复用】。

三个部分：
  ① 把 L02 的客服 swarm 封装成子图，嵌入父图（前置分类 + 客服子图 + 后置汇总）
  ② 条件路由：父图根据分类决定走不走客服子图
  ③ State 对齐：父图 State ⊇ 子图 State，子图只读写共享字段

映射：agent-lessons/08_multi_agent（三个独立函数，没有封装概念）
兑现：framework-lessons/07_tools_and_agents 决策表预告的"子图"（L09 没兑现，本课兑现）

运行：python workflow-lessons/03_subgraph/code.py
"""
# 消除 langchain-community 的 sunset 警告 + jwt 密钥长度警告（都不影响使用）
import warnings
warnings.filterwarnings("ignore", message=".*langchain-community.*is being sunset.*")
try:
    from jwt.warnings import InsecureKeyLengthWarning
    warnings.filterwarnings("ignore", category=InsecureKeyLengthWarning)
except ImportError:
    pass

import os
from typing import Annotated
from typing_extensions import TypedDict

from dotenv import load_dotenv
from langchain_community.chat_models import ChatZhipuAI
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.graph.message import add_messages
from langgraph_swarm import create_swarm, create_handoff_tool

CHAT_MODEL = "glm-4"  # 想免费可换 "glm-4-flash"


# ════════════════════════════════════════════════════════════
# 第 1 步：构建【子图】—— L02 的客服 swarm 系统
# ════════════════════════════════════════════════════════════
def build_customer_service_subgraph(llm):
    """构建客服 swarm 子图（复用 L02 的设计）。

    这个子图内部是一个完整的 swarm（triage → refund → after_sales），
    但从父图看，它只是【一个节点】——这就是"封装"。

    对比 Agent L08 手写：
        手写版三个函数 planner()/executor()/reviewer() 是平铺的，
        没有封装概念，要复用得复制粘贴。
        子图可以编译一次，到处嵌入（复用）。
    """
    triage = create_agent(
        llm,
        tools=[
            create_handoff_tool(agent_name="refund"),
            create_handoff_tool(agent_name="after_sales"),
        ],
        name="triage",
        system_prompt=(
            "你是客服分诊员，只分类转交：退款转 refund，售后转 after_sales。不要自己处理。"
        ),
    )
    refund = create_agent(
        llm, tools=[create_handoff_tool(agent_name="after_sales")],
        name="refund", system_prompt="你是退款专员，处理退款后转 after_sales。",
    )
    after_sales = create_agent(
        llm, tools=[create_handoff_tool(agent_name="triage")],
        name="after_sales", system_prompt="你是售后专员，处理完回复用户。",
    )
    # 子图用 MessagesState（只有 messages 字段）
    return create_swarm(
        agents=[triage, refund, after_sales],
        default_active_agent="triage",
    ).compile()


# ════════════════════════════════════════════════════════════
# 第 2 步：定义【父图 State】—— 比子图多业务字段
# ════════════════════════════════════════════════════════════
class ParentState(TypedDict):
    """父图 State：messages（子图也用）+ category（父图独有）。

    State 对齐规则：
        子图的 State（MessagesState，只有 messages）是父图 State 的【子集】。
        子图只读写它认识的字段（messages），父图独有的字段（category）子图不碰。
        这就像函数参数：子图"接收" messages，"不关心" category。
    """
    messages: Annotated[list, add_messages]
    category: str  # 父图独有：任务分类（客服 / 咨询 / 投诉 等）


# ════════════════════════════════════════════════════════════
# 第 3 步：构建【父图】—— 前置分类 + 客服子图 + 后置汇总
# ════════════════════════════════════════════════════════════
def build_parent_graph(llm, service_subgraph):
    """构建父图：classify →(条件)→ customer_service(子图) / other → END。

    父图的三个节点：
        - classify：前置分类（写到父图独有字段 category）
        - customer_service：【子图节点】—— 把客服 swarm 整个塞进来
        - other_handler：非客服问题的兜底处理
    """
    # ── 前置节点：分类（用 LLM 或规则判断）──
    def classify(state: ParentState):
        last_msg = state["messages"][-1].content
        # 简单规则分类（真实场景可用 LLM 分类）
        if any(kw in last_msg for kw in ["退款", "售后", "退货", "换货"]):
            cat = "客服"
        elif any(kw in last_msg for kw in ["投诉", "举报", "不满"]):
            cat = "投诉"
        else:
            cat = "咨询"
        print(f"  [父图-classify] 分类结果：{cat}")
        return {"category": cat}  # 只写父图独有字段，不碰 messages

    # ── 条件路由：根据分类决定走哪条路 ──
    def route(state: ParentState) -> str:
        if state.get("category") == "客服":
            return "customer_service"  # 走客服子图
        return "other_handler"         # 其他走兜底

    # ── 兜底节点：非客服问题 ──
    def other_handler(state: ParentState):
        cat = state.get("category", "未知")
        return {"messages": [AIMessage(content=f"这是「{cat}」问题，已记录，稍后人工跟进。")]}

    # ── 组装父图 ──
    builder = StateGraph(ParentState)
    builder.add_node("classify", classify)
    # ⭐ 核心：把子图（编译好的 swarm）当作一个节点
    # 从父图视角看，customer_service 就是一个普通节点——内部复杂性被封装
    builder.add_node("customer_service", service_subgraph)
    builder.add_node("other_handler", other_handler)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", route)  # 条件路由
    builder.add_edge("customer_service", END)         # 子图完直接结束
    builder.add_edge("other_handler", END)

    return builder.compile()


# ════════════════════════════════════════════════════════════
# 实验 1：客服问题 → 走子图（看子图封装后的完整流程）
# ════════════════════════════════════════════════════════════
def part_1_customer_service_via_subgraph(graph):
    """演示客服问题被路由到子图。

    观察流程：classify(分类) → customer_service(子图内部 triage→refund→after_sales) → END
    从父图看只有 3 步，但子图内部是一个完整的 swarm。
    """
    print("\n" + "─" * 60)
    print("实验 1：客服问题 → 路由到客服子图")
    print("─" * 60)
    task = "我要退款订单 12345，退款后确认到账。"
    print(f"📋 用户请求：{task}")
    print("\n流程：classify(分类) → customer_service(子图) → END\n")

    result = graph.invoke({"messages": [{"role": "user", "content": task}], "category": ""})

    print(f"\n【分类结果】{result.get('category')}")
    print(f"【子图处理的最终回复】\n{result['messages'][-1].content}")
    print("\n💡 注意：父图只看到 customer_service 这一个节点，")
    print("   但它内部跑了一个完整的 swarm（triage→refund→after_sales）。")
    print("   这就是子图的【封装】价值——复杂性藏起来，父图保持简洁。")


# ════════════════════════════════════════════════════════════
# 实验 2：非客服问题 → 走兜底（条件路由的价值）
# ════════════════════════════════════════════════════════════
def part_2_other_question_bypass(graph):
    """演示非客服问题跳过子图。

    观察流程：classify(分类为咨询) → other_handler → END
    客服子图根本不被执行——条件路由让它被跳过。
    这就是"按需调用子图"——不是所有请求都要启动整套客服系统。
    """
    print("\n\n" + "─" * 60)
    print("实验 2：非客服问题 → 跳过客服子图")
    print("─" * 60)
    task = "你们公司地址在哪里？"
    print(f"📋 用户请求：{task}")
    print("\n流程：classify(分类) → other_handler(兜底) → END（客服子图被跳过）\n")

    result = graph.invoke({"messages": [{"role": "user", "content": task}], "category": ""})

    print(f"\n【分类结果】{result.get('category')}")
    print(f"【兜底回复】{result['messages'][-1].content}")
    print("\n💡 对比：客服问题才启动 swarm 子图（贵），")
    print("   咨询问题走轻量兜底（省）。这就是条件路由 + 子图的组合价值。")


# ════════════════════════════════════════════════════════════
# 实验 3：父图拓扑可视化（看子图如何"黑盒"显示）
# ════════════════════════════════════════════════════════════
def part_3_topology(graph):
    """打印父图 Mermaid——观察子图显示为单个节点。

    重点：customer_service 在图里是【一个节点】，不是三个。
    子图内部的 triage/refund/after_sales 不展开——这就是"黑盒封装"。
    """
    print("\n\n" + "─" * 60)
    print("实验 3：父图拓扑（子图显示为单个「黑盒」节点）")
    print("─" * 60)
    print(graph.get_graph().draw_mermaid())
    print("━" * 60)
    print("拓扑解读：")
    print("  - 父图只有 3 个业务节点：classify / customer_service / other_handler")
    print("  - customer_service 是子图，但 Mermaid 只画成一个节点（黑盒）")
    print("  - 对比 L02：那里 swarm 的 triage/refund/after_sales 全平铺在一张图里")
    print("  - 子图的意义：父图简洁，内部复杂度封装，可独立开发/测试/复用")


# ════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════
def main():
    print("=" * 64)
    print("Lesson 03 — 子图 Subgraph：模块化与复用")
    print("=" * 64)
    print("把 L02 的客服 swarm 封装成子图，嵌入更大的父图。")
    print("映射：agent-lessons/08_multi_agent（三个独立函数，无封装）")
    print("兑现：framework-lessons/07 决策表预告的「子图」（本课兑现）")

    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env 里配置 ZHIPUAI_API_KEY")
    llm = ChatZhipuAI(model=CHAT_MODEL, api_key=api_key)

    # 第 1 步：构建子图（L02 的客服 swarm）
    print("\n🔧 构建客服 swarm 子图（triage + refund + after_sales）...")
    service_subgraph = build_customer_service_subgraph(llm)
    print("✅ 子图已编译（可独立运行，也可嵌入父图）")

    # 第 2 步：构建父图（把子图当节点嵌入）
    print("🔧 构建父图（classify + customer_service[子图] + other_handler）...")
    graph = build_parent_graph(llm, service_subgraph)
    print("✅ 父图（含子图）已编译")

    part_1_customer_service_via_subgraph(graph)  # 客服问题走子图
    part_2_other_question_bypass(graph)          # 非客服跳过子图
    part_3_topology(graph)                       # 看子图如何黑盒显示

    print("\n" + "=" * 64)
    print("✅ 子图 Subgraph 小结：")
    print("   - 子图 = 把编译好的图当节点：add_node('name', compiled_graph)")
    print("   - 价值：封装（父图简洁）+ 复用（子图可到处嵌）+ 独立开发测试")
    print("   - State 对齐：父图 State ⊇ 子图 State，子图只读写共享字段")
    print("   - 兑现 framework L07 预告：现在你会用子图管理复杂度了")
    print("   - 对比手写 L08：三个函数平铺无封装 → 子图模块化")
    print("=" * 64)


if __name__ == "__main__":
    main()
