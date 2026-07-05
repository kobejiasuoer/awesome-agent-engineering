"""
L06 — 规划与任务分解
====================
实现 Plan-and-Execute 模式，并和 ReAct 对比：
    ① plan()：让 LLM 输出任务计划（JSON 步骤列表）
    ② execute_plan()：逐步执行计划，每步可调用工具
    ③ 对比 Plan-Execute 和 ReAct 的工作方式差异

运行：python agent-lessons/06_planning/code.py
"""
from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv
from zhipuai import ZhipuAI

CHAT_MODEL = "glm-4"  # 想免费可换 "glm-4-flash"


def create_client() -> ZhipuAI:
    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env 里配置 ZHIPUAI_API_KEY")
    return ZhipuAI(api_key=api_key)


# ════════════════════════════════════════════════════════════
# 工具（复用前面的，保持简洁）
# ════════════════════════════════════════════════════════════


def get_weather(city: str, unit: str = "摄氏度") -> str:
    weather_map = {
        "北京": ("晴", 25), "上海": ("多云", 28), "广州": ("雨", 30),
        "深圳": ("阴", 29), "杭州": ("晴", 26),
    }
    if city not in weather_map:
        return f"抱歉，没有 {city} 的天气数据。支持：{list(weather_map.keys())}"
    cond, t = weather_map[city]
    return f"{city}：{cond}，{t}°C"


def calculator(expression: str) -> str:
    try:
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expression):
            return "错误：表达式包含非法字符"
        return str(eval(expression))
    except Exception as e:
        return f"计算错误：{e}"


TOOL_REGISTRY = {"get_weather": get_weather, "calculator": calculator}

TOOLS_SPEC = [
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "查询指定城市的天气。当需要知道某城市温度/天气状况时使用。",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "城市名"},
        }, "required": ["city"]},
    }},
    {"type": "function", "function": {
        "name": "calculator",
        "description": "计算数学表达式。需要精确计算时使用。expression 如 '28-25'。",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string", "description": "数学表达式"},
        }, "required": ["expression"]},
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
# 阶段 1：Plan（让 LLM 输出任务计划）
# ════════════════════════════════════════════════════════════
def plan(client: ZhipuAI, task: str) -> list[str]:
    """让 LLM 把任务分解成步骤列表（JSON 格式）。

    关键：要求模型输出 JSON，并给格式示例，确保可解析。
    """
    prompt = f"""你是一个任务规划专家。请把下面的任务分解成清晰的执行步骤。

要求：
1. 输出一个 JSON 对象，格式为 {{"steps": ["步骤1", "步骤2", ...]}}
2. 每个步骤是一个具体的、可执行的动作
3. 步骤要覆盖完成任务需要的所有操作（包括查数据、计算、总结等）
4. 只输出 JSON，不要其他内容

任务：{task}

步骤计划："""

    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    content = resp.choices[0].message.content.strip()

    # 从模型回复里提取 JSON（模型可能在前后加了 ```json 标记）
    json_match = re.search(r'\{[^{}]*"steps"[^{}]*\}', content, re.DOTALL)
    if json_match:
        content = json_match.group(0)

    try:
        plan_data = json.loads(content)
        return plan_data.get("steps", [])
    except json.JSONDecodeError:
        # 解析失败兜底：按行分割
        print(f"⚠️ JSON 解析失败，原始输出：{content[:100]}")
        return [content]


# ════════════════════════════════════════════════════════════
# 阶段 2：Execute（逐步执行计划）
# ════════════════════════════════════════════════════════════
def execute_plan(client: ZhipuAI, task: str, steps: list[str]) -> str:
    """逐步执行计划。每步带着任务+已完成步骤的结果，让 LLM 决定调什么工具。

    和 ReAct 的区别：这里有一个明确的"计划清单"在指导执行，
    Agent 知道总共有几步、当前在第几步、后面还有什么。
    """
    # 记录已完成的步骤结果（作为上下文传给后续步骤）
    completed = []

    for i, step in enumerate(steps, 1):
        print(f"\n📌 步骤 {i}/{len(steps)}：{step}")

        # 把任务、计划、已完成步骤的结果都告诉 LLM，让它执行当前步骤
        context = f"""你正在执行一个多步骤任务。

原始任务：{task}
完整计划：{json.dumps(steps, ensure_ascii=False)}
已完成步骤的结果：{json.dumps(completed, ensure_ascii=False) if completed else '（还没有）'}

现在请执行【步骤 {i}】：{step}
你可以调用工具来获取信息或计算。如果这一步不需要工具，直接基于已有信息回答。"""

        messages = [{"role": "user", "content": context}]
        max_tries = 3  # 每个步骤最多尝试3次工具调用

        for _ in range(max_tries):
            resp = client.chat.completions.create(
                model=CHAT_MODEL, messages=messages, tools=TOOLS_SPEC, tool_choice="auto"
            )
            msg = resp.choices[0].message

            if msg.tool_calls:
                messages.append(msg.model_dump())
                for tc in msg.tool_calls:
                    name = tc.function.name
                    args = json.loads(tc.function.arguments)
                    result = execute_function(name, args)
                    print(f"   🔧 调用 {name}({args}) → {result}")
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            else:
                # 这一步完成，记录结果
                print(f"   ✅ 结果：{msg.content[:80]}")
                completed.append({"step": step, "result": msg.content})
                break
        else:
            completed.append({"step": step, "result": "（达到最大尝试次数）"})

    # 返回最后一步的结果作为最终答案
    return completed[-1]["result"] if completed else ""


# ════════════════════════════════════════════════════════════
# 对比用：ReAct 方式（边想边做，无全局计划）
# ════════════════════════════════════════════════════════════
def run_react(client: ZhipuAI, task: str, max_steps: int = 6):
    """简化版 ReAct：直接带着任务循环调工具，没有预先规划。"""
    print(f"\n（ReAct：边想边做，无预先计划）")
    messages = [{"role": "user", "content": task}]
    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(
            model=CHAT_MODEL, messages=messages, tools=TOOLS_SPEC, tool_choice="auto"
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append(msg.model_dump())
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                result = execute_function(name, args)
                print(f"   第{step}步 🔧 {name}({args}) → {result}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        else:
            print(f"   第{step}步 💬 {msg.content[:80]}")
            return msg.content
    return None


# ════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("L06 — 规划与任务分解")
    print("=" * 60)
    client = create_client()

    task = "帮我查明天上海的天气，如果下雨就推荐室内活动，否则推荐户外活动，最后把推荐理由说出来。"

    # === Plan-and-Execute ===
    print("\n\n" + "═" * 60)
    print("方式一：Plan-and-Execute（先规划，再执行）")
    print("═" * 60)

    print(f"\n🧠 任务：{task}")
    print("\n📋 规划阶段（让 LLM 分解任务）...")
    steps = plan(client, task)
    print(f"计划共 {len(steps)} 步：")
    for i, s in enumerate(steps, 1):
        print(f"  {i}. {s}")

    print("\n🏃 执行阶段...")
    execute_plan(client, task, steps)

    # === 对比 ReAct ===
    print("\n\n" + "═" * 60)
    print("方式二：ReAct（边想边做，无预先规划）")
    print("═" * 60)
    print(f"\n🧠 同样的任务：{task}")
    run_react(client, task)

    print("\n\n" + "═" * 60)
    print("对比要点：")
    print("  Plan-Execute：先看到完整计划清单，再逐步执行——有全局视野。")
    print("  ReAct：边走边看，灵活但可能遗漏或走弯路。")
    print("  💡 复杂任务用 Plan-Execute，探索性任务用 ReAct。")
    print("=" * 60)


if __name__ == "__main__":
    main()
