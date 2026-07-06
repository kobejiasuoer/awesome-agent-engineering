"""
Lesson 08 — AutoGen 对比：对话驱动的群聊编排
==============================================
横向对比段的最后一课。AutoGen 用「对话」作为一等公民——
多个 Agent 在一个 GroupChat 里像开会一样轮流发言。

核心问题：
    Agent L08 exercise 留了「辩论模式」的骨架没实现——本课用 AutoGen 补全。
    同时对比三种范式：LangGraph（图）/ CrewAI（角色）/ AutoGen（对话）。

三个部分：
  ① 辩论模式：RoundRobinGroupChat 让正方/反方轮流辩论（补 Agent L08 坑）
  ② Selector 群聊：LLM 选择发言者（对应 L01 supervisor）
  ③ 三框架范式对比总结

补全：agent-lessons/08_multi_agent exercise 留的「辩论模式」骨架
对比：workflow-lessons/01_supervisor_pattern（L01）+ 07_crewai_comparison（L07）
运行：python workflow-lessons/08_autogen_comparison/code.py
"""
# 消除警告
import warnings
warnings.filterwarnings("ignore", message=".*langchain-community.*is being sunset.*")
try:
    from jwt.warnings import InsecureKeyLengthWarning
    warnings.filterwarnings("ignore", category=InsecureKeyLengthWarning)
except ImportError:
    pass

import asyncio
import os

from dotenv import load_dotenv
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat, SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_ext.models.openai import OpenAIChatCompletionClient

CHAT_MODEL = "glm-4-flash"  # AutoGen 也用智谱


# ════════════════════════════════════════════════════════════
# 第 1 步：创建模型 client（AutoGen 接国产模型的方式）
# ════════════════════════════════════════════════════════════
def create_model_client():
    """创建 AutoGen 的模型 client。

    ⚠️ 教学金矿：AutoGen 0.4+ 接国产模型的两个坑
    1. 用 OpenAIChatCompletionClient + base_url 指向智谱
    2. ⭐⭐⭐ 非 OpenAI 模型必须手传 model_info！
       否则报 ValueError: model_info is required when model name is not a valid OpenAI model
       （AutoGen 内置了 OpenAI 模型白名单，不认识 glm-4-flash）

    对比 CrewAI（L07）：CrewAI 走 litellm 桥接，不用传 model_info
    对比 LangGraph：LangGraph 用 ChatZhipuAI 封装，最简单
    """
    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env 里配置 ZHIPUAI_API_KEY")
    return OpenAIChatCompletionClient(
        model=CHAT_MODEL,
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4",
        # ⭐ 非 OpenAI 模型必须手传 model_info（AutoGen 白名单坑）
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
            "structured_output": True,
            "multiple_system_messages": True,
        },
    )


# ════════════════════════════════════════════════════════════
# 辅助：打印群聊消息流
# ════════════════════════════════════════════════════════════
def print_conversation(messages):
    """打印 AutoGen 的对话流（标注每个发言者）。"""
    print("━" * 60)
    for m in messages:
        source = getattr(m, "source", "?")
        content = str(getattr(m, "content", "")).replace("\n", " ")
        if len(content) > 80:
            content = content[:80] + "..."
        print(f"  [{source}]: {content}")
    print("━" * 60)


# ════════════════════════════════════════════════════════════
# 实验 1：辩论模式（RoundRobinGroupChat）—— 补 Agent L08 坑
# ════════════════════════════════════════════════════════════
async def part_1_debate(model_client):
    """辩论模式：正方 vs 反方轮流发言。

    🎯 补全 Agent L08 exercise 留的坑：
       Agent L08 exercise 练习 3 要求实现「辩论模式」，但只给了 prompt 骨架，
       没有成品。本实验用 AutoGen 的 RoundRobinGroupChat 实现。

    RoundRobin = 轮流：正方→反方→正方→反方...
    对比 LangGraph swarm（L02）：那里用 handoff 交接，AutoGen 用 GroupChat 轮转。
    """
    print("\n" + "─" * 60)
    print("实验 1：辩论模式（RoundRobinGroupChat）—— 补 Agent L08 坑")
    print("─" * 60)

    proponent = AssistantAgent(
        "proponent",
        model_client=model_client,
        system_message=(
            "你是辩论正方，认为「AI 会取代程序员」。"
            "每次发言 2-3 句话反驳对方、论证己方观点。"
            "认为辩论可以结束时，在末尾说 CONCLUDE。"
        ),
    )
    opponent = AssistantAgent(
        "opponent",
        model_client=model_client,
        system_message=(
            "你是辩论反方，认为「AI 不会取代程序员」。"
            "每次发言 2-3 句话反驳对方、论证己方观点。"
            "认为辩论可以结束时，在末尾说 CONCLUDE。"
        ),
    )

    # RoundRobin：参与者轮流发言
    # 终止条件：有人说 CONCLUDE，或达到 6 条消息（防无限辩论）
    team = RoundRobinGroupChat(
        participants=[proponent, opponent],
        termination_condition=(
            TextMentionTermination("CONCLUDE")
            | MaxMessageTermination(6)  # ⚠️ 用 | 组合多个终止条件
        ),
    )

    print("📋 辩题：AI 会取代程序员吗？正方先发言（最多 6 轮）\n")

    result = await team.run(task="辩题：AI 会取代程序员吗？正方先发言。")

    print(f"【辩论记录（共 {len(result.messages)} 条发言）】")
    print_conversation(result.messages)

    print(f"\n💡 补全了 Agent L08 exercise 练习 3 的「辩论模式」坑——")
    print(f"   手写实现要管理轮次、终止条件、消息传递；AutoGen 的 RoundRobinGroupChat 一键搞定。")


# ════════════════════════════════════════════════════════════
# 实验 2：Selector 群聊（LLM 选择发言者）—— 对应 L01 supervisor
# ════════════════════════════════════════════════════════════
async def part_2_selector(model_client):
    """Selector 群聊：LLM 根据对话内容选下一个发言者。

    这对应 L01 的 supervisor——只不过这里"调度"是隐式的：
    LLM 看对话历史，决定下一个该谁发言。
    """
    print("\n\n" + "─" * 60)
    print("实验 2：Selector 群聊（LLM 选发言者 = L01 supervisor）")
    print("─" * 60)

    researcher = AssistantAgent(
        "researcher", model_client=model_client,
        system_message="你是研究员，负责查事实、给定义。",
    )
    analyst = AssistantAgent(
        "analyst", model_client=model_client,
        system_message="你是分析师，负责分析优缺点。",
    )

    # SelectorGroupChat：LLM（model_client）选择下一个发言者
    # 对比 RoundRobin：那里是固定轮流，这里是 LLM 智能选择
    team = SelectorGroupChat(
        participants=[researcher, analyst],
        model_client=model_client,  # ⭐ LLM 决定下一个发言者
        termination_condition=MaxMessageTermination(4),
    )

    task = "简要说明什么是 RAG 技术，并分析它的一个优点"
    print(f"📋 任务：{task}\n")

    result = await team.run(task=task)

    print(f"【群聊记录（共 {len(result.messages)} 条）】")
    print_conversation(result.messages)

    print(f"\n💡 对比 L01 supervisor：")
    print(f"   LangGraph: create_supervisor + handoff 工具显式调度")
    print(f"   AutoGen: SelectorGroupChat 让 LLM 隐式选发言者")
    print(f"   AutoGen 更像「开会」——大家在一个群里，主持人(LLM)点谁谁说。")


# ════════════════════════════════════════════════════════════
# 实验 3：三框架范式对比总结
# ════════════════════════════════════════════════════════════
def part_3_three_frameworks_comparison():
    """打印三种框架的范式对比总结。"""
    print("\n\n" + "─" * 60)
    print("实验 3：三框架范式对比总结（LangGraph / CrewAI / AutoGen）")
    print("─" * 60)

    print("""
┌─────────────┬─────────────────┬─────────────────┬─────────────────┐
│             │  LangGraph       │  CrewAI          │  AutoGen         │
│             │  (L01-L06)       │  (L07)           │  (L08)           │
├─────────────┼─────────────────┼─────────────────┼─────────────────┤
│ 核心范式     │ 命令式：画图     │ 声明式：角色     │ 对话式：群聊     │
│             │ (节点+边)        │ (role+task)      │ (GroupChat)      │
├─────────────┼─────────────────┼─────────────────┼─────────────────┤
│ 调度方式     │ 显式(add_edge)   │ 框架自动编排     │ LLM选发言者/轮转 │
├─────────────┼─────────────────┼─────────────────┼─────────────────┤
│ 灵活性       │ ★★★★★ 最高     │ ★★☆ 两预设模式  │ ★★★ 几种群聊    │
├─────────────┼─────────────────┼─────────────────┼─────────────────┤
│ 代码量       │ 多               │ 少               │ 中等             │
├─────────────┼─────────────────┼─────────────────┼─────────────────┤
│ 接国产模型   │ 最简单           │ 需 litellm 桥    │ 需传 model_info  │
│             │ ChatZhipuAI一行  │ openai/前缀      │ (白名单坑)       │
├─────────────┼─────────────────┼─────────────────┼─────────────────┤
│ 同步/异步    │ 同步(invoke)     │ 同步(kickoff)    │ ⭐异步(await)    │
├─────────────┼─────────────────┼─────────────────┼─────────────────┤
│ 特色能力     │ 子图/并行/HITL   │ expected_output  │ 辩论/群聊/终止   │
│             │ 流式/自定义State │ 人设驱动         │ 条件组合         │
├─────────────┼─────────────────┼─────────────────┼─────────────────┤
│ 最适合       │ 复杂生产系统     │ 快速原型         │ 多方对话/辩论    │
└─────────────┴─────────────────┴─────────────────┴─────────────────┘
""")
    print("💡 选型决策树：")
    print("   需要精细控制（子图/并行/HITL）？ → LangGraph")
    print("   需要快速搭原型（角色明确）？     → CrewAI")
    print("   需要多 Agent 自由对话/辩论？     → AutoGen")
    print()
    print("💡 三个框架不冲突，可以组合用：")
    print("   用 CrewAI 快速验证想法 → 用 LangGraph 重写生产版 → 用 AutoGen 做对话类功能")


# ════════════════════════════════════════════════════════════
# 主流程（AutoGen 是异步的，需要 asyncio.run）
# ════════════════════════════════════════════════════════════
async def async_main():
    """AutoGen 的主流程（异步）。"""
    print("=" * 64)
    print("Lesson 08 — AutoGen 对比：对话驱动的群聊编排")
    print("=" * 64)
    print("用 GroupChat 补全 Agent L08 辩论模式坑，对比三框架范式。")
    print("补全：agent-lessons/08_multi_agent exercise 练习 3（辩论模式）")
    print("对比：workflow-lessons/01 + 07（LangGraph + CrewAI）")

    model_client = create_model_client()

    await part_1_debate(model_client)      # 辩论模式（补 Agent L08 坑）
    await part_2_selector(model_client)    # Selector 群聊（对应 supervisor）
    part_3_three_frameworks_comparison()   # 三框架对比总结

    await model_client.close()  # AutoGen 要手动关闭 client

    print("\n" + "=" * 64)
    print("✅ AutoGen 对比小结：")
    print("   - AutoGen 用「对话」组织：多 Agent 在 GroupChat 里发言")
    print("   - RoundRobinGroupChat：轮流发言（辩论/流水线）")
    print("   - SelectorGroupChat：LLM 选发言者（对应 supervisor）")
    print("   - model_info 白名单坑：非 OpenAI 模型必须手传（教学金矿）")
    print("   - 异步架构：async/await（和 LangGraph/CrewAI 的同步不同）")
    print("   - 补全了 Agent L08 exercise 的辩论模式坑 🎯")
    print("   - 三框架各有所长：LangGraph(精细)/CrewAI(简洁)/AutoGen(对话)")
    print("=" * 64)


def main():
    """同步入口，包装异步主流程。"""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
