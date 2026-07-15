# Lesson 02 — 成本预算：轨迹级的钱包

> 本课目标：**让一次运行的 token 消耗可计量、可预算、超支可刹车**——给轨迹装一个钱包，软预算（80%）降级模型、硬预算（100%）诚实收尾，并产出分节点成本分摊表指出吞金兽。
>
> 学完你能回答面试官那句：**「你的 Agent 一次跑要花多少钱？怎么控？」**——答案是轨迹级 token 预算：实时累计、软预算降级、硬预算诚实收尾，静态选型管单价、轨迹预算管总量。

---

## 0. 起点：L00 基线里故障⑤的裸奔结局

L00 的 `baseline_chaos.json` 记录故障⑤（预算炸弹）结局是 `overspent`——**token 烧穿无刹车**。诚实数字：一个子题返回 40000 字符（≈10000 token），3 个子题就 30000 token，现状系统一路吃下不停。

```
L00 基线 · 故障⑤预算炸弹：
  总 token：70714（mock 估算）
  结局：💸 overspent（烧穿预算无刹车）
```

> 🎯 **核心认知**：Agent 的成本和请求的成本是两种东西。请求成本**事前可估**（prompt 长度已知），轨迹成本是**涌现的**（步数 × 每步消耗都不确定）。所以 ops-L12 的静态选型（选 glm-4 还是 flash）管得了单价，管不了总量——它不知道这次会跑多少步、每步吃多少 token。

---

## 1. 为什么静态选型管不了轨迹成本

### 1.1 请求成本 vs 轨迹成本

| 维度 | 请求成本（ops-L12 静态选型） | **轨迹成本（本课）** |
|---|---|---|
| 对象 | 一次 LLM 调用 | 一次 Agent 运行（N 步 × M 次调用） |
| 可估性 | 事前可估（prompt 长度已知） | **涌现的**（步数 × 每步消耗都不确定） |
| 控制手段 | 选便宜模型 / 缓存 | **运行时累计 + 预算刹车** |
| 失败模式 | 单次贵一点 | **烧穿预算**（叠加步数爆炸） |

### 1.2 现状缺口

现状 `config.py` 有 `smart_model=glm-4` / `fast_model=glm-4-flash` 的多模型路由（split/researcher 用 fast，writer/reviewer 用 smart）——这是静态选型，管单价。但**没有任何机制约束一次运行的总 token**：

- `enable_*` 开得越多，吞金兽越多（memory recall、code interpreter、browser 都要额外 LLM 调用）。
- reviewer 打回循环每多一轮，writer + reviewer 的 token 重新烧一遍。
- 一个子题返回超长文本，全部吃下不停。

---

## 2. 计量：从 usage_metadata 取真实 token

### 2.1 字段查证（实测）

> ⚠️ **诚实标注（实测）**：`ChatZhipuAI` 的响应是 langchain 的 `AIMessage`，其 `usage_metadata` 字段（实测可用）是一个 dict：`{"input_tokens": N, "output_tokens": M, "total_tokens": N+M}`。这是 token 计量的权威来源。

```python
# cost_budget.py
def extract_usage(llm_response):
    """优先取 usage_metadata，取不到按字符/4 估算。"""
    usage = getattr(llm_response, "usage_metadata", None)
    if isinstance(usage, dict) and usage:
        return {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("total_tokens", ...),
            "estimated": False,   # ← 真实计量
        }
    # 降级：字符估算，诚实标注
    est = max(1, len(str(content)) // 4)
    return {"total_tokens": est, "estimated": True}  # ← 估算
```

> 💡 为什么不直接信估算：估算（字符/4）的绝对值与真实 token 差很多（中文一个字常是 1–2 token，英文一个词常是 1 token），但**结构性结论一致**——「有无预算刹车」的差异、哪个节点是吞金兽，估算和真实都能反映。mock 测试用估算，真实运行用 `usage_metadata`，逐处标注。

### 2.2 累计进 State

```python
# state.py
token_usage: Annotated[int, add_int]   # ← 复用 L01 的 add_int reducer
cost_mode: str                          # normal / frugal / over_budget
```

每个节点调完 LLM 记一笔增量（`token_delta` 返回本次调用的 token，reducer 累加）。**增量而非累计**——因为用了 reducer，返回累计会重复计数。

---

## 3. 预算刹车：软预算降级 + 硬预算收尾

### 3.1 两级刹车

```
                    token 累计
                        │
    ┌───────────────────┼───────────────────┐
    │     normal        │    frugal         │  over_budget
    │  （未到 80%）      │  （80%~100%）      │  （≥100%）
    │                   │                   │
    │  正常跑            │  节俭模式          │  诚实收尾
    │                   │  剩余子题降级       │  （复用 L01 路径）
    │                   │  flash            │  带部分结果退出
    └───────────────────┴───────────────────┘
     0           80% × budget       100% × budget
```

**软预算（80%）**：进入「节俭模式」。后续子题的 researcher 改用 `glm-4-flash`（已是 flash，演示降级语义；若 smart 节点则降级到 fast）。这是「拿质量换成本」——自主-控制主线的体现。

**硬预算（100%）**：触发 L01 的诚实收尾路径（reviewer 检查 `should_truncate_for_cost`，超限强制 pass + truncated）。用户拿到带截断标注的部分结果，而不是继续烧。

### 3.2 与 L01 的复用关系

```python
# nodes.py（reviewer 开头）
from .step_budget import should_truncate          # L01：步数预算
from .cost_budget import should_truncate_for_cost # L02：成本预算

truncate, reason = should_truncate(state)          # 步数/循环
if not truncate:
    truncate, cost_reason = should_truncate_for_cost(state)  # 成本
    if truncate:
        reason = cost_reason
if truncate:
    return {"review_decision": "pass", "truncated": True, ...}  # 同一条诚实收尾路径
```

> 🎯 **核心认知**：L01 的诚实收尾路径是**通用基础设施**——L02 只需把「成本超限」也接进同一个判断点。这就是为什么 L01 要先做：它建立了「超预算 → 带部分结果退出」的骨架，L02/L03 的刹车都往这个骨架上接。

---

## 4. 分节点成本分摊：哪个节点是吞金兽

```python
# cost_budget.py
@dataclass
class NodeCostTracker:
    by_node: dict[str, dict]  # {node: {total_tokens, calls, estimated}}

    def report(self):
        """按 token 降序列出每个节点的消耗（吞金兽在前）。"""
        ...
```

预期分摊（从 code.py 实测）：

```
预算炸弹场景（裸奔）：
  researcher        11748 token   99.5%   ← 吞金兽（吃超长搜索结果）
  writer               30 token    0.3%
  summarize            20 token    0.2%
  split                 5 token    0.0%
```

> 💡 **为什么 researcher 是大头**：它并行跑 N 个，每个吃 web_search 的完整返回文本。预算炸弹正是从这里注入的。这个表的价值是**定位**——成本治理该从哪个节点下手（给 researcher 的搜索结果做截断/摘要）。

---

## 5. 方案对比：怎么给轨迹控成本？

| 方案 | 做法 | 取舍 |
|---|---|---|
| ① **事前静态选型**（ops-L12） | 选 glm-4 还是 flash，配多模型路由 | ✅ 管单价、零运行时成本；🚫 管不了总量，不知道这次跑多少步 |
| ② **运行时预算刹车**（本课主路线） | token 实时累计，软预算降级 / 硬预算收尾 | ✅ 管总量、能刹车、有分摊表定位吞金兽；🚫 需要每节点记账（几行） |
| ③ **预测性预算**（思考题） | 按历史轨迹估「剩余步数的预期成本」，超阈提前拒单 | ✅ 最优雅（提前拒比中途刹车好）；🚫 需要历史数据训练预测器，冷启动没数据 |

**选 ② 的理由**：方案 ① 是地基（没有它单价就贵），方案 ② 是必备（没有它总量失控）。两者叠加才是完整的成本控制。方案 ③ 是进阶（留给 exercise）。

> 💡 **紧还是松？**（自主-控制主线）：`max_budget_tokens` 设多少？判断依据是「正常路径的 token 消耗 × 安全系数」。软预算降级是「拿质量换成本」——降级到 flash 后报告质量会降，所以软预算阈值（80%）要设在「正常任务不会误触」的位置。硬预算是「宁可出部分结果也不烧穿」，阈值要对齐你的预算上限（如单次运行不超过 ¥X → 反推 token 数）。

---

## 6. 跑起来：故障⑤ before/after

### `code.py` 演示

```
💸 before：裸奔（预算炸弹）
   总 token：11803  ← 烧穿
   researcher 99.5%  ← 吞金兽

✅ after：开预算（预算炸弹）
   总 token：7837  ← 硬预算刹车（诚实收尾）
   researcher 99.9%

✅ 对照：开预算（正常）
   总 token：70  ← 成本可控，治理零税
```

**解读**：
- **before**：预算炸弹下 token 烧到 11803，无任何刹车。
- **after**：开预算后硬预算触发，诚实收尾（带部分结果退出）。
- **对照**：正常跑（无炸弹）成本只有 70 token——证明**治理零税**（开关开但无故障时成本不劣化）。

```bash
cd portfolio-projects/research-assistant
python ../../agent-ops-lessons/02_cost_budget/code.py
```

---

## 7. 落地清单

| 文件 | 改动 | 如何验证 |
|---|---|---|
| `src/research_assistant/cost_budget.py` | **新增**：`extract_usage`/`NodeCostTracker`/`token_delta`/`should_truncate_for_cost`/`pick_model_for_mode` | `pytest tests/test_cost_budget.py -q` |
| `src/research_assistant/state.py` | **新增**：`token_usage`(add_int) / `cost_mode` 字段 | import 不报错 |
| `src/research_assistant/config.py` | **新增**：`enable_cost_budget`/`max_budget_tokens`（默认关） | 改 `.env` |
| `src/research_assistant/nodes.py` | split/researcher/summarize 加 `_record_call`；writer/reviewer 加 `_token_delta`；reviewer 接 `should_truncate_for_cost` | 见下 |
| `src/research_assistant/service.py` + `cli.py` | `_initial_state` 加 token 字段；invoke/stream 开头 `reset_tracker()` | 跑 cli 不报错 |
| `tests/test_cost_budget.py` | **新增**：17 个测试 | `pytest tests/test_cost_budget.py -q` |

### 验收

```bash
cd portfolio-projects/research-assistant

# 1. 全部测试绿（139 + 17 = 156）
python -m pytest -q
# 预期：156 passed

# 2. 开关关时行为 = 现状
python -m pytest tests/test_graph.py tests/test_nodes.py tests/test_step_budget.py -q
# 预期：全绿

# 3. 开成本预算后硬预算触发
python -c "
from research_assistant import config
config.settings.__dict__['enable_cost_budget'] = True
config.settings.__dict__['max_budget_tokens'] = 100
from research_assistant.cost_budget import should_truncate_for_cost
print(should_truncate_for_cost({'token_usage': 150}))
"
# 预期：(True, '成本预算超限（150/100 token）')
```

---

## 8. 本课在两条主线上的位置

- **爆炸半径主线**：把「成本超支」的爆炸半径从**无界**（烧到多少都不停）压到**有界**（max_budget_tokens 内必刹车，软预算降级 + 硬预算收尾两级保护）。
- **自主-控制主线**：软预算是「拿质量换成本」（降级 flash），硬预算是「宁可部分结果也不烧穿」。两级的阈值判断依据是「正常路径消耗 × 安全系数」——太紧误杀正常任务，太松等于没设。

---

## 🎯 面试话术

> 「我的 Agent 每次运行带一个钱包：token 从 `usage_metadata` 实时累计进 State（取不到按字符/4 估算并诚实标注）。软预算（80%）进节俭模式降级 flash，硬预算（100%）触发诚实收尾——复用我 L01 建的『超预算带部分结果退出』路径，成本刹车只是往这个判断点接了一个新条件。
>
> 分节点成本分摊表能指出吞金兽——预期 researcher×N 并行是大头，因为每个吃 web_search 的完整返回。成本治理该从哪个节点下手，看这张表就知道。
>
> 静态选型管单价（ops-L12 那套），轨迹预算管总量（本课）——两层都要。Agent 成本是涌现的，步数 × 每步消耗都不确定，没有运行时刹车就会烧穿。」
