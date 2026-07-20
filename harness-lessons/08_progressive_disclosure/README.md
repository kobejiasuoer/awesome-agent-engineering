# Lesson 08 — 渐进披露与 skills：指令的懒加载

> 本课目标：**system 不再单体全量——三层指令架构收口：常驻核心（身份+红线）/ 索引层（技能目录+记忆索引+工作区指针，便宜常驻）/ 按需层（命中的正文，用时换入）。实测三任务各命中各的，30 调用膨胀账省 58%；复用 frontier-L03 的 skill_loader，不另起炉灶。**

---

## 1. 指令膨胀定律与已有雏形

能力越多 system 越长：每个工具的用法、每种场景的规程若全量常驻，90% 场景用不到 90% 的指令，但每次调用都付全额窗口租金。实测本仓库技能库（4 个 skill）：全部正文 468 token vs 目录索引 66 token——**7 倍差**，且技能库越大差距越悬殊（索引成本只随「技能数×一行」线性长）。

**frontier-L03 已经做了雏形**：skill_loader 的「描述先行、用到才加载全文」在 writer 单点跑了很久。本课做两件事：把它推广成**全链路的三层架构**（`build_layered_system`），并给每层装上**账本计量**（breakdown）——复用 `enable_skills` 开关与 `skills/` 目录，不新建模块（边界表红线）。

## 2. 三层指令架构（整门课窗口构成的定稿图）

```
┌ 常驻核心   身份+红线              永远在（L02 分层可压性：system 不可压）
├ 索引层     skill 目录（每技能一行）
│            + 记忆索引（L03）        便宜常驻——「可能有用」挂在墙上
│            + 工作区指针（L06）
└ 按需层     命中的 skill 正文
             + 记忆正文 / 文件内容    用时换入——「此刻在场」才付全文租金
```

实测组装（任务「跨源深度调研」）：核心 10 + 索引 66 + 按需 120（只装命中的 deep-research-protocol）= 202 token；未命中的 quick-scan/comparison-table 正文一字未进。三任务对照：

| 任务 | 命中 | 三层账单 | 单体账单 |
|---|---|---:|---:|
| 跨源深度调研 | deep-research-protocol | 202 | 481 |
| 快讯速览 | quick-scan-protocol | 182 | 481 |
| 订会议室 | （无） | 77 | 481 |

30 次调用的膨胀账：单体 14,911 vs 三层 6,262——**省 58%**。

## 3. 与 L03 的同构收口：一套机制，三种内容

「索引常驻、正文按需」在本课程出现了三次，本课把它们收进同一个索引层：

| | 谁写的 | 索引形态 | 正文何时进窗 |
|---|---|---|---|
| 记忆（L03） | **agent 写**（学到的） | MEMORY.md 每条一行 | trigger 命中 |
| skill（本课） | **人写**（配置的） | 目录每技能一行 | match/LLM 判断命中 |
| 文件（L06） | **运行产出的** | 指针每文件一行 | agent 主动读回 |

同构的代价也同构：**索引质量决定召回**。反例可复现（测试锁死）：description 写成抽象词「输出规范」，任务「写一份研究报告」命不中——漏加载。与 L03 练习 3 的 triggers 写差、L04 练习 2 的检索式 query 写差是同一根软肋：渐进披露把「全文常驻」的窗口成本换成了「索引写得好不好」的召回风险——这笔交换几乎总是划算，但风险要有人看着（练习 2）。

## 4. 加载决策：判断与纪律（第五次）

哪些 skill 该加载——机械匹配（match_skills 关键词+停用词，frontier-L03 现状）够用时用它；不够时换 **LLM 判断**（「本任务需要哪些技能？」——判断交给模型）。不变的纪律：三层结构、逐层计量（breakdown 进账本口径）、加载留痕。writer 单点路径保持现状不动（验收条款）；`build_layered_system` 的运行时消费方是长程模式的 system 组装（v5/L09）。

## 5. 流派对比：能力扩张的四条路线

| 流派 | 思路 | 取舍 |
|---|---|---|
| 单体 system | 全部规程常驻 | 简单；膨胀账线性涨，且大 system 稀释注意力 |
| 每场景一个 agent | skill 沦为 agent，路由分发 | 隔离好；编排成本高、共享上下文难（Cognition 警示再现） |
| **渐进披露** | 索引常驻+正文按需 | **本课**：省 58% 起；代价是索引召回风险 |
| 微调内化 | 把规程练进权重 | 零窗口成本；贵、改不动、规程一变要重训 |

业界锚点：Anthropic Agent Skills（skill=文件夹+SKILL.md，描述先行——frontier-L03 的直接出处，本课的三层化是它的工程延伸）；Claude Code 的 skills/slash-commands（名字+描述常驻，正文按需——你在本课程的生成过程中看过它加载 skill）；MCP（工具的远程按需——同一母题在工具维度的投影，ops 课已学）。

## 6. 跑起来

```bash
cd harness-lessons/08_progressive_disclosure
python code.py   # 膨胀定律 → 三层解剖 → 三任务对照 → 同构收口+漏加载反例
```

## 7. 落地清单

| 文件 | 改动 |
|---|---|
| `src/research_assistant/skill_loader.py` | **扩展**（不新建）：build_layered_system（三层组装+breakdown 计量）+ monolithic_system（对照组） |
| `skills/deep-research-protocol/`、`skills/quick-scan-protocol/` | 新增 2 个 skill（深研究规程/快讯速览规程；与既有 2 个共 4 个） |
| `src/research_assistant/config.py` | `enable_layered_system`（默认 off；skills 加载复用现有 `enable_skills`） |
| `tests/test_layered_system.py` | 新增 9 测试（三层组装/计量/同构组合/单体对照/漏加载反例/确定性） |

### 验收

```bash
cd portfolio-projects/research-assistant
python -m pytest tests/test_layered_system.py tests/test_skills.py -q  # 22 passed（9 新 + frontier 回归）
python -m pytest -q                                                     # 444 passed（435 + 9）
cd ../../harness-lessons/08_progressive_disclosure && python code.py
```

## 8. 本课在两条主线上的位置

**窗口经济**：指令的「可能有用」与「此刻在场」分开计价在本课收口——核心永在、索引便宜常驻、正文按需，膨胀账省五成起。**外置化**：最后一类内容（指令正文）也搬出窗口——虚拟内存图八部件齐装，L09 全套合体跑收益矩阵。

## 🎯 面试话术

> 「我的 system prompt 是三层的：常驻核心只有身份和红线；索引层放技能目录、记忆索引、工作区指针——每项一行，便宜常驻；按需层只装本任务命中的正文。实测 4 技能库单任务只命中 1 个，30 次调用省 58%，技能库越大省得越多。这套机制和记忆文件、工作区指针同构——学到的、配置的、产出的三种内容，一样的索引经济学。软肋我也量化过：描述写成抽象词就漏加载——渐进披露把窗口成本换成索引召回风险，所以我的技能描述有写作规范、有漏加载的回归测试。」
