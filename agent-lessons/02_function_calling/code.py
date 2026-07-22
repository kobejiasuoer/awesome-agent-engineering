"""
L02 — Function Calling 深入：让大模型调用工具
==============================================
比 L01 更健壮、更通用的 Agent：
    ① 通用工具调度器（TOOL_REGISTRY 注册表，加工具不用改调度逻辑）
    ② 4 个工具 + 参数解析 + 错误兜底
    ③ 三个实验：正常调用 / 错误处理 / 多轮调用

运行：python agent-lessons/02_function_calling/code.py
"""
from __future__ import annotations

import json
import os
import random
from datetime import datetime

from dotenv import load_dotenv
from zhipuai import ZhipuAI

CHAT_MODEL = "glm-4"  # 想免费可换 "glm-4-flash"
# 智谱当前仅支持 auto，不支持 none 或强制指定某个函数。
# https://docs.bigmodel.cn/cn/guide/capabilities/function-calling
ZHIPU_TOOL_CHOICE = "auto"


def create_client() -> ZhipuAI:
    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env 里配置 ZHIPUAI_API_KEY")
    return ZhipuAI(api_key=api_key)


# ════════════════════════════════════════════════════════════
# 第 1 步：定义工具函数（真正的 Python 实现）
# ════════════════════════════════════════════════════════════
# 注意：每个函数都有完整的错误兜底——这是生产级 Agent 的基本要求。


def get_weather(city: str, unit: str = "摄氏度") -> str:
    """查询城市天气（模拟数据，教学用，不真实联网）。"""
    # 模拟数据
    weather_map = {
        "北京": ("晴", 25), "上海": ("多云", 28), "广州": ("雨", 30),
        "深圳": ("阴", 29), "杭州": ("晴", 26),
    }
    if city not in weather_map:
        return f"抱歉，没有 {city} 的天气数据（目前只支持：{list(weather_map.keys())}）"
    condition, temp = weather_map[city]
    if unit == "华氏度":
        temp = temp * 9 / 5 + 32
        return f"{city}：{condition}，气温 {temp:.0f}°F"
    return f"{city}：{condition}，气温 {temp}°C"


def calculator(expression: str) -> str:
    """计算数学表达式。"""
    try:
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expression):
            return "错误：表达式包含非法字符"
        result = eval(expression)  # 教学用，生产环境别用 eval
        return str(result)
    except ZeroDivisionError:
        return "错误：除数不能为 0"
    except Exception as e:
        return f"计算错误：{e}"


def string_length(text: str) -> str:
    """返回字符串的字符数。"""
    return f"字符串 '{text}' 的长度是 {len(text)} 个字符"


def random_choice(items: list) -> str:
    """从列表里随机选一个。"""
    if not items:
        return "错误：列表为空，无法选择"
    chosen = random.choice(items)
    return f"从 {items} 中随机选了：{chosen}"


# ════════════════════════════════════════════════════════════
# 第 2 步：工具注册表 + tools 定义
# ════════════════════════════════════════════════════════════
# TOOL_REGISTRY：函数名 → 真正的 Python 函数（调度器用它查找）
# TOOLS_SPEC：给大模型看的工具描述（JSON Schema）

TOOL_REGISTRY = {
    "get_weather": get_weather,
    "calculator": calculator,
    "string_length": string_length,
    "random_choice": random_choice,
}

TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的天气。当用户问'XX天气''XX下雨吗''气温多少'时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名，如'北京'、'上海'"},
                    "unit": {"type": "string", "enum": ["摄氏度", "华氏度"], "description": "温度单位，默认摄氏度"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算数学表达式。需要精确计算加减乘除时使用。expression 是数学表达式，如 '12 * 34' 或 '100 / 7'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式，如 '3 * (4 + 5)'"},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "string_length",
            "description": "计算字符串的字符数。当用户问'XX有几个字''XX多长'时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要计算长度的字符串"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "random_choice",
            "description": "从一个列表中随机选择一个元素。当用户说'帮我随机选一个''抽签'时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "string"}, "description": "候选列表，如 ['苹果', '香蕉', '橘子']"},
                },
                "required": ["items"],
            },
        },
    },
]


# ════════════════════════════════════════════════════════════
# 第 3 步：通用工具调度器（生产级，带错误兜底）
# ════════════════════════════════════════════════════════════
def execute_function(name: str, arguments: dict) -> str:
    """根据函数名从注册表查找并执行，带完整的错误处理。

    这是比 L01 更通用的写法：用注册表（字典）查找函数，
    加新工具只需注册到 TOOL_REGISTRY，不用改这里的 if/elif。
    """
    # ① 函数不存在
    if name not in TOOL_REGISTRY:
        return f"错误：工具 '{name}' 不存在。可用工具：{list(TOOL_REGISTRY.keys())}"

    func = TOOL_REGISTRY[name]

    # ② 执行函数，捕获所有异常（绝不让 Agent 因工具报错而崩溃）
    try:
        result = func(**arguments)
    except TypeError as e:
        # 参数不匹配（缺少必填参数、多了未知参数等）
        return f"参数错误：{e}。你传的参数是：{arguments}"
    except Exception as e:
        # 其他所有错误
        return f"工具执行失败：{e}"

    return str(result)


# ════════════════════════════════════════════════════════════
# 第 4 步：Agent 循环（和 L01 类似，但更健壮）
# ════════════════════════════════════════════════════════════
def run_agent(client: ZhipuAI, user_question: str, max_steps: int = 6) -> str | None:
    """运行 Agent 处理问题。"""
    messages = [{"role": "user", "content": user_question}]

    for step in range(1, max_steps + 1):
        print(f"\n{'─' * 50}\n🔄 第 {step} 步")

        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            tools=TOOLS_SPEC,
            tool_choice=ZHIPU_TOOL_CHOICE,
        )
        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg.model_dump())
            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                # 参数解析：模型返回的是 JSON 字符串，要解析成字典
                try:
                    func_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}
                    print(f"⚠️ 参数 JSON 解析失败，用空参数兜底")

                print(f"🤔 调用 {func_name}({func_args})")
                result = execute_function(func_name, func_args)
                print(f"🔧 结果：{result}")

                messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                )
        else:
            print(f"💬 最终回答：\n{msg.content}")
            return msg.content

    print("⚠️ 达到最大步数。")
    return None


# ════════════════════════════════════════════════════════════
# 主流程：三个实验
# ════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("L02 — Function Calling 深入")
    print("=" * 60)

    client = create_client()

    # 实验 1：正常调用（看工具调度器怎么分发）
    print("\n\n" + "═" * 60)
    print("实验 1：正常调用多工具")
    print("═" * 60)
    run_agent(client, "北京和上海今天天气怎么样？'你好世界'有几个字？")

    # 实验 2：错误处理（故意触发除以 0）
    print("\n\n" + "═" * 60)
    print("实验 2：错误处理（故意触发错误）")
    print("═" * 60)
    run_agent(client, "帮我算一下 10 / 0 等于多少？")

    # 实验 3：多轮调用（一个任务需要多个工具配合）
    print("\n\n" + "═" * 60)
    print("实验 3：多轮调用（多个工具配合）")
    print("═" * 60)
    run_agent(
        client,
        "帮我随机从['红','绿','蓝']选一个颜色，"
        "然后算一下这个颜色名有几个字，再告诉我北京天气。",
    )

    print("\n" + "=" * 60)
    print("完成！核心要点：通用调度器 + 错误兜底 = 健壮的 Agent。")
    print("=" * 60)


if __name__ == "__main__":
    main()
