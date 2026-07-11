# Lesson 07 — 落地：研究助手的代码解释器

> 本课目标：**给 research-assistant 加 code interpreter 工具（复用 L06 沙箱），让"需要对比数据时能写代码算"，报告附录附执行过的代码（可复算性——研究报告的可信度升级）。**

学完你能回答：**「你的研究助手数字怎么来的？可信吗？」**——数值结论不靠 LLM 口算，路由到沙箱代码计算，报告附可复算脚本。

---

## 0. 起点：L06 的沙箱落地到项目

L06 手写了 CodeAct loop + 进程级沙箱（subprocess + 超时 + import 白名单 + 输出截断）。本课把它**落地到 research-assistant**：

- 新增 `code_interpreter.py`：封装沙箱执行 + 路由判断 + 代码历史记录
- writer 节点接入：涉及数值对比/统计时，生成代码→沙箱执行→结果附报告
- 报告附录：附执行过的代码（可复算性）

---

## 1. 什么研究步骤该走代码？

### 路由判断

| 走代码 ✅ | 走 LLM 直出 ✅ |
|---|---|
| 数值对比（X vs Y 的数据差异） | 观点综述（多方看法汇总） |
| 去重统计（20 条结果里有几个唯一来源） | 语言组织（报告的结构和表述） |
| 表格生成（结构化对比表） | 判断推理（采信 A 还是 B） |
| 占比计算（X 占总数的百分比） | 创意生成（标题、摘要措辞） |

**判断信号**（简化版关键词匹配）：摘要含"对比/统计/计算/分组/排序/数量/占比/分布"→ 走代码。

> 生产可换 LLM 判断（"这个研究步骤需要写代码吗"），本课用关键词够演示。

### 为什么不全部走代码？

- LLM 直出更快（代码执行有 subprocess 开销）
- 观点/语言类任务代码做不了（代码不能"写一段综述"）
- 代码适合**精确计算**，LLM 适合**模糊生成**

---

## 2. 可复算性：报告的可信度升级

### 一般 AI 写的报告

```
MCP 生态在 2024 年快速增长，工具数量增加了约 60%。
```

> 🚫 这个"60%"哪来的？LLM 口算的。不可验证、不可复算。可能是幻觉。

### 有代码解释器的报告

```
MCP 生态在 2024 年快速增长，工具数量增加了约 60%。

📊 代码计算结果：
```
2023年: 15 个工具
2024年: 24 个工具
增长率: 60.0%
```

## 附录：代码执行记录（可复算）
### 脚本 1
```python
data = {"2023": 15, "2024": 24}
growth = (data["2024"] - data["2023"]) / data["2023"] * 100
print(f"增长率: {growth:.1f}%")
```
```

> ✅ 这个"60%"可复算——读者拿脚本跑一遍就能验证。数字可信度和"AI 写的报告"不是一个档次。

> 🎯 **核心认知**：研究报告的可信度不取决于"写得像不像真的"，取决于"数字能不能复算"。代码解释器让每个数值结论都有脚本支撑——这是"AI 辅助研究"和"AI 编故事"的分界线。

---

## 3. 流派对比（延续 L06）

**问题**：研究助手的数值计算怎么实现？

| 流派 | 做法 | 取舍 |
|---|---|---|
| ① LLM 口算 | 让 LLM 直接在文本里算 | ✅ 零成本；🚫 不可靠（LLM 算术幻觉）、不可复算 |
| ② 预定义计算工具 | 给 Agent 一个 calculate 工具 | ✅ 可控；🚫 只能算简单表达式，分组/统计做不了 |
| ③ 代码解释器（本课选它） | 沙箱执行 Agent 生成的代码 | ✅ 任意计算、可复算；🚫 需沙箱、有开销 |

**选 ③ 的理由**：研究助手需要分组统计、占比计算、对比表——这些用预定义工具做不动（每个要新工具），用 LLM 口算不可靠。代码解释器一次解决且可复算。

---

## 4. 落地实现

### code_interpreter.py

```python
def execute_code(code) -> CodeResult:
    # ① import 白名单检查
    # ② subprocess + 超时执行
    # ③ 输出截断
    # 返回 CodeResult(success, output, code, error)

def should_use_code(summary) -> bool:
    # 关键词路由：含"对比/统计/计算"→ True

def run_code_for_research(code) -> CodeResult:
    # 执行 + 记录历史（附报告用）

def format_code_appendix() -> str:
    # 把执行过的代码格式化成报告附录
```

### writer 接入

```python
if settings.enable_code_interpreter:
    if should_use_code(summary):
        code = smart_llm.invoke("生成分析代码...")  # LLM 生成代码
        result = run_code_for_research(code)        # 沙箱执行
        if result.success:
            report += f"📊 代码计算结果：\n{result.output}"
        report += format_code_appendix()             # 附可复算脚本
```

### 白名单（比 L06 更窄）

研究场景只需计算库，不需要文件/网络：

```python
ALLOWED_IMPORTS = {"json", "statistics", "collections", "math", "re",
                   "datetime", "itertools", "functools", "string"}
# 不含：os/sys/socket/subprocess/urllib/open/pathlib
```

---

## 5. 落地清单

### 改了哪些文件

| 文件 | 改动 | 说明 |
|---|---|---|
| `src/research_assistant/code_interpreter.py` | **新增** | 沙箱执行 + 路由 + 代码历史 + 附录格式化 |
| `src/research_assistant/config.py` | 加 `enable_code_interpreter` | 默认关 |
| `src/research_assistant/nodes.py` | writer 接入代码解释器 | 涉及计算时生成代码→执行→附报告 |
| `src/research_assistant/service.py` | 每次研究前重置代码历史 | |
| `tests/test_code_interpreter.py` | **新增** 15 个测试 | 白名单/执行/超时/截断/路由/附录 |

### 如何验证

```bash
cd portfolio-projects/research-assistant

# 1. 全量测试（62 原有 + 15 新增 = 77 全绿）
.venv/Scripts/python.exe -m pytest tests/ -q
# 预期：77 passed

# 2. 单独跑代码解释器测试
.venv/Scripts/python.exe -m pytest tests/test_code_interpreter.py -v
# 预期：15 passed（含越权拦截/超时/正常执行/附录）

# 3. 演示
cd ../../frontier-lessons/07_code_interpreter
PYTHONIOENCODING=utf-8 ../../.venv/Scripts/python.exe code.py
# 预期：研究摘要→路由判断→生成代码→沙箱执行→报告附脚本

# 4. 真实跑（需 ENABLE_CODE_INTERPRETER=true + API key）
# 跑一个涉及"对比发布节奏"的主题
# 报告里应出现代码计算结果 + 附录脚本
```

---

## 6. 本课在两条主线上的位置

- **评估主线**：本课引入了"代码执行成功率"和"数值复算率"（报告里的数字有多少附了脚本）两个指标。L08 的 TrajectoryEvaluator 会量化——开了 code interpreter 后报告的可复算性提升多少。
- **上下文工程主线**：代码解释器是上下文工程的**信息生成**——不是调回已有信息，是让 Agent 生成代码执行，把计算结果放进上下文。这和 L03 的 skills 配合：skills 规定"数字要可复算"（格式规范），code interpreter 实现"数字确实可复算"（执行脚本）。

---

## 🎯 面试话术

> 「我的研究助手数值结论不靠 LLM 口算——writer 写报告时如果涉及对比/统计，路由到沙箱代码解释器：LLM 生成代码、subprocess + import 白名单 + 超时执行、结果附报告附录。每个数字都有脚本支撑，读者可复算。沙箱白名单只放 json/statistics/collections 等纯计算库，网络文件全禁。数字可信度和一般'AI 写的报告'不是一个档次——一般报告的 60% 是口算的可能是幻觉，我的 60% 附了脚本，跑一遍就能验证。」
