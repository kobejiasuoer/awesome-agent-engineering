# Lesson 03 — 增量研究回路：只研究变化，不重研全量

> 本课目标：**把 watcher 的变化集接进研究图**——变化条目直接变成焦点子题（split 跳过 LLM 拆题），旧结论注入 prompt「已知这些，只补新的」，产出走 TaskLedger 增量简报（🆕新增/✏️修正/➡️不变）。矛盾不再被静默覆盖。
>
> 学完你能回答面试官那句：**「你的 Agent 第二次研究同一主题时，怎么不重复劳动？」**——答案分三层：研究面缩到变化（焦点子题）、已知结论不重研（旧结论注入）、产出只讲 diff（增量简报）。

---

## 0. 起点：L00 基线的第③环

基线 Day3：只多了一条小更新（框架 Y 补丁），现状仍重研全部 3 个子题，新增内容埋在全量报告里要人肉 diff。Day4 更糟：item-c 反转（撤回 AGUI 支持），报告没有任何修正标注——**旧结论被静默覆盖，矛盾要读者自己发现**。

本课的数据流（接在 L02 之后）：

```
watcher.scan_source() → ChangeSet
        │
run_incremental(topic, change_set) 三分支：
        │
   ┌────┴─────────────┬──────────────────────────┐
   ▼                  ▼                          ▼
ok=False          is_no_change()             有变化
「没能看到」       「确认无变化」          build_incremental_focus()
不进图、不产结论    不进图、零成本          变化条目 → 焦点子题
（L02 纪律消费端）                              │
                                    invoke(extra_state={focus, prior})
                                                │
                              split：焦点直用（跳过 LLM 拆题）
                              researcher：旧结论注入「只补新的，矛盾用『更正：』开头」
                                                │
                              record_and_brief()：ledger 记进度 → 增量简报 🆕/✏️/➡️
```

---

## 1. 焦点即子题：研究面由「主题」缩到「变化」

增量模式下 `split` 不再问 LLM「这个主题怎么拆」，而是直接采用变化集生成的焦点：

```python
# nodes.py · split 开头（enable_incremental_run 且有焦点时）
focus = state.get("incremental_focus") or []
if settings.enable_incremental_run and focus:
    return {"subtopics": [f.strip() for f in focus if f.strip()][:8]}
```

> 🎯 **核心认知**：LLM 拆题回答的是「研究**这个主题**该看哪几块」——它天然把研究面扩回全量。而变化集已经指认了「世界动了哪几条」，**拆题这一步在增量模式下是多余的**（还省一次 LLM 调用）。`code.py` Part 1 量化了 Day3 的差距：全量 587 token vs 增量 92 token，省 84%。变化越小省得越多——而 L02 已证明大多数日子变化为零。

焦点的构造（`incremental.py`）带着**通道语义**：

- 新增条目 → `【新增】标题：内容——这条新信息的内容、背景与影响`
- 变更条目 → `【内容变更】标题：最新内容——与此前已知结论有何出入？若矛盾，用「更正：」开头明确指出`

变更条目的措辞是故意的：它把「检查矛盾」的指令编码进子题本身，researcher 的产出若以「更正：」开头，简报层就能识别为 ✏️（见第 3 节）。

---

## 2. 旧结论注入：「已知这些，只补新的」

`prior_conclusions(topic)` 从 TaskLedger 取已确认结论（done 状态的任务结果），经 `prior_context` 字段流入子图，`route_to_researchers` 把它装进每个 Send 载荷（researcher 是 Send 驱动的，看不到子图全量 State——**旧结论必须随载荷下发**），researcher 的 prompt 里：

```
已确认的历史结论（不要重复研究）：
- 框架X支持AGUI：X 宣布全面支持 AGUI
只提炼新信息；若新信息与上述结论矛盾，用「更正：」开头明确指出。
```

与 frontier 记忆系统的分工：`enable_memory` 的 recall 注入的是**语义相关的旧经验**（模糊、跨主题）；本课注入的是**本主题账本上的已确认结论**（精确、结构化）。两者可同时开，互不替代。

---

## 3. 账本协作闭环：世界增量 → 工作增量

frontier-L10 的 TaskLedger 此前只有模块与测试，**没有运行时调用方**——本课是它首次接入主链路：

```
watcher（世界增量：信源变了什么）
   → 焦点研究（只研究变化）
      → ledger.update_status(done, result=finding)（工作增量：我确认了什么）
         → 下次 run 的 prior_conclusions（「已知这些」）
            → generate_incremental_brief（🆕新增 / ✏️修正 / ➡️不变）
```

`record_and_brief` 的顺序是关键：**先**对照「昨天为止的历史」生成简报，**再**把今天的发现入账——今天的结论明天才是「历史」。`code.py` Part 2 的 Day4 简报：

```
## 本次新增
- 🆕 新增: 重磅：框架 X 撤回 AGUI 支持转投 A2A……
- ✏️ 修正: 更正：框架 X 宣布支持 AGUI 协议……此前结论已不成立
## 不变项
- ➡️ LangGraph 发布 1.2 稳定版: 仍成立
```

对照 L00 基线 Day4：现状矛盾被静默覆盖；现在旧结论仍在场（➡️），反转显式标注（✏️）——读者一眼看到「世界观变了哪一块」。

> ⚠️ **复用资产的已知局限（诚实标注）**：`generate_incremental_brief` 判「不变项」用的是简单关键词启发式（frontier-L10 原样复用，红线不重写）——Day4 里被修正的「框架 X 支持 AGUI」同时出现在 ✏️ 和「仍成立」里。修法（把 ✏️ 命中的任务从不变项剔除）留作练习 4；它不影响 ✏️ 通道本身的正确性。

---

## 4. 流派对比：第二次研究同一主题，怎么做？

| 流派 | 做法 | 取舍 |
|---|---|---|
| ① **每次全量重研**（现状） | 当世界是全新的 | ✅ 永不漂移（每次都是完整快照）；🚫 大多数日子在烧重复的钱（L00 Day2/Day3 实测），增量埋在全量里 |
| ② **增量研究**（本课） | 只研究变化条目 + 旧结论注入 | ✅ 成本随变化量缩放（Day3 省 84%）、矛盾显式修正、产出是 diff 可读性高；🚫 **漂移风险**——每次只看变化，全局图景可能与世界脱节（旧结论错了但没条目触发重查，就一直错下去） |
| ③ **只做摘要不研究** | 变化条目直接进简报，不进研究图 | ✅ 最便宜（零 LLM）；🚫 没有「研究」——不核实、不关联旧结论、不判断影响，是 RSS 阅读器不是研究员 |

**选 ② + 定期校准的理由**：② 的漂移风险有标准解法——**定期全量校准**（如每 30 天强制一次 full run，重建基线），成本上等于「把 ① 的频率从每天降到每月」。本课不实现校准调度（属于 L07 的班次策略，留了练习），但 `first_scan` 的建仓语义已经为它留好了路径。③ 适合纯资讯流场景，但那不是「研究助手」的定位。

---

## 5. 跑起来

```bash
cd ambient-agent-lessons/03_incremental_research
python code.py        # 零 API、零联网、零等待
```

诚实标注：Part 2 的「研究」步骤用确定性 mock（真实图要 API key）；变化检测、焦点构造、账本记账、增量简报全部走真实落地模块。

---

## 6. 落地清单

| 文件 | 改动 | 如何验证 |
|---|---|---|
| `src/research_assistant/incremental.py` | **新增**：`build_incremental_focus` / `prior_conclusions` / `record_and_brief` / `run_incremental`（三分支入口） | 见下 |
| `src/research_assistant/state.py` | **新增**：`incremental_focus` / `prior_context` 字段（两层 State） | import 冒烟 |
| `src/research_assistant/nodes.py` | split 焦点直用（3 行，开关内）；route_to_researchers 载荷携带 prior_context；researcher prompt 注入旧结论（开关内）；research_team 透传两字段 | `pytest tests/test_incremental.py -q` |
| `src/research_assistant/service.py` | `_initial_state` 补两字段；`invoke` 加 `extra_state` 可选参（不传=现状） | 现有测试全绿 |
| `src/research_assistant/config.py` | **新增**：`enable_incremental_run`（默认关） | `.env` 设 `ENABLE_INCREMENTAL_RUN=true` |
| `tests/test_incremental.py` | **新增**：14 个测试（三分支/焦点直用/开关不变式/载荷下发/账本闭环/✏️ 修正） | `pytest tests/test_incremental.py -q` |

### 验收

```bash
cd portfolio-projects/research-assistant
python -m pytest -q          # 245 + 14 = 259 passed
# 开关关 = 现状（核心不变式）：即使 state 里有焦点，split 仍走 LLM 拆题
python -m pytest tests/test_incremental.py::test_split_ignores_focus_when_disabled -q
```

---

## 7. 本课在两条主线上的位置

- **倒置主线**：第③环——「增量靠人肉 diff」变成「机器只研究变化、产出只讲 diff」。人从 diff 工具升级为 diff 的读者。
- **注意力经济主线**：增量简报是为**注意力**设计的产出格式——🆕/✏️/➡️ 让「值得看的部分」自解释（✏️ 永远最值得看）。这直接为 L04 铺路：判级器判「major/minor」时，看的正是简报里有没有 ✏️ 和 🆕 的分量。

---

## 🎯 面试话术

> 「我的 Agent 第二次研究同一主题时做三层增量：一，**研究面缩到变化**——变化检测指认哪几条动了，这些条目直接变成研究子题，拆题的 LLM 调用都省了，Day3 场景实测省 84% token；二，**已知结论不重研**——账本里已确认的结论注入 prompt『只补新的』，并要求矛盾用『更正：』开头显式指出；三，**产出只讲 diff**——增量简报分 🆕新增/✏️修正/➡️不变三通道，重大反转不会被静默覆盖。
>
> 增量的代价是漂移——只看变化，全局图景可能与世界脱节。所以要配定期全量校准，相当于把全量重研的频率从每天降到每月，成本和正确性各拿一头。」
