"""
L09 — 毕业项目：智能研究助手（简历级）
========================================
综合前 8 课所有技术，做一个能进简历的 Agent：
    用户给主题 → Agent 自主联网搜索 → 多轮补充 → 生成结构化研究报告

集成技术：
    - Function Calling（搜索工具）
    - ReAct 循环（思考→行动→观察）
    - 记忆（保留搜索历史）
    - 规划（自主决定搜什么）
    - 错误处理（搜索失败优雅降级）
    - 工程化（步数限制、日志、来源引用）

运行：python agent-lessons/09_capstone/code.py
"""
from __future__ import annotations

import json
import os
import warnings

from dotenv import load_dotenv
# 过滤 duckduckgo_search 包改名提示（不影响使用）
warnings.filterwarnings("ignore", message=".*renamed.*")
from ddgs import DDGS
from zhipuai import ZhipuAI

CHAT_MODEL = "glm-4"  # 想免费可换 "glm-4-flash"
MAX_STEPS = 8  # Agent 最大循环步数（防止无限搜索烧钱）


def create_client() -> ZhipuAI:
    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env 里配置 ZHIPUAI_API_KEY")
    return ZhipuAI(api_key=api_key)


# ════════════════════════════════════════════════════════════
# 代理配置（DuckDuckGo 国内无法直连，需要走代理）
# 如果你有 HTTP 代理，填在下面；没有的话设置成 None 试试能不能通
# ════════════════════════════════════════════════════════════
PROXY = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or None  # 如 "http://127.0.0.1:7890"


# ════════════════════════════════════════════════════════════
# 工具 1：联网搜索（核心工具，用 DuckDuckGo，免费无 key）
# ════════════════════════════════════════════════════════════
def web_search(query: str, max_results: int = 5) -> str:
    """联网搜索，返回搜索结果摘要。

    错误兜底：搜索失败时返回友好提示（不崩溃），让 Agent 知道可以重试。
    """
    try:
        ddgs = DDGS(proxy=PROXY)
        results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return f"搜索 '{query}' 没有返回结果。可以换个关键词试试。"

        # 整理成简洁文本（标题 + 摘要 + 链接）
        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", "")[:150]  # 摘要截断，控制长度
            href = r.get("href", "")
            formatted.append(f"[{i}] {title}\n    {body}\n    来源: {href}")
        return "\n".join(formatted)
    except Exception as e:
        # 错误兜底：返回友好信息，Agent 可以换关键词重试
        return f"搜索失败（{type(e).__name__}）。可以换个关键词或稍后再试。"


# ════════════════════════════════════════════════════════════
# 工具 2：生成最终报告（把搜集的信息整理成结构化报告）
# ════════════════════════════════════════════════════════════
def generate_report(topic: str, collected_info: str) -> str:
    """这不是一个 function calling 工具，而是最终整理步骤。

    把 Agent 搜集到的所有信息，整理成结构化研究报告。
    """
    prompt = f"""你是一个研究助理。请根据下面搜集到的信息，写一份关于「{topic}」的结构化研究报告。

要求：
1. 包含：概述、核心要点（3-5条）、总结
2. 每个要点尽量标注来源
3. 如果信息不足，在总结里说明"现有信息有限，建议进一步研究"
4. 语言简洁专业

搜集到的信息：
{collected_info}

研究报告："""
    client = create_client()
    resp = client.chat.completions.create(
        model=CHAT_MODEL, messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content


# ════════════════════════════════════════════════════════════
# 工具注册（只有 web_search 是 function calling 工具）
# ════════════════════════════════════════════════════════════
TOOL_REGISTRY = {"web_search": web_search}

TOOLS_SPEC = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": (
            "联网搜索互联网信息。当你需要查找某个主题的资料、最新信息、事实数据时使用。"
            "query 是搜索关键词。如果一次搜索信息不够，可以换不同关键词多次搜索。"
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索关键词，如 'RAG技术 原理'"},
            "max_results": {"type": "integer", "description": "返回结果数量，默认5"},
        }, "required": ["query"]},
    }},
]


def execute_function(name: str, args: dict) -> str:
    if name not in TOOL_REGISTRY:
        return f"错误：工具 '{name}' 不存在"
    try:
        return str(TOOL_REGISTRY[name](**args))
    except Exception as e:
        return f"工具失败：{e}"


# ════════════════════════════════════════════════════════════
# ReAct system prompt（让 Agent 显式思考 + 自主规划搜索）
# ════════════════════════════════════════════════════════════
RESEARCH_SYSTEM_PROMPT = """你是一个专业的研究助手 Agent。你的任务是针对用户给的研究主题，通过联网搜索收集信息，最终生成研究报告。

工作方式（ReAct 循环）：
1. 每一步先写 Thought（你的思考）：分析当前掌握了什么信息、还需要搜什么
2. 调用 web_search 搜索你需要的信息
3. 看搜索结果（Observation），判断信息够不够
4. 如果不够，换关键词再搜（多轮搜索）
5. 当你认为信息足够时，写 "FINAL_REPORT" 表示可以生成报告了

原则：
- 搜索关键词要具体、有针对性
- 同一个关键词不要重复搜
- 一般搜索 2-4 次就能收集足够信息
- 每一步都要先写 Thought 再行动"""


# ════════════════════════════════════════════════════════════
# 核心：研究 Agent 的 ReAct 循环
# ════════════════════════════════════════════════════════════
def run_research_agent(client: ZhipuAI, topic: str, max_steps: int = MAX_STEPS) -> str:
    """运行研究 Agent：自主搜索 + 收集信息 + 生成报告。

    这就是前 8 课技术的综合应用：
        - ReAct 循环（L03）：Thought → Action → Observation
        - Function Calling（L02）：调用 web_search
        - 记忆（L05）：messages 保留所有搜索历史
        - 规划（L06）：Agent 自主决定搜什么
        - 错误处理（L02）：搜索失败优雅降级
    """
    print(f"\n🎯 研究主题：{topic}")
    print("=" * 60)

    messages = [
        {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
        {"role": "user", "content": f"请帮我研究：{topic}"},
    ]

    collected_sources = []  # 记录所有搜索过的来源（供最终报告引用）

    for step in range(1, max_steps + 1):
        print(f"\n{'━' * 50}")
        print(f"🔄 第 {step}/{max_steps} 步")

        response = client.chat.completions.create(
            model=CHAT_MODEL, messages=messages, tools=TOOLS_SPEC, tool_choice="auto"
        )
        msg = response.choices[0].message

        # 打印 Agent 的思考过程（ReAct 的核心价值：推理可见）
        if msg.content:
            if "FINAL_REPORT" in msg.content:
                print(f"💭 {msg.content[:100]}")
                print(f"\n{'━' * 50}")
                print("✅ Agent 判断信息已足够，开始生成报告...")
                break
            else:
                print(f"💭 Thought: {msg.content}")

        # 执行搜索工具
        if msg.tool_calls:
            messages.append(msg.model_dump())
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                print(f"🔍 Action: web_search({args.get('query')})")

                result = execute_function(name, args)
                collected_sources.append({"query": args.get("query"), "result": result})

                # 打印搜索结果摘要
                result_preview = result[:120].replace("\n", " ")
                print(f"👁️ Observation: {result_preview}...")

                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result}
                )
        else:
            # 没调工具也没说 FINAL_REPORT——可能直接回答了
            if msg.content:
                break
    else:
        print(f"\n⚠️ 达到最大步数 {max_steps}，强制进入报告生成。")

    # 生成最终报告（把所有搜集的信息整理）
    print(f"\n{'━' * 50}")
    print("📝 正在生成研究报告...")

    collected_info = "\n\n".join(
        f"搜索「{s['query']}」的结果:\n{s['result']}" for s in collected_sources
    )
    if not collected_info:
        collected_info = "（Agent 没有搜集到任何信息）"

    report = generate_report(topic, collected_info)
    print(f"\n{'═' * 60}")
    print(f"📋 研究报告：{topic}")
    print(f"{'═' * 60}")
    print(report)
    print(f"\n{'─' * 60}")
    print(f"本次共搜索 {len(collected_sources)} 次。")
    print(f"{'═' * 60}")
    return report


# ════════════════════════════════════════════════════════════
# 主流程：演示 + 交互模式
# ════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("L09 — 毕业项目：智能研究助手")
    print("=" * 60)
    print("这是一个综合了前 8 课所有技术的 Agent 项目。")
    print("给它一个研究主题，它会自主联网搜索并生成报告。")

    client = create_client()

    # 演示主题（先跑一个让大家看到效果）
    demo_topic = "2024年有哪些重要的大模型技术进展"
    print(f"\n先演示一个主题：{demo_topic}")
    run_research_agent(client, demo_topic)

    # 交互模式
    print("\n\n" + "=" * 60)
    print("进入交互模式，输入你想研究的主题（输 exit 退出）：")
    print("=" * 60)
    while True:
        try:
            topic = input("\n🔬 研究主题> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not topic:
            continue
        if topic.lower() in ("exit", "quit", "退出"):
            break
        run_research_agent(client, topic)

    print("\n再见！这个项目可以写进简历 😊")


if __name__ == "__main__":
    main()
