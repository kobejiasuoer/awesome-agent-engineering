# Lesson 06 — CodeAct 手写：代码是最通用的工具

> 本课目标：**理解「让 Agent 写代码执行」为什么比「调预定义工具」强，手写最小 CodeAct loop + 进程级沙箱（subprocess + 超时 + import 白名单 + 输出截断），演示一个工具调用做不动、代码一次搞定的任务。**

学完你能回答：**「Code Agent 怎么回事？为什么写代码比调工具强？」**——代码是行动空间不是又一个工具，组合与循环免费获得。

---

## 0. 从"点菜"到"进厨房"

### 工具调用 = 从菜单点菜

LangChain function calling：你预定义了一组工具（`search`、`calculate`、`send_email`），Agent 从中选一个调用。就像去餐厅**从菜单点菜**——能点什么取决于菜单上有什么。

```
Agent: 我要算 20 条数据的年份分组统计
工具菜单: search / calculate / send_email
Agent: calculate(数据) → 只能算一个表达式，不能分组循环
       🚫 做不到——calculate 不是为分组统计设计的
```

### CodeAct = 进厨房自己做

CodeAct（Wang et al. 2024）：Agent 直接写 Python 代码，沙箱执行，结果回注。就像**进厨房自己做**——只要食材（标准库）够，想做什么做什么。

```
Agent: 我要算 20 条数据的年份分组统计
CodeAct: 
  from collections import Counter
  years = [extract_year(d) for d in data]
  stats = Counter(years)
  for y, c in sorted(stats.items()): print(f"{y}: {'█'*c} {c}")
  → ✅ 一次搞定——循环、分组、统计、可视化全在代码里
```

> 🎯 **核心认知**：代码是**行动空间（action space）**不是又一个工具。工具是"预定义的动作"，代码是"任意可组合的动作"。写代码意味着 Agent 获得了循环、条件、中间变量、函数组合——这些在工具调用里要每个都单独定义。

> **论文**：CodeAct: Execute Code Actions to Enhance LLM Agents（Wang et al. 2024, [arXiv:2402.01030](https://arxiv.org/abs/2402.01030)）

**一句话说它证明了什么**：用代码作为 Agent 的行动空间（而非 JSON 工具调用），在多个 benchmark 上成功率更高——因为代码天然支持组合、循环、中间状态，而 JSON 工具调用每次都是独立的无状态请求。

---

## 1. 流派对比

**问题**：Agent 怎么执行复杂计算/数据处理？

| 流派 | 做法 | 取舍 |
|---|---|---|
| ① JSON function calling | 预定义工具，Agent 选一个调 | ✅ 安全可控；🚫 组合弱、每个新需求要加工具 |
| ② CodeAct（本课选它） | Agent 写代码，沙箱执行 | ✅ 强、组合/循环免费；🚫 需沙箱、安全风险 |
| ③ 混合 | 复杂计算走代码，外部副作用走工具 | ✅ 各取所长；🚫 两套机制 |

**选 ②+③ 的理由**：研究助手需要"数值对比、去重统计、表格生成"这类计算——这些用预定义工具做不动（每个都要新工具），用代码一次搞定。但"联网搜索""发邮件"这类有外部副作用的还是走工具（L07 的混合模式）。本课先手写 CodeAct loop + 沙箱，L07 落地时和现有工具混合。

### 沙箱层级

| 层级 | 做法 | 安全性 | 成本 | 适用 |
|---|---|---|---|---|
| 进程级（本课） | subprocess + 超时 + import 白名单 | ⚠️ 中（同 OS 用户） | 低 | 教学够用 |
| 容器级 | Docker 容器隔离 | ✅ 高 | 中 | 生产推荐 |
| 微 VM | Firecracker 等轻量 VM | ✅✅ 很高 | 高 | 高安全场景 |

> ⚠️ **诚实标注**：本课用进程级沙箱（subprocess + 白名单），**教学够用但生产不够**。进程级沙箱仍是同一 OS 用户权限——恶意代码可能通过未覆盖的攻击面逃逸。生产环境要上容器隔离（Docker）或微 VM。本课的白名单覆盖了主要危险 import，但不保证 100% 安全。

---

## 2. 手写沙箱

### 安全设计：四道防线

```
┌─────────────────── 进程级沙箱 ───────────────────┐
│                                                   │
│  ① import 白名单：只允许安全标准库                 │
│     ✅ json/statistics/collections/math/re        │
│     🚫 os/sys/subprocess/socket/urllib/open      │
│                                                   │
│  ② 超时杀进程：subprocess timeout                 │
│     超时 → kill → 返回"超时"提示                  │
│                                                   │
│  ③ 输出截断：防止内存爆炸                         │
│     stdout 超过 N 字符只保留前 N                   │
│                                                   │
│  ④ 无网络无文件：白名单不放网络/文件库             │
│     （进程级做不到完全隔离，但白名单堵主要风险）    │
│                                                   │
└───────────────────────────────────────────────────┘
```

### 白名单 vs 黑名单

```python
# 白名单（本课选它）：只允许安全的，其余全拒
ALLOWED_IMPORTS = {"json", "statistics", "collections", "math", "re", "datetime", "itertools"}
# 检查代码里所有 import，不在白名单里的拒绝执行

# 黑名单（不选）：拒绝危险的，其余放行
BLOCKED_IMPORTS = {"os", "sys", "subprocess", "socket"}
# 问题：漏掉一个危险库就完蛋（如 ctypes、multiprocessing）
```

> 🎯 **白名单比黑名单安全**：白名单默认拒绝，只有明确安全的才放行；黑名单默认放行，漏一个就完蛋。安全设计永远选白名单。

### import 检测

```python
def check_imports(code: str) -> list[str]:
    """提取代码里的 import，返回不在白名单里的。"""
    violations = []
    for line in code.split("\n"):
        line = line.strip()
        if line.startswith("import "):
            mod = line.split()[1].split(".")[0]
            if mod not in ALLOWED_IMPORTS:
                violations.append(mod)
        elif line.startswith("from "):
            mod = line.split()[1].split(".")[0]
            if mod not in ALLOWED_IMPORTS:
                violations.append(mod)
    return violations
```

---

## 3. 手写 CodeAct loop

### 核心流程

```python
def codeact_loop(task, llm, max_rounds=3):
    history = ""
    for round in range(max_rounds):
        # 1. LLM 生成代码（基于任务 + 历史结果）
        code = llm.generate_code(task, history)
        # 2. 沙箱检查 import
        violations = check_imports(code)
        if violations:
            history += f"代码被拒：import {violations} 不在白名单\n"
            continue
        # 3. 沙箱执行
        result = sandbox_exec(code, timeout=10)
        # 4. 结果回注
        history += f"代码：\n{code}\n结果：\n{result}\n"
        # 5. LLM 判断是否完成
        if llm.is_done(result, task):
            return result
    return history
```

### Mock LLM 设计

code.py 用 Mock LLM 演示：
- 给定任务，生成预设的 Python 代码（如分组统计 + ASCII 柱状图）
- 演示越权 import 被拒（`import os` → 拒绝）
- 演示超时被杀（`while True` → 超时）

### 对比实验

```
任务：对 20 条搜索结果按年份分组统计并画 ASCII 柱状图

工具调用方式：
  calculate(数据) → 只能算一个表达式，不能分组循环
  🚫 做不到——需要预定义一个"分组统计"工具

CodeAct 方式：
  from collections import Counter
  data = [...]  # 20 条
  years = [...]
  stats = Counter(years)
  for y, c in sorted(stats.items()): print(f"{y}: {'█'*c} {c}")
  → ✅ 一次搞定
```

---

## 4. 安全红线演示

code.py 演示三道安全防线的拦截：

```
① import os → 🚫 拒绝（不在白名单）
② import socket → 🚫 拒绝
③ while True: pass → ⏱ 超时杀进程
④ from collections import Counter → ✅ 允许
⑤ print("hello") → ✅ 正常执行
```

---

## 5. 落地清单

本课是**纯手写原理课，无落地改动**（不改 research-assistant 任何文件）。落地在 L07（代码解释器接入）。

### 如何验证

```bash
cd frontier-lessons/06_codeact
PYTHONIOENCODING=utf-8 ../../.venv/Scripts/python.exe code.py
# 预期：
# - 演示 CodeAct loop（生成代码→沙箱检查→执行→回注）
# - 拦截越权 import（os/socket 被拒）
# - 超时杀进程（while True 被杀）
# - 统计任务跑通（分组 + ASCII 柱状图）
```

---

## 6. 本课在两条主线上的位置

- **评估主线**：本课引入了"代码执行成功率"和"沙箱安全拦截率"两个可量化点——代码能不能跑通、越权尝试能不能拦住。L08 的 TrajectoryEvaluator 会把它们纳入指标。
- **上下文工程主线**：CodeAct 是上下文工程的**动态生成**——不是从外部调回信息（记忆/RAG/skills），是让 Agent 生成代码、执行、把结果放进上下文。这扩展了上下文工程的边界：上下文不只是"调回已有信息"，还能"生成新信息"（计算结果）。

---

## 🎯 面试话术

> 「CodeAct 我手写过 loop 和沙箱。核心认知：代码是行动空间不是又一个工具——组合与循环免费获得，不用每个新需求都加工具。沙箱我用进程级：subprocess + 超时 + import 白名单 + 输出截断，四道防线。白名单比黑名单安全——默认拒绝只有明确安全的放行。我也清楚进程级沙箱的边界：同 OS 用户权限，生产要上容器隔离。我的研究助手数值结论不靠 LLM 口算，路由到沙箱代码解释器。」
