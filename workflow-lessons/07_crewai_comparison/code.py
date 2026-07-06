"""
Lesson 07 — CrewAI 对比：角色驱动的声明式编排
================================================
LangGraph 段（L01-L06）已收官。本课进入横向框架对比段。

核心问题：
    同一个多 Agent 系统，用 CrewAI 写和用 LangGraph 写，有什么差别？

两种范式：
    LangGraph：命令式——你画"节点+边"的图（L01-L06 一直在做）
    CrewAI：声明式——你声明"角色+任务+编队"，框架自动编排

三个部分：
  ① CrewAI sequential：按角色顺序自动执行（对应手写 L08 流水线）
  ② CrewAI hierarchical：manager 动态调度（对应 L01 supervisor）
  ③ 代码量对比：同样系统，CrewAI vs LangGraph 各多少行

对比基准：workflow-lessons/01_supervisor_pattern（L01 的 supervisor 系统）
运行：python workflow-lessons/07_crewai_comparison/code.py
"""
# 消除警告
import warnings
warnings.filterwarnings("ignore", message=".*langchain-community.*is being sunset.*")
try:
    from jwt.warnings import InsecureKeyLengthWarning
    warnings.filterwarnings("ignore", category=InsecureKeyLengthWarning)
except ImportError:
    pass

import os

# ⚠️ CrewAI 接国产模型的关键设置（教学金矿）
# 1. 必须用 litellm 桥接：model 名加 'openai/' 前缀
# 2. 必须关 tracing，否则会弹交互提示卡住
os.environ["CREWAI_TRACING_ENABLED"] = "false"

from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM  # CrewAI 三件套

SMART_MODEL = "openai/glm-4"        # litellm 前缀走 OpenAI 兼容协议
FAST_MODEL = "openai/glm-4-flash"   # 免费版


# ════════════════════════════════════════════════════════════
# 第 1 步：创建 LLM 实例（CrewAI 接国产模型的方式）
# ════════════════════════════════════════════════════════════
def create_llm():
    """创建 CrewAI 的 LLM 实例。

    ⚠️ 教学金矿：CrewAI 接国产模型（智谱 GLM）的方式
    - model 名必须加 'openai/' 前缀（告诉 litellm 走 OpenAI 兼容协议）
    - 传 api_key 和 base_url 指向智谱
    - 这和 LangGraph 用 ChatZhipuAI 不同——CrewAI 不认识 ChatZhipuAI

    对比 L01 LangGraph：
        LangGraph: llm = ChatZhipuAI(model='glm-4', api_key=...)   # 直接用智谱封装
        CrewAI:    llm = LLM(model='openai/glm-4', api_key=..., base_url=...)  # 走 litellm
    """
    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env 里配置 ZHIPUAI_API_KEY")
    return LLM(
        model=FAST_MODEL,
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4",
    )


# ════════════════════════════════════════════════════════════
# 实验 1：CrewAI sequential（按角色顺序自动执行）
# ════════════════════════════════════════════════════════════
def part_1_sequential(llm):
    """CrewAI sequential process：按 agents 列表顺序自动执行。

    这对应手写 L08 的流水线（planner→executor→reviewer）和 LangGraph 的串行图。
    但 CrewAI 你不用画图、不用连边——声明角色 + 任务，框架自动按顺序跑。
    """
    print("\n" + "─" * 60)
    print("实验 1：CrewAI sequential（按角色顺序自动执行）")
    print("─" * 60)

    # ── 声明 3 个角色（对应 L01 的 researcher/analyst/writer）──
    # CrewAI 的 Agent 三要素：role（角色）+ goal（目标）+ backstory（背景）
    researcher = Agent(
        role="研究员",
        goal="收集事实信息，简洁回答",
        backstory="你是资深研究员，擅长查资料。",
        llm=llm,
    )
    analyst = Agent(
        role="分析师",
        goal="分析信息得出结论",
        backstory="你是数据专家，擅长分析。",
        llm=llm,
    )
    writer = Agent(
        role="撰写者",
        goal="整理成通顺的文字",
        backstory="你是文案专家。",
        llm=llm,
    )

    # ── 声明任务（每个任务指定由谁做）──
    task = Task(
        description="查一下什么是 RAG 技术，分析它的一个优点，整理成一段介绍。",
        expected_output="一段关于 RAG 的完整介绍",
        agent=researcher,  # 起始 agent，sequential 会按 agents 顺序传递
    )

    # ── 组建编队（Crew）──
    # ⭐ 这就是 CrewAI 的核心：声明 agents + tasks + process，框架自动编排
    # 对比 LangGraph：那里你要 add_node + add_edge + compile，手动画图
    crew = Crew(
        agents=[researcher, analyst, writer],
        tasks=[task],
        process=Process.sequential,  # 按顺序：研究→分析→写作
        verbose=False,
    )

    print("📋 任务：查 RAG 技术 + 分析优点 + 整理成文")
    print("🔧 编队：研究员→分析师→撰写者（sequential 自动按顺序）\n")

    result = crew.kickoff()
    print(f"\n✅ 结果：\n{str(result).strip()[:200]}")

    print(f"\n💡 观察：你没画任何图、没连任何边。")
    print(f"   只声明了角色（role/goal/backstory）+ 任务 + 编队，")
    print(f"   CrewAI 自动按顺序执行——这就是「声明式编排」。")
    print(f"   对比 LangGraph L01：你要写 create_agent + create_supervisor + compile。")


# ════════════════════════════════════════════════════════════
# 实验 2：CrewAI hierarchical（manager 动态调度 = L01 supervisor）
# ════════════════════════════════════════════════════════════
def part_2_hierarchical(llm):
    """CrewAI hierarchical process：manager 动态调度。

    这就是 L01 supervisor 的 CrewAI 版本！
    hierarchical 模式下，CrewAI 自动创建一个 manager（=supervisor），
    manager 根据 task 内容动态决定派给哪个 agent。
    """
    print("\n\n" + "─" * 60)
    print("实验 2：CrewAI hierarchical（manager 动态调度 = L01 supervisor）")
    print("─" * 60)

    researcher = Agent(
        role="研究员", goal="收集事实信息", backstory="资深研究员", llm=llm,
    )
    analyst = Agent(
        role="分析师", goal="分析数据得出结论", backstory="数据专家", llm=llm,
    )

    # hierarchical 模式：task 不指定 agent，由 manager 决定
    task1 = Task(
        description="查一下什么是 RAG 技术",
        expected_output="RAG 技术简介",
        # ⚠️ hierarchical 也可以指定 agent，但 manager 会决定执行顺序
        agent=researcher,
    )
    task2 = Task(
        description="分析 RAG 的一个优点",
        expected_output="优点分析",
        agent=analyst,
    )

    # ⭐ hierarchical 必须指定 manager_llm（manager = supervisor）
    crew = Crew(
        agents=[researcher, analyst],
        tasks=[task1, task2],
        process=Process.hierarchical,
        manager_llm=llm,  # ⭐ manager（调度中心）用什么 LLM
        verbose=False,
    )

    print("📋 任务：查 RAG + 分析优点")
    print("🔧 编队：hierarchical 模式，manager 自动调度\n")

    result = crew.kickoff()
    print(f"\n✅ 结果：\n{str(result).strip()[:200]}")

    print(f"\n💡 对比 L01 supervisor：")
    print(f"   LangGraph: create_supervisor(agents=..., model=..., prompt=...) → 自动调度")
    print(f"   CrewAI:    Crew(agents=..., process=hierarchical, manager_llm=...) → 自动调度")
    print(f"   两者都是「manager/supervisor 动态决定派给谁」，只是 API 不同。")
    print(f"   CrewAI 更简洁（不用写 prompt 教 manager 怎么调度）。")


# ════════════════════════════════════════════════════════════
# 实验 3：代码量对比（CrewAI vs LangGraph）
# ════════════════════════════════════════════════════════════
def part_3_code_comparison():
    """打印同样系统的两种写法，对比代码量和可读性。"""
    print("\n\n" + "─" * 60)
    print("实验 3：代码量对比（同样系统，CrewAI vs LangGraph）")
    print("─" * 60)

    print("""
同样的「supervisor 调度 researcher + analyst」系统：

【CrewAI 版】（声明式，~12 行）
─────────────────────────────
researcher = Agent(role='研究员', goal='查资料', backstory='...', llm=llm)
analyst = Agent(role='分析师', goal='分析', backstory='...', llm=llm)
task1 = Task(description='查RAG', expected_output='简介', agent=researcher)
task2 = Task(description='分析RAG优点', expected_output='分析', agent=analyst)
crew = Crew(agents=[researcher, analyst], tasks=[task1, task2],
            process=Process.hierarchical, manager_llm=llm)
result = crew.kickoff()
─────────────────────────────

【LangGraph 版】（命令式，~15 行，来自 L01）
─────────────────────────────
researcher = create_agent(llm, tools=[], name='researcher',
                          system_prompt='你是研究员...')
analyst = create_agent(llm, tools=[], name='analyst',
                       system_prompt='你是分析师...')
supervisor = create_supervisor(
    agents=[researcher, analyst],
    model=llm,
    prompt='你是调度中心。研究派 researcher，分析派 analyst。',
    output_mode='full_history',
)
graph = supervisor.compile()
result = graph.invoke({'messages': [{'role':'user','content':'查RAG并分析'}]})
─────────────────────────────
""")

    print("📊 对比：")
    print("   CrewAI 更简洁（不用 system_prompt、不用 output_mode）")
    print("   LangGraph 更灵活（能精确控制每个节点的行为、流式、HITL）")
    print()
    print("💡 选型建议：")
    print("   快速原型/角色明确的场景 → CrewAI（声明式，少写代码）")
    print("   需要精细控制（子图/并行/HITL/流式）→ LangGraph（命令式，更灵活）")


# ════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════
def main():
    print("=" * 64)
    print("Lesson 07 — CrewAI 对比：角色驱动的声明式编排")
    print("=" * 64)
    print("用 CrewAI 重写 L01 的 supervisor 系统，对比两种范式。")
    print("对比基准：workflow-lessons/01_supervisor_pattern")

    llm = create_llm()

    part_1_sequential(llm)     # sequential（流水线）
    part_2_hierarchical(llm)   # hierarchical（supervisor）
    part_3_code_comparison()   # 代码量对比

    print("\n" + "=" * 64)
    print("✅ CrewAI 对比小结：")
    print("   - CrewAI 三件套：Agent(角色) + Task(任务) + Crew(编队)")
    print("   - sequential：按 agents 顺序自动执行（对应流水线）")
    print("   - hierarchical：manager 动态调度（对应 L01 supervisor）")
    print("   - 范式差异：声明式（角色+任务）vs 命令式（节点+边）")
    print("   - 接国产模型：LLM(model='openai/glm-4') 走 litellm + 关 tracing")
    print("   - 选型：快速原型用 CrewAI，精细控制用 LangGraph")
    print("=" * 64)


if __name__ == "__main__":
    main()
