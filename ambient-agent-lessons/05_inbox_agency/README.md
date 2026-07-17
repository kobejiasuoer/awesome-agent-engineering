# Lesson 05 — 收件箱与自主级别：不打断的交付面

> 本课目标：**给常驻产出一个异步交付面（收件箱五通道），并给「代办动作」装上胆量分层（agency ladder：notify / propose / act）**。人不在场时：通知有处落、摘要有处攒、审批能隔夜、先斩后奏有留痕。
>
> 学完你能回答面试官那句：**「后台 Agent 要发布/要审批，用户睡着了怎么办？」**——答案：interrupt 状态在 checkpoint 里等人，审批从「阻塞对话」变成「收件箱待办」；自主级别决定哪些动作可以不等人。

---

## 0. 起点：交付面问题

前四课解决了「何时醒、看什么、研究什么、说不说」。最后一环：**说到哪？** 会话式的交付面是对话窗口——人在场才成立。常驻 Agent 的产出发生在人不在场时，需要一个**异步交付面**：

```
L04 decide() ──deliver()──→ 收件箱（sqlite）
                              ├─ notify    立即通知（major 且配额内）
                              ├─ digest    摘要条目（攒着，build_digest 日结）
                              ├─ proposal  行动草稿（agency=propose，等人 accept）
                              ├─ approval  审批请求（后台 HITL，隔夜等人）
                              └─ alert     健康告警（L07：缺勤/预算/信源故障）
```

> 🎯 **核心认知**：五类条目的**通道语义不同**——notify 是「现在看」，digest 是「今晚看」，proposal/approval 是「要你决定」，alert 是「系统出事了」。混在一个通道里，就是换个地方重演通知疲劳。同样关键：`stay_silent` **不产生任何条目**——沉默连收件箱都不进，这是最常见的正确结局。

对齐 LangChain ambient agents 的三姿势：notify（通知）/ question（审批）/ review（草稿确认）——本课的 notify+digest、approval、proposal 三组通道分别是它们的落地。

---

## 1. 隔夜审批：interrupt 在 checkpoint 里等人

agent-ops L05 的 HITL 是**会话内**的：SSE 发 `approval_required`，人在前端点批准。常驻场景里 publish 触发 interrupt 时是深夜 23:00——人不在场。本课的组合拳（**零新机制，纯复用**）：

```
23:00  后台班次跑到 publish → interrupt（enable_hitl）
       daemon 不阻塞等待：file_approval_request() 落一条 approval 条目
       任务挂起——interrupt 状态持久在 checkpoint 里，不占进程、不怕重启
（夜里什么都不发生）
08:30  人打开收件箱 → pending_approvals() 看到待办
       approve_entry(id, True) → 复用 service.submit_approval(thread_id)
       → Command(resume) 从 checkpoint 恢复 → publish 执行 → 条目落章
```

> 💡 agent-ops L05 当时写下「跨进程恢复（审批可以隔夜）」这句话时还没有真实场景——常驻模式就是它等的那个场景。**审批可以隔夜**不是新能力，是旧能力第一次被用对地方。

---

## 2. agency ladder：代办动作的胆量分层

产出之后「要不要代办动作」（本项目的动作=publish 发布），`agency_level` 三级：

| 级别 | 行为 | 副作用边界 | 适用 |
|---|---|---|---|
| `notify`（默认） | 只报告，动作碰都不碰 | 零副作用 | 新上线的盯梢、高风险动作 |
| `propose` | Agent 拟好草稿 → proposal 条目 → 人 `accept_proposal` 才执行 | 副作用在**人点头之后** | 中风险（发报告、建 issue） |
| `act` | 直接执行（幂等键防重放）+ notify 留痕条目 | 副作用在**人点头之前** | 低风险 + 幂等 + 可回滚 |

`code.py` Part 3 的分岔实录：notify 连 publish 都不 import；propose 的发布发生在 accept 之后；act 直接发布、同内容重放被幂等键挡下（`idempotent_replay=True`）、且必有「已代你发布」留痕。

> 🎯 **核心认知（自主-控制主线的总旋钮）**：阶梯的爬法是**单向观察、双向可退**——新动作先 notify 跑两周攒信任，产出稳定升 propose，只有「做错了也能撤」的动作才配 act；出一次事故，降级永远是一行配置。act 的两条硬前提缺一不可：**幂等**（重放不翻车，agent-ops L04 资产）+ **留痕**（先斩后奏必须可审计）。

---

## 3. 流派对比：人不在场的交互，怎么设计？

| 流派 | 做法 | 取舍 |
|---|---|---|
| ① **阻塞等待** | interrupt 后进程原地等人回复 | ✅ 实现最直觉；🚫 常驻场景下等 8 小时=资源浪费+一崩全丢；超时放弃则重大动作永远做不成 |
| ② **超时默认放行/否决** | 等 N 分钟没人回就按默认走 | ✅ 不卡死；🚫 「默认放行」=夜里无人审批变横行，「默认否决」=夜班全白跑——两个默认都不对 |
| ③ **收件箱待办**（本课） | interrupt 状态落 checkpoint，审批条目落箱，人回来恢复 | ✅ 不占资源、不怕重启、审批可隔夜、决策权真正在人；🚫 动作延迟到人出现（对紧急动作要配 escalation——练习） |
| ④ **全自动 + 事后审计**（act 级） | 不问直接做，幂等+留痕+可回滚 | ✅ 零延迟；🚫 只适用低风险动作——它不是 ③ 的替代，是阶梯上的另一级 |

**选 ③ 做默认、④ 做低风险特例的理由**：checkpoint 持久化让「挂起等人」的成本≈0（不占进程），这是 ① 做不到的；而 ② 的本质问题是把**风险决策**交给了超时器。③ 和 ④ 不是二选一——agency ladder 就是让每类动作停在正确的那一级。

---

## 4. 跑起来

```bash
cd ambient-agent-lessons/05_inbox_agency
python code.py        # 零 API、零联网、零等待
```

---

## 5. 落地清单

| 文件 | 改动 | 如何验证 |
|---|---|---|
| `src/research_assistant/inbox.py` | **新增**：五通道收件箱 CRUD + `deliver`（L04 投递面）+ `build_digest` 日结 + `file_approval_request`/`approve_entry` 隔夜审批 + `apply_agency`/`accept_proposal` 阶梯 | 见下 |
| `src/research_assistant/config.py` | **新增**：`enable_inbox` / `agency_level`（默认 notify） | `.env` 设 `AGENCY_LEVEL=propose` |
| `tests/test_inbox.py` | **新增**：15 个测试（通道语义/沉默零条目/日结不重复/隔夜审批恢复/审批幂等/三级副作用边界/act 重放被挡） | `pytest tests/test_inbox.py -q` |

研究图 / service **零改动**——`approve_entry` 只是 `submit_approval` 的收件箱前台；publish/HITL/幂等资产原样复用。

### 验收

```bash
cd portfolio-projects/research-assistant
python -m pytest -q          # 274 + 15 = 289 passed
python -m pytest tests/test_inbox.py -q   # 15 passed
```

---

## 6. 本课在两条主线上的位置

- **倒置主线**：第⑤环（怎么送 & 人不在场怎么办）落地完成。至此五个环节全部倒置——只差一个把它们串起来**跑在真实时间里**的常驻进程（L06）。
- **注意力经济主线**：收件箱是注意力的**分级队列**——notify 抢占、digest 批处理、approval 是「需要你决策」的显式队列。L04 决定「说不说」，本课决定「放哪、什么时候被看到」；两课合起来，注意力预算才算真正管完。

---

## 🎯 面试话术

> 「后台 Agent 的审批问题我用『checkpoint 挂起 + 收件箱待办』解决：夜里跑到危险动作触发 interrupt，daemon 不阻塞等待——中断状态持久在 checkpoint 里，收件箱落一条审批待办，进程该干嘛干嘛；人第二天一键批准，用同 thread_id 带 Command(resume) 恢复执行。审批可以隔夜，重启也不丢。
>
> 哪些动作可以不等人？我做了自主级别阶梯：notify 只报告、propose 拟稿等确认、act 先斩后奏。act 的硬前提是幂等加留痕——同内容重放被幂等键挡下，每次代办都有可审计的留痕条目。爬梯子单向观察（先 notify 攒信任再升级），降级永远一行配置。」
