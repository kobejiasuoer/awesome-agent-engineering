# L02 — Function Calling 深入：让大模型调用工具

> 本课目标：**彻底搞懂 function calling 机制，手写一个通用的工具调度器**。L01 你看到 Agent 能调工具了，但 `tools` 那段 JSON 怎么写、参数怎么解析、出错怎么办——这些细节本课全拆开。
>
> 学完这课，你能自己定义任意工具、处理各种异常情况，写出健壮的 Agent。

---

## 1. 模型怎么"决定"调用工具？

先破除一个误解：**模型并不是真的"理解"了你的函数然后决定调用它。**

Function calling 的本质是：
1. 模型在海量数据上训练过"看到这种工具描述 + 这种问题，应该输出这种 tool_call 格式"的模式
2. 它基于 `description`（工具描述）做**模式匹配**：问题描述和哪个工具描述最契合，就倾向调用哪个
3. 它输出的 `tool_calls` 是**特定格式的文本**，你的代码解析后执行

> 🎯 **关键认知**：模型"决定"调用工具，靠的是 **description 写得好不好**。description 模糊 → 选错工具；description 清晰 → 选得准。这就是为什么 L04 会专门讲工具设计。

这也解释了一个现象：**模型偶尔会选错工具、传错参数**——因为它不是真的懂，只是模式匹配。所以你的代码必须做好错误处理。

---

## 2. tools 定义：JSON Schema 格式

L01 你见过 `TOOLS` 这个列表。每个工具的完整结构：

```python
{
    "type": "function",          # 目前只支持 function 类型
    "function": {
        "name": "get_weather",   # 函数名（英文，模型用它调用）
        "description": "查询指定城市的天气。当用户问'XX天气''下雨吗'时使用。",
                       # ↑ 最关键！模型靠这个判断该不该用这个工具
        "parameters": {          # 参数定义（JSON Schema 格式）
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名，如'北京'、'上海'"
                },
                "unit": {
                    "type": "string",
                    "enum": ["摄氏度", "华氏度"],  # enum 限制取值范围
                    "description": "温度单位，默认摄氏度"
                }
            },
            "required": ["city"]  # 必填参数
        }
    }
}
```

### 三个关键字段

| 字段 | 作用 | 写不好会怎样 |
|------|------|-------------|
| **name** | 模型调用的函数名 | 必须和代码里的函数名一致 |
| **description** | 告诉模型"这工具干嘛的、什么时候用" | 写得模糊，模型会选错或不选 |
| **parameters** | 告诉模型"需要什么参数、什么类型" | 写得不清楚，模型传错参数 |

> 💡 **description 是 function calling 的灵魂**。它就是工具的"广告语"——模型根据广告语判断该不该用这个工具。L04 会深入讲怎么写好 description。

---

## 3. tool_choice：控制模型用不用工具

`tool_choice` 用来控制模型如何选择工具，但**具体支持哪些值取决于模型服务商**。一些兼容 OpenAI 协议的服务支持以下三种策略：

| 值 | 含义 | 适用场景 |
|----|------|---------|
| `"auto"` | 模型自主决定（默认） | 大多数情况，让模型自己判断 |
| `"none"` | 禁止调用工具 | 强制模型直接回答，不借助工具 |
| `{"type": "function", "function": {"name": "xxx"}}` | 强制调用指定工具 | 测试、或确定必须用某工具时 |

本课程使用的智谱接口目前**默认且仅支持 `"auto"`**，不能把 `"none"` 或指定函数对象传给接口。以服务商的官方文档为准：[智谱工具调用文档](https://docs.bigmodel.cn/cn/guide/capabilities/function-calling)。

```python
# 智谱支持：让模型自己决定是否调用工具
client.chat.completions.create(..., tools=TOOLS, tool_choice="auto")

# 不允许调用工具：不要向模型提供 tools
client.chat.completions.create(..., messages=messages)

# 业务流程确定必须执行某个工具时，由应用层直接调度
result = execute_function("get_weather", {"city": "北京"})
```

> ⚠️ 应用层直接调度不是 function calling：参数由程序提供，模型没有参与工具选择。如果必须让模型生成参数并强制指定函数，需要改用明确支持 named tool choice 的模型服务。

---

## 4. 参数解析：模型给的参数能用吗？

模型调用工具时，参数是以 **JSON 字符串**形式返回的：

```python
tool_call.function.arguments  # 这是一个字符串，如 '{"city": "北京", "unit": "摄氏度"}'
```

你需要 `json.loads()` 解析成字典。但这里有一堆可能出错的情况：

| 问题 | 例子 | 怎么办 |
|------|------|--------|
| 参数缺失 | 必填的 city 没给 | 工具内部给默认值或报错提示 |
| 类型不对 | 要数字给了字符串 "abc" | try/except 兜底 |
| 多余参数 | 给了不需要的 foo=1 | 忽略（只取需要的）|
| JSON 格式错 | 模型偶尔输出非法 JSON | try/except，给模型反馈让它重试 |

**生产级 Agent 必须处理这些**。否则一个参数错误就会让整个 Agent 崩溃。

---

## 5. 错误处理：让 Agent 健壮起来

L01 的代码是最简版，没怎么做错误处理。真实场景里，工具可能：
- 执行失败（比如查天气但网络断了）
- 参数无效（比如除以 0）
- 超时（工具卡住）

好的处理方式：**把错误信息当"观察结果"喂回给模型**，让模型自己决定怎么办（换个参数重试？换工具？告诉用户做不到？）。

```python
def execute_function(name, args):
    try:
        result = TOOLS_REGISTRY[name](**args)
    except Exception as e:
        result = f"工具执行失败：{e}"  # 把错误当结果返回
    return str(result)
```

这比直接崩溃好得多——模型看到"失败了"，可以调整策略重试或如实告诉用户。

---

## 6. 本课代码会做什么

`code.py` 实现一个**比 L01 更健壮、更通用的 Agent**：

### ① 通用工具调度器
用一个 `TOOL_REGISTRY`（字典）注册所有工具，`execute_function` 自动从注册表查找并调用。加新工具只需注册，不用改调度逻辑（**开闭原则**）。

### ② 4 个工具 + 参数解析 + 错误兜底
- `get_weather`（天气，模拟数据，演示带参数的工具）
- `calculator`（计算器，演示错误兜底——除以 0、非法表达式）
- `string_length`（字符串长度，演示参数类型）
- `random_choice`（随机选择，演示 list 参数）

### ③ 三个实验
- 实验 1：正常调用，看工具调度器怎么分发
- 实验 2：故意触发错误（除以 0），看错误怎么被优雅处理并喂回模型
- 实验 3：多轮调用（一个任务需要多个工具配合）

### ④ 理解 tool_choice 的能力边界
示例按照智谱接口的能力使用 `tool_choice="auto"`。禁用工具时不传 `tools`；智谱不支持强制指定某个函数。

---

## 7. 跑起来

```bash
python agent-lessons/02_function_calling/code.py
```

终端会打印三个实验。重点看实验 2（错误处理）——工具失败时，Agent 不会崩溃，而是看到错误信息后调整策略。

---

下一课 [L03 — ReAct 循环](../03_react_loop/) 是**面试核心考点**：手写 Thought→Action→Observation 循环。
