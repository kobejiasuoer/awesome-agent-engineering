# Lesson 09 — 毕业整合：Deep Research Agent v3 + 课程九注册

> 本课目标：**全机制协同跑通混沌任务，v3 定稿与全仓收尾**。一条命令跑全程：七机制协同 + 混沌收益矩阵定稿（对照 L00）+ 纯净跑零税；research-assistant README 加 v3 章节；根 README（中英）注册课程九。
>
> 学完你能回答面试官那句：**「你的研究智能体经历了哪些演进？生产可靠性怎么证明？」**——答案是三个版本：能跑的 v1 → 有记忆能反思会写代码的 Deep Research v2 → 生产可靠的 v3。v3 的七机制全部默认关、可降级，收益有混沌矩阵和 SLO 卡背书。

---

## 0. 全课程回顾：从裸奔到生产可靠

```
L00 量出五种失控的无界半径（baseline_chaos.json）
  ↓
L01-L03 模块 A 失控治理：步数/成本/熔断（循环/超支/故障扩散 有界）
  ↓
L04-L05 模块 B 危险动作：幂等/审批（副作用 有界）
  ↓
L06-L07 模块 C 恢复与观测：续跑/体检（崩溃重做量 有界 + 可见性）
  ↓
L08 评估：混沌收益矩阵（33%→100%）+ SLO 卡
  ↓
L09 毕业整合：v3 定稿 + 全仓注册
```

---

## 1. 七机制协同（治理架构在双层图上的位置）

| 机制 | 课程 | 位置 | 兜住的故障 |
|------|------|------|-----------|
| 📏 全局步数预算 + 循环检测 | L01 | reviewer 开头 | ③ 死循环 |
| 💰 轨迹级成本预算 | L02 | reviewer 开头（与①复用） | ⑤ 成本超支 |
| 🔌 超时熔断与诚实降级 | L03 | web_search_structured（researcher 内） | ①② 慢/坏工具 |
| 🔑 副作用与幂等 | L04 | publish 节点（可选） | ⑥ 危险副作用（重放） |
| 🚦 人在环审批 | L05 | publish 节点内 interrupt | ⑥ 危险副作用（首次） |
| 🔄 断点续跑 | L06 | service 层 + jobs 注册表 | ④ 进程崩溃 |
| 📊 轨迹级可观测 | L07 | service 层（每次运行结束） | 可见性 |

> 🎯 **核心认知**：七机制不是堆砌，而是**协同**——L01 的诚实收尾路径被 L02/L03 复用（成本超限、降级声明都接同一条「带部分结果退出」）；L04 的幂等键是 L05 审批策略（first_only 免审）和 L06 断点续跑（不重放副作用）的地基。每个机制默认关、可降级，纯净跑零税。

---

## 2. 混沌收益矩阵定稿（对照 L00）

| 故障 | 全关（v2 裸奔） | 全开（v3） | 收益 |
|------|----------------|-----------|------|
| slow | ☠️ polluted (124) | 🟡 truncated (30) | 省 94 + 不污染 |
| flaky | ☠️ polluted (162) | 🟡 truncated (40) | 省 122 + 不污染 |
| loop | 🟡 caught (220) | 🟡 truncated (80) | 省 140 |
| crash | 🔄 full_rerun (115) | ✅ completed (60) | 省 55 + 不重跑 |
| bomb | 💸 overspent (70714) | 🟡 truncated (5000) | 省 65714 |
| sideeffect | ⚠️ duplicate (168) | ✅ completed (10) | 省 158 + 不重复 |

**SLO 卡**：任务成功率 33%→100%，平均浪费 token 11917→870，副作用重复率 17%→0%。

> ⚠️ **诚实标注**：mock 演示数字（基于 L00 基线的结构性结论）。真实 API 的绝对数字需 `--real` 模式，但「全关 vs 全开」的差异结构不变。

---

## 3. 纯净跑零税回归

| 场景 | 全关 | 全开 | 应满足 |
|------|------|------|--------|
| pure（无故障） | 成功 0 token | 成功 0 token | 全开不劣于全关 |

全开七机制对无故障的正常任务**不劣化**——证明治理零税。这是「不伤老能力」传统的延续：所有机制默认关、可降级，开了不劣化、故障下才生效。

---

## 4. 版本演进

```
v1（多智能体）          v2（Deep Research）              v3（生产可靠）
能跑的搜索→写报告  →    有记忆/反思/CodeAct/浏览器  →   +步数/成本/熔断/幂等/审批/恢复/观测
rag/workflow 课程       frontier + gui-agent 课程        agent-ops 课程
测试：25         →      104                        →    219
可靠性：无        →      无                         →    SLO 卡（33%→100%）
```

与 kb-qa README 的三版本格式对齐——两个作品集项目对称：kb-qa 走 RAG→运维→多模态，research-assistant 走多智能体→深研究→生产可靠，每一步都有数字。

---

## 5. 落地清单（L09 整合改动）

| 文件 | 改动 | 如何验证 |
|------|------|---------|
| `portfolio-projects/research-assistant/README.md` | **新增**「## 🛡️ 生产可靠性（AgentOps v3）」章节：七机制治理架构表 + 开关降级路径 + SLO 卡 + v1→v2→v3 演进 | 见 README |
| `portfolio-projects/research-assistant/docs/production-reliability.md` | **新增**：v3 架构文档（七机制位置 + 降级路径 + 混沌矩阵 + SLO 卡 + 版本演进） | 见 docs |
| `README.md`（根，中） | 注册课程九：徽章 85→95 / 266→485、课程路线表加行、课程九详情章节、目录树加 agent-ops-lessons/、作品集行 v2→v3 | grep `九大方向\|课程九` |
| `README.en.md`（根，英） | 同步：Nine Courses / Course 9 | grep `Course 9\|Nine` |
| `.gitignore` | 课程运行产物（outputs/、jobs/publish db、chaos 档案本地再生成物） | — |

### 验收

```bash
cd portfolio-projects/research-assistant

# 1. 全部旧测试 + 新增全绿（123 + 96 = 219）
python -m pytest -q
# 预期：219 passed

# 2. 任一开关关掉回退现状行为
python -m pytest tests/test_graph.py tests/test_nodes.py -q
# 预期：全绿（开关默认关）

# 3. 混沌端到端可复现
python eval_agent/run_chaos_eval.py
# 预期：生成 CHAOS_REPORT.md，全开成功率 100%

# 4. 根 README 中英一致
cd ../..
grep -c "课程九\|agent-ops-lessons" README.md       # 中文有课程九
grep -c "Course 9\|agent-ops-lessons" README.en.md   # 英文有 Course 9
grep "八大方向\|eight courses\|85 lessons" README.md README.en.md  # 无残留（除历史课次介绍）
```

---

## 6. 全仓课程九注册核对

按任务书要求，本课**无需重编号任何旧课程**，只做追加注册。grep 核对：

- ✅ 徽章：lessons 85→95，tests 266→485
- ✅ 课程路线表：加「生产 | Agent 生产可靠性 | 10/10」行
- ✅ 课程九详情章节：10 节课逐课介绍
- ✅ 目录树：加 `agent-ops-lessons/`
- ✅ 作品集行：research-assistant 测试 123→219，加「生产可靠性」
- ✅ flowchart：加 I["Agent 生产可靠性"] 节点
- ✅ README.en.md 同步（Nine Courses / Course 9）
- ✅ 无「八大方向」残留（本仓库用的是「课程路线」表非「八大方向」文本，逐处确认）

---

## 7. 两条贯穿主线（全课程总结）

- **爆炸半径主线**：L00 量出五种失控的无界半径，每课把一种压到有界——循环→步数有界、成本→预算有界、故障→降级有界、副作用→幂等+审批有界、崩溃→重做量有界。
- **自主-控制主线**：每个保护机制拿自主性/延迟/人力换安全——闸太紧 Agent 废掉，太松等于裸奔。first_only 审批、软预算降级、熔断阈值，都是这个权衡的产物。

---

## 🎯 面试话术（毕业版）

> 「我的研究智能体经历三个版本：能跑的多智能体 v1 → 有记忆能反思会写代码的 Deep Research v2 → 生产可靠的 v3。
>
> v3 的七个治理机制——步数预算、成本预算、熔断降级、副作用幂等、人在环审批、断点续跑、轨迹观测——全部默认关、可降级。收益有混沌矩阵和 SLO 卡背书：六类故障注入下，全关成功率 33%、全开 100%，平均浪费 token 从 1.2 万降到 870。还有一行纯净跑回归证明治理零税。
>
> 我的两个作品集项目现在是对称的：kb-qa 走了 RAG→运维→多模态，research-assistant 走了多智能体→深研究→生产可靠——每一步都有数字。
>
> 这套和 ops-lessons 的区别在于：ops 护一次请求（鉴权限流守护栏），我护一条轨迹（Agent 会自己转很多圈、自己决定下一步）。kb-qa 是线性链用不上这些机制，research-assistant 是循环体非用不可，这个不对称本身就是边界证据。」
