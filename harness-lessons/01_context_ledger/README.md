# Lesson 01 — 上下文账本：先量出来才管得住

> 本课目标：**给每次 LLM 调用装一个「窗口记账器」——prompt 拆四桶计量（system/task_state/tool_results/history）、水位三区（safe/caution/danger）、可注入 tokenizer。窗口管理第一步是记账不是压缩：不知道钱花哪了，就谈不上省。**

---

## 1. 可注入 tokenizer：本课程的命根子

课程十的命根子是可注入时钟——任何「时间到了没」的判断走 `clock.now()`，FakeClock 一行 `advance()` 快进 5 天。本课程的命根子与它**严格同构**：任何「窗口够不够」的判断走注入的 `Tokenizer.count()` + `window_limit_tokens`。

| | 课程十（时间） | 本课程（空间） |
|---|---|---|
| 被注入的判断 | 到点了没 / 缺勤了没 | 装得下吗 / 到水位了吗 |
| 生产实现 | `time.time()` | 真 tokenizer / usage 回执 |
| 测试实现 | `FakeClock`（拨表） | `FakeTokenizer`（len//4） |
| 不注入的下场 | 测 5 天要真等 5 天 | 数字随模型/版本漂移，CI 不可复现 |

`FakeTokenizer` 用 `len(text)//4`——**与 cost_budget 的字符估算同口径**（仓库既有约定），对中文偏保守。诚实标注：绝对数字非真实 tokenizer；占比、水位、越限点这些**结构性结论**不受影响。真实对账走 API usage 回执（`cost_budget.extract_usage` 已有），L09 可选真模型章做校准。

## 2. 四桶口径：把 prompt 拆开看

```
system        常驻身份/规程/红线（每次调用全额付租）
task_state    本轮指令与任务态（目录、计划、当前指令、加载的 skill）
tool_results  工具带回的外部材料（搜索返回、信源全文、命令输出）
history       过往轮次的产出（findings/summary/report 等 LLM 生成物、旧笔记）
```

桶边界宣言（RA 集成的归桶规则，测试锁死）：**检索材料 → tool_results；LLM 自己生成过的东西（findings/summary/report/记忆命中）→ history；指令模板与 skill 正文 → task_state**。v4 是单串 prompt 调用（无独立 system 消息），所以 RA 集成里 system 桶常为 0——长程单窗形态（L00 裸基线）里它才是常驻大头。归桶不是精确科学，是**统一口径**：口径一致，跨调用、跨配置的占比才可比。

两笔账的分工（与 agent-ops L02 的边界）：

| | cost_budget（钱） | context_ledger（空间） |
|---|---|---|
| 问题 | 这次运行**烧了**多少 token | 这次调用窗口里**装了**什么 |
| 记账时机 | 调用**后**（从响应取 usage） | 调用**前**（从 prompt 拆桶） |
| 失控形态 | 账单爆炸 | 400 拒绝 / 截断失忆 / 迷航 |
| 刹车 | 软预算降级 / 硬预算收尾 | 水位触发压缩与外置（L02+） |

## 3. 水位三区：「最后 20% 不干大事」的量化版

| 区 | 占比 | 行为约定 |
|---|---|---|
| safe | < 60% | 放心干活 |
| caution | 60%–85% | 该压缩/外置了（**L02 的触发区**） |
| danger | > 85% | 只做收尾，不开新工作 |
| over | > 100% | 越限（真实 API 会 400；enforce 模式模拟它） |

为什么在 caution 就动手、不等 danger：压缩本身要花窗口和钱（摘要调用），太早=浪费摘要成本，太晚=一次大压丢更多、且 danger 区已经没有余量容纳「压缩过程」本身。60/85 是课程约定的起点，不是真理——练习 2 让你扫参数找自己的阈值。

账本跑长途任务的实测（`python code.py` Part 3）：长程裸奔**第 5 源就进 caution**（5,065/8,000）——L00 说它死于 S11，本课的账本说它从 S05 就开始病了。死亡是急性的，水位是慢性的：**账本的价值是把急性死亡提前成慢性告警**。

## 4. 份额思维：并行子调用的窗口预算

Send 并行的 N 个 researcher 各有自己的调用窗口——账本按调用记账，天然覆盖。份额思维是：给每类调用设计窗口份额（researcher 单源 ≤ X、summarize ≤ Y），**超份额是上游设计问题**（该整形/该外置），不是下游执行问题（换更大模型硬扛）。L05 子代理的「窗口份额」（subagent_window_tokens）就是这个思想的落地。

## 5. 流派对比：窗口计量的四条路线

| 流派 | 思路 | 取舍 |
|---|---|---|
| 不记账 | 等 API 报错再说 | 免费；但错误即事故，且截断失忆根本不报错 |
| **注入式字符近似** | len//4，调用前算 | **本课选择**：确定、零依赖、CI 友好；绝对值有偏差 |
| 真 tokenizer 精确 | tiktoken 等本地模型分词 | 精确；慢、模型绑定、引重依赖（违反零新增依赖约束） |
| usage 回执 | 从 API 响应读实际 token | 完全精确；**事后**才知道——防不了 400 |

本课选「注入近似 + 回执校准挂钩」：近似做**事前预算**（调用前判水位），回执做**事后校准**（cost_budget 已有），两者对账即可持续修正 `len//4` 的系数——这与「估算的绝对数字不同、结构性结论一致」的仓库诚实传统完全一致。

## 6. 跑起来

```bash
cd harness-lessons/01_context_ledger
python code.py     # 四部演示：注入性 → 三区 → 长途记账 → RA 主链路开/关
```

RA 主链路集成实测（FakeLLM + mock 搜索，六次调用）：

```
窗口账本：6 次调用，峰值 552/8000（safe），越限 0 次
  system               0 token    0.0%
  task_state          88 token    6.1%
  tool_results      1080 token   74.7%
  history            277 token   19.2%
```

→ **tool_results 占 75%**：治理顺序从此有账可查——先控源（L04 整形），再止损（L02 压缩），能外置的外置（L05/L06）。关掉开关重跑：账本为 `None`，一条记录都不产生（纯测量不拦截、默认零介入）。

## 7. 落地清单

| 文件 | 改动 |
|---|---|
| `src/research_assistant/context_ledger.py` | 新增：Tokenizer 协议 + FakeTokenizer（规范住所）+ zone 三区 + WindowLedger + ContextOverflowError + 模块级单例（对齐 cost_budget tracker 模式） |
| `src/research_assistant/nodes.py` | 五节点六调用点挂 `_ledger_measure`（开关守卫；prompt 拼接逐字节不变） |
| `src/research_assistant/config.py` | `enable_context_ledger`（默认 off）、`window_limit_tokens=8000` |
| `eval_agent/long_haul.py` | FakeTokenizer 改为从 context_ledger 复用（eval 与主链路同一把尺子） |
| `tests/test_context_ledger.py` | 新增 13 测试（算术/账本/集成/零介入） |

### 验收

```bash
cd portfolio-projects/research-assistant
python -m pytest tests/test_context_ledger.py -q   # 13 passed
python -m pytest -q                                 # 358 passed（345 + 13）
cd ../../harness-lessons/01_context_ledger && python code.py
```

## 8. 本课在两条主线上的位置

**窗口经济**：账本是空间预算的记账器——量租金是砍租金的前提，水位三区把「什么时候该动手」变成可测阈值。**外置化**：账本自己不外置任何东西，但它指认了该外置谁——四桶占比就是外置优先级表。

## 🎯 面试话术

> 「窗口管理第一步是记账不是压缩。我给每次 LLM 调用装了四桶账本——system/任务态/工具结果/历史，调用前计量、水位三区告警。token 数是依赖注入的：测试用 len//4 假 tokenizer 保证确定性，生产用 usage 回执事后校准，两者对账修正系数。账本给了我两个改变决策的数字：长程任务第 5 源就进 60% 警戒区（死亡是急性的，水位是慢性的），工具结果占窗口 75%（所以治理顺序是先整形控源、再压缩止损）。」
