# Lesson 06 — 文件即工作记忆：窗口只留指针

> 本课目标：**把工作集（计划/原文/笔记/草稿）搬进文件工作区，State/窗口只留一行指针——指针总量 2,763 字替 91,366 字原文站岗（33 倍差）。附赠两件大杀器：recitation（现读 plan.md 对抗漂移）与崩溃续跑（fetch 30 次 vs 无工作区重启 48 次）。**

---

## 1. 虚拟内存观在本课闭环

L04 把工具全文引用落盘、L05 把过程关进子窗口——本课把**工作集**正规化：

```
workspace/<run_id>/
  plan.md        计划快照（目标与源清单；recitation 的原料；L07 改道改的就是它）
  sources/       信源原文（无损落盘——压缩丢的、截断砍的，这里都在）
  notes/         每源结论笔记（「有笔记=已研完」：断点续跑的进度事实源）
  draft.md       报告草稿
```

**指针协议**：State/窗口里只住一行——`📁 [sources/S17.txt]（13,624 字）开头：《生态依赖图谱》……`。内容按需读回，回读也要过 L04 整形——**外置不是免费回读**。

## 2. 三存储各管一段（边界表落地，互补不替代）

| | checkpoint（agent-ops L06） | task_ledger（frontier） | **workspace（本课）** |
|---|---|---|---|
| 存什么 | 图状态快照 | TODO 树、进度语义 | 计划/原文/笔记/草稿 |
| 谁读 | 机器（恢复用） | 结构化查询 | **人和 agent 都直接读写** |
| 崩溃后 | 图从最后快照续跑 | 进度可查 | **工作集原地满血** |

**双恢复各管一段**：checkpoint 恢复「图跑到哪了」（课程九资产，只引用不重演），workspace 恢复「工作集还在不在」。实测崩溃线：第 18 源后进程死亡 → 新进程 `Workspace.attach(run_id)` → `note_names()` 即进度事实源，跳过已完成的 S01–S18 → **fetch 总数仍 30**；无工作区的重启=前功尽弃：18 次白干 + 30 次重来 = 48 次。

**人机共域**：工作区是自由文本文件——你可以直接用编辑器打开 plan.md 改目标、翻 notes/ 检查结论。文件是最好的人机接口（与课程十 inbox 的异步协作面一脉相承）。

## 3. recitation：重读胜于记住

长任务后半程（S16 起），每步把 plan.md **现读**进窗口尾部：

- **为什么读尾部**：lost in the middle 的实证是窗口首尾利用率高、中段低——任务目标写在 20 轮之前，等于埋进了低利用率区；每步在尾部复述一次，目标永远「新鲜」。
- **为什么现读文件而不是引用窗口里的旧计划**：文件是事实源、窗口是缓存——L07 改道改的是 plan.md，复述自动带上最新版（demo Part 3：改了计划，复述块立刻变）。
- **机械账**：15 次复述 × ~50 token，总开销 <1% 计费；认知收益（少迷航）属于 mock 测不了的部分，引证据讲清、L09 真模型章抽查——诚实边界照旧。

这是 Manus 的 recitation 思想（他们用 todo.md 复述）——本课程用 plan.md 承担同一角色。

## 4. 流派对比：工作集放哪

| 流派 | 思路 | 取舍 |
|---|---|---|
| 全在 State | v4 现状 | 窗口扛全文；崩溃靠 checkpoint 但工作集语义埋在状态里，人不可读 |
| 只靠 checkpoint | 状态快照兜一切 | 管崩溃不管注意力：恢复后窗口还是那么肥；人不可读不可改 |
| **文件工作区** | 自由文本落盘+指针 | **本课**：人机共读写、无损、可 git；代价是指针/读回的纪律要维护 |
| 数据库工作集 | sqlite/向量库结构化 | 查询强；但「打开编辑器直接改」没了——适合 ledger 这类结构化语义，不适合草稿与原文 |

业界锚点：LangChain deepagents（虚拟文件系统是三件套之一：agent 用 ls/read/write 管理自己的文件）；Manus（「文件系统即终极上下文」：可恢复的压缩靠文件兜底 + todo.md recitation）；Claude Code（计划文件、`ls`/`Read` 工具、以及你在本课程里看到的每个 lesson 目录——都是 agent 与人共域的文件工作区）；MemGPT（外部上下文分页调入——本课指针+按需读回的学术先驱）。

## 5. 跑起来

```bash
cd harness-lessons/06_file_workspace
python code.py   # 解剖 → 长途主秀 → recitation → 崩溃续跑
```

| 指标 | L05 隔离档 | **L06 +工作区** |
|---|---|---|
| 完成/在场 | 30/30，20/20 | 30/30，20/20 |
| 主窗峰值 | 706 | 718（+recitation 的 ~50/步） |
| 指针 vs 原文 | —（原文用完即弃） | **2,763 字 vs 91,366 字** |
| 崩溃在 S18 | 重启=48 次 fetch | **attach 续跑=30 次 fetch** |
| 原文可回看 | ❌（丢了要重 fetch） | ✅ sources/ 永在 |

## 6. 落地清单

| 文件 | 改动 |
|---|---|
| `src/research_assistant/workspace.py` | 新增：Workspace（四件套/attach/指针协议/tree/recitation/进度事实源 note_names） |
| `src/research_assistant/config.py` | `enable_workspace`（默认 off）、`workspace_dir` |
| `eval_agent/harness_runs.py` | 新增 run_workspace_longhaul（落盘+复述+crash_at 续跑；fetch 计数跨「进程」连续） |
| `tests/test_workspace.py` | 新增 11 测试（结构/指针/现读复述/attach/进度事实源/崩溃续跑/确定性） |

运行时集成沿 L02/L05 先例：消费方是长程模式（eval 已接，v5/L09 接管）；`enable_workspace` 为 v5 预留。

### 验收

```bash
cd portfolio-projects/research-assistant
python -m pytest tests/test_workspace.py -q   # 11 passed
python -m pytest -q                            # 423 passed（412 + 11）
cd ../../harness-lessons/06_file_workspace && python code.py
```

## 7. 本课在两条主线上的位置

**窗口经济**：State 从「扛全文」变成「持指针」——窗口彻底回归「工作集缓存」的本分。**外置化**：虚拟内存图闭环——RAM（窗口）/磁盘（文件）/swap（压缩）/进程（子代理）全部就位；剩下驾驶舱（L07）与懒加载（L08）。

## 🎯 面试话术

> 「我的 Agent 把窗口当 RAM 用：工作集住文件工作区——计划、原文、笔记、草稿四件套，State 里只留一行指针，实测 2,763 字指针替 91,366 字原文站岗。这买到三样东西：一，原文无损——压缩丢的截断砍的都能从 sources/ 回来；二，崩溃续跑——『有笔记=已研完』是进度事实源，attach 工作区后 fetch 总数不变，无工作区的重启要多付 60% 的重复劳动；三，recitation——后半程每步现读 plan.md 进窗口尾部对抗目标漂移，总开销不到 1%。为什么现读而不是记住？文件是事实源、窗口是缓存——改道改的是文件，复述自动带上最新版。」
