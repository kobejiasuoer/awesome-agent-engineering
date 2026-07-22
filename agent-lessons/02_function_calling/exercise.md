# L02 练习

> 改 `code.py` 里的代码，运行 `python agent-lessons/02_function_calling/code.py` 观察变化。

---

## 练习 1：给工具调度器加一个新工具（热身）
实现一个 `get_day_of_week` 工具（返回今天星期几），完整地加进来：

```python
# 1. 实现函数
def get_day_of_week() -> str:
    days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return f"今天是{days[datetime.now().weekday()]}"

# 2. 注册到 TOOL_REGISTRY
TOOL_REGISTRY["get_day_of_week"] = get_day_of_week

# 3. 加到 TOOLS_SPEC
{"type": "function", "function": {"name": "get_day_of_week", "description": "...", "parameters": {...}}}
```

**观察重点**：因为你用了注册表设计，加新工具**不用改 `execute_function`**。这就是"开闭原则"的好处——对扩展开放，对修改封闭。

问 Agent `"今天是星期几？"`，看它能不能正确调用新工具。

---

## 练习 2：测试错误兜底的健壮性
故意制造几种错误，看 Agent 怎么处理：

```python
# 在 main() 里加这些测试
run_agent(client, "帮我算一下 abcdefg")          # 非法表达式
run_agent(client, "帮我查一下火星的天气")           # 不支持的城市
run_agent(client, "帮我从一个空列表里随机选")        # 空列表
```

**观察**：Agent 崩溃了吗？还是优雅地把错误信息反馈给模型，模型再如实告诉用户？

**思考**：对比"直接报错崩溃"和"把错误喂回模型让它应对"——后者为什么是更好的设计？（提示：模型看到"火星没有数据"后，可以建议用户换个城市，而不是整个程序挂掉）

---

## 练习 3：理解 tool_choice 的平台差异

本课程使用的智谱接口目前仅支持 `tool_choice="auto"`。不要把 `"none"` 或指定函数对象传给接口；下面分别从模型层和应用层观察工具控制的差异。

先运行现有代码，让模型自主决定是否调用工具：

```python
# auto：智谱支持的工具选择策略
run_agent(client, "现在北京天气怎么样")
```

然后给 `run_agent` 增加一个 `enable_tools` 参数。当它为 `False` 时，不向请求传递 `tools` 和 `tool_choice`：

```python
request = {"model": CHAT_MODEL, "messages": messages}
if enable_tools:
    request.update(tools=TOOLS_SPEC, tool_choice="auto")
response = client.chat.completions.create(**request)

run_agent(client, "现在北京天气怎么样", enable_tools=False)
# → 请求没有提供工具，模型无法发起 tool_call
```

最后体验应用层直接调度：

```python
result = execute_function("get_weather", {"city": "北京"})
print(result)
```

**思考**：不传 `tools` 与应用层直接调用分别控制了什么？为什么直接调用不属于 function calling？如果业务要求“由模型生成参数，但必须调用指定函数”，应该先确认什么？

---

## 练习 4：理解参数解析的风险
看 `execute_function` 里的 `func(**arguments)`。如果模型传了一个函数不支持的参数（比如给 calculator 传了 `{"expression": "1+1", "precision": 2}`），会怎样？

试试在 TOOL_REGISTRY 里临时加一个严格的函数：

```python
def strict_add(a: int, b: int) -> str:
    return str(a + b)

TOOL_REGISTRY["strict_add"] = strict_add
```

然后问 Agent 一个可能让它传多余参数的问题，观察 `TypeError` 是不是被 `execute_function` 的 except 兜住了。

**思考**：`**arguments` 解包的机制——多余参数会触发 TypeError。这就是为什么错误兜底（except TypeError）很重要。

---

## ✅ 完成本课后，你应该能回答
1. 模型"决定"调用工具，靠的是什么？（提示：不是真懂，是 description 模式匹配）
2. tools 定义里最关键的三个字段是什么？哪个最容易写错？
3. 智谱目前支持哪种 tool_choice？如何在应用层禁用或直接调用工具？
4. 为什么要用 TOOL_REGISTRY（注册表）而不是 if/elif？（提示：开闭原则）
5. 工具执行失败时，为什么把错误信息喂回模型，比直接崩溃好？
