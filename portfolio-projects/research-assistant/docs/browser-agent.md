# Browser Agent 架构文档（GUI Agent 课程 L11 毕业整合）

> 本文档总结 GUI Agent 课程（gui-agent-lessons L00–L12）给 research-assistant 长出的「会上网」能力。课程细节见 `gui-agent-lessons/`，本文档聚焦生产架构。

## 1. 四层全景

research-assistant 的「手」由四层构成（L01–L07 手写，L09 落地封装）：

```
┌─────────────────────────────────────────────────────────┐
│  安全层（L07，默认开，不随 enable_browser 开关）            │
│  域名 allowlist + 敏感动作确认 + 注入扫描                   │
├─────────────────────────────────────────────────────────┤
│  可靠性层（L06）                                          │
│  循环检测（观察哈希）+ 换策略 + 重试预算 + 人工接管点        │
├─────────────────────────────────────────────────────────┤
│  行动层（L03）                                            │
│  受限 DSL：click(n)/type(n,text)/scroll/back/finish       │
│  可校验可白名单，非法动作转结构化错误回注                    │
├─────────────────────────────────────────────────────────┤
│  观察层（L02）                                            │
│  元素编号列表（主）+ SoM 截图（混合路线卡住时）             │
│  比原始 HTML 省 ~9x token                                 │
└─────────────────────────────────────────────────────────┘
        ↑                              ↓
   BrowserSession（L01，async）    Evidence 证据链（L10）
   goto/click/type/extract         URL+访问时间+快照
```

## 2. 与既有五机制的协作

Browser 能力不是孤立的，它和 frontier 课建立的五机制协同：

| 既有机制 | 与 browser 的协作 |
|---|---|
| 记忆（L01-02） | browse 的证据可写入记忆，下次同类任务前 recall「这种页容易卡在假按钮」 |
| 反思（L04-05） | browse 失败→语言化教训→注入重试（L06 步级换策略 + frontier 任务级 Reflexion） |
| 代码解释器（L06-07） | browse 取回的数值证据走沙箱复算，报告「数字可复算 + 来源可回访」 |
| Skills（L03） | browse 工具的使用规范可做成 skill（如「翻页取证 skill」） |
| 任务账本（L10） | 多步 browse 的进度可记入账本，跨会话续跑 |
| 轨迹评估（L08-09） | browser 轨迹落盘，TrajectoryEvaluator 评步数/循环/失败归因 |

## 3. 一次运行的数据流

```
用户提问「对比 LangGraph 最近 release」
  ↓
split 拆子问题 → researcher 并行
  ↓
每个 researcher:
  1. (enable_memory) recall 旧记忆
  2. web_search → 摘要 + 来源链接 [github.com/..., arxiv.org/..., evil.com/...]
  3. (enable_browser) get_browser_tool()
     → browse_for_evidence([allowlist 内的 URL]) 或 deep_browse(入口, 跟链接)
     → [Evidence(内容, URL, 访问时间, 快照)]
     ↓ 安全层：evil.com 拦、.exe 敏感确认、注入扫描标注
     ↓ 降级链：browse 失败 → 回退 search 摘要
  4. LLM 综合 摘要+证据 → finding（含 URL+时间）
  ↓
summarize 汇总 → writer 写报告（引用带 [来源](URL)（访问于 时间））
  ↓ (enable_code_interpreter) 数值走沙箱复算
reviewer 审稿 → pass/重写/补研
  ↓
报告：结论可回访（URL+时间）+ 数字可复算（代码附录）
```

## 4. 开关与降级路径

每个开关默认关，关掉任一系统仍跑，123 测试始终绿。

| 开关 | 默认 | 关掉时降级到 | 开启时增益 |
|------|------|------------|-----------|
| `enable_browser` | false | 纯 search 摘要 | 详情页取证（URL+时间+字段） |
| `enable_memory` | false | 无记忆（每次从零） | 跨会话记得查过什么 |
| `enable_skills` | false | 无格式规范 | writer 遵循 skill 格式 |
| `enable_code_interpreter` | false | LLM 口算 | 数值可复算 |
| `enable_ledger` | false | 每次完整报告 | 增量简报 |

**安全层不在此表**——它不随 `enable_browser` 开关，只要 browser 一开，allowlist/敏感确认/注入扫描就默认生效。安全是红线不是开关。

## 5. 机制收益表（对照 L00 裸基线）

用 L08 mini-benchmark + frontier TrajectoryEvaluator 出的收益表：

| 指标 | L00 裸基线（纯 search） | L11 全开（+browser） | 收益 |
|------|----------------------|---------------------|------|
| 能拿到的证据种类 | 标题+摘要+链接 | +版本号/日期/变更要点/翻页内容 | 详情页字段从无到有 |
| 引用可回访率 | 0%（无 URL 或不可点） | ~100%（每条结论带 URL+时间） | 来源可回访 |
| 访问时间戳 | 无 | 有（ISO） | 时效可追溯 |
| 任务成功率（8 任务） | 75%（T6/T7 失败） | 100%（加固后） | +25pp |
| 平均步数 | 3.9 | 2.9（加固版换策略省步） | -25% |
| 注入失守率 | 100%（mock） | 0%（动作层硬拦） | 安全 |
| 循环打转 | 有（裸 agent 卡假按钮） | 无（观察哈希检出） | 可靠性 |

> ⚠️ 数字来自本地 mini-benchmark（mock LLM + 本地 test_pages），非真实 API。真实收益需 `--real` 跑，但「browse 多拿到详情页字段」「加固后成功率↑」的结论是结构性的，不依赖具体内容。

## 6. 技术栈

- **浏览器自动化**：Playwright（async API，Chromium）
- **LLM**：智谱 glm-4（文本路线）/ glm-4v-plus（视觉路线，混合）
- **视觉标注**：Pillow（SoM 画框编号）
- **集成**：LangGraph async 图（researcher 节点接 browser_tool）
- **测试**：pytest（123 测试，含 19 browser 测试，全 mock + 本地页）

## 7. 安全红线

- 敏感动作（登录/支付/提交/下载执行文件）强制人工确认
- 默认域名 allowlist（127.0.0.1/arxiv.org/github.com），非白名单硬拦
- 不碰需登录页面，不写绕过验证码/反爬/风控的内容
- 真实网站演示限公开只读页面，访问频率克制，诚实标注访问日期
