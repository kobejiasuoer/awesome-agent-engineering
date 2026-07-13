# Lesson 10 — 深度浏览：多步任务与证据链

> 本课目标：**从「单页提取」到「多步取证」——给 BrowserTool 加 `deep_browse`（跟链接跨页），建证据链格式（结论 + URL + 访问时间 + 快照），让报告每个关键结论可回访。与 frontier L07「数字可复算」呼应，现在来源可回访——研究报告可信度第二次升级。**

学完你能回答：**「怎么让 agent 的研究报告可信到每条结论都能点开核对？」**——答案是证据链：多步浏览取证 + 每条结论带 URL+访问时间+页面快照，数字可复算（frontier L07）+ 来源可回访（本课）= 两次可信度升级。

---

## 0. 从「单页证据」到「证据链」

L09 的 `browse_for_evidence` 是**广度**——并行开多个独立详情页，每页一条证据。但有些任务需要**深度**：从一个入口页出发，跟链接翻页、跨页对比、逐层深入。例如硬任务「对比最近几次 release」：

```
L09（广度，单页）：                 L10（深度，多步）：
开 detail.html?id=1 → 1 条证据      开 search.html（列表）→ 跟「下一页」→ 翻到第2页
开 detail.html?id=2 → 1 条证据       → 跟第1条结果进 detail → 提取
开 detail.html?id=3 → 1 条证据       → back → 跟第2条结果进 detail → 提取
3 条独立证据，无顺序关系              证据链：列表→第2页→详情1→详情2，有访问路径
```

`deep_browse` 补的是「跟链接深入」这个维度——证据按访问顺序成链，能还原 agent 的取证路径。

> 🎯 **核心认知**：证据链不只是「多条证据」，是「**有路径的证据**」——每条证据带 URL+访问时间+从哪来，能还原 agent 走过什么路拿到什么。这是研究报告可信度的关键：读者不只看到结论，还能复走 agent 的取证路径自己核对。

---

## 1. 证据链格式

每条 Evidence 四个字段（L09 已定义，L10 强化使用）：

| 字段 | 作用 | 来源 |
|---|---|---|
| `content` | 提取的内容（版本号/日期/变更要点） | 页面正文 |
| `url` | 来源 URL | 当前页地址 |
| `accessed_at` | 访问时间（ISO） | 浏览时刻 |
| `snapshot` | 页面快照（文本摘要） | 正文前 200 字 |

报告引用格式（writer 产出）：

```
LangGraph 最近一次发布是 v0.12.0（[来源](https://github.com/.../releases)，
访问于 2026-07-13 11:00 UTC）。
```

- **URL** 让读者能点开核对
- **访问时间** 标注「这个结论在那个时间点的页面是这样」——网站会变，时间戳让结论可追溯
- **快照** 落盘存档，即使原页改版/下线，快照仍在

### 与 frontier L07「数字可复算」呼应

```
frontier L07（代码解释器）          本课（证据链）
─────────────────────            ─────────────────────
报告里的数字 → 附可复算脚本         报告里的结论 → 附可回访来源
读者能自己跑代码核对数字            读者能自己点开 URL 核对来源
数字可信度升级                    来源可信度升级
```

合起来 = **数字可复算 + 来源可回访** = 研究报告的两次可信度升级。这是 research-assistant 从「搜索→写报告」进化到「可审计的深度研究」的关键。

---

## 2. deep_browse 设计

```python
async def deep_browse(self, query, entry_url, max_steps=4, link_hint=""):
    """从入口页出发，跟链接跨页取证。"""
    page = await self._new_page()
    current_url = entry_url
    for step in range(max_steps):
        if not check_url_allowed(current_url): break       # 安全
        if not await self._safe_goto(page, current_url): break  # 降级
        # 提取当前页证据
        evidences.append(Evidence(content, current_url, accessed_at, ...))
        # 找下一个要跟的链接（hint 优先，过 allowlist）
        next_url = await self._pick_next_link(page, link_hint, allowed)
        if not next_url: break
        current_url = next_url
    return evidences
```

### 链接选择（`_pick_next_link`）

跟链接不是「随便点」——要选**相关且安全**的：

| 选择规则 | 作用 |
|---|---|
| `link_hint` 优先 | 含「release/版本/changelog」的链接优先跟（相关性） |
| allowlist 过滤 | 非白名单域的链接不跟（安全） |
| 跳过 `#` 锚点 | 死链不跟 |
| 第一个合规链接兜底 | 无 hint 命中时跟第一个 allowlist 内链接 |

### 与 browse_for_evidence 的分工

| 方法 | 维度 | 场景 |
|---|---|---|
| `browse_for_evidence` | 广度（并行多独立页） | 已知多个详情页 URL，各取各的 |
| `deep_browse` | 深度（跟链接串联） | 从列表页出发，翻页/跟链接深入 |

researcher 按任务选：有明确 URL 列表用广度，要从入口探索用深度。

---

## 3. 成本控制

多步浏览成本 = 步数 × (浏览器操作 + LLM)。控制：

| 控制 | 默认 | 作用 |
|---|---|---|
| `max_steps` | 4 | 最多跟几步链接 |
| `max_pages`（广度） | 2-3 | 最多开几个独立页 |
| 截图仅在混合路线卡住时开 | — | 视觉贵，按需（L05） |
| 快照截断 200 字 | — | 防快照膨胀 |

> 🎯 多步浏览的步数预算和 L04 agent 循环的步数上限是同一套成本哲学——每步烧钱，必须设上限。L11 收益表会有「browse 步数 vs 证据收益」的权衡列。

---

## 4. writer 产出的报告引用

L10 让 writer 在报告里引用证据——每个关键结论后附 `[来源](URL)（访问于 时间）`。这是在 writer 的 prompt 里引导：

```
你的报告每个关键结论必须标注来源，格式：
结论（[来源](URL)，访问于 YYYY-MM-DD HH:MM UTC）
```

writer 基于 researcher 提供的证据（带 URL+时间）写引用。报告从「无来源断言」升级到「每条结论可回访」。

### before/after 对比

```
纯搜索版报告（L00 基线）：              浏览取证版报告（L10）：
LangGraph 近期发布了 v0.12 系列，      LangGraph 最近一次发布是 v0.12.0
改进了 checkpoint 和并行子图。          （[来源](https://github.com/.../releases)，
                                        访问于 2026-07-13 11:00 UTC）。
                                        主要变更：断点续跑支持、死锁修复、
                                        序列化体积减 30%。
→ 无来源、无具体版本、无日期            → 有版本/日期/变更 + 可点开核对的 URL + 时间戳
```

---

## 5. 落地清单

### 改动文件

| 文件 | 改动 |
|---|---|
| `src/research_assistant/browser_tool.py` | **新增** `deep_browse` + `_pick_next_link`（多步证据链） |
| `tests/test_browser_tool.py` | **新增** 2 测试（多步取证/非 allowlist 停） |
| writer prompt | 引导引用证据（README 说明，落地在 writer 节点已有结构） |

### 验证

```bash
cd portfolio-projects/research-assistant
.venv/Scripts/python.exe -m pytest tests/ -q
# 预期：123 passed（L09 的 121 + deep_browse 2）
```

课程 code.py 演示 deep_browse 多步取证 + 证据链格式 + before/after 报告对比。

---

## 6. 课程 code.py 演示

`gui-agent-lessons/10_evidence/code.py`：

- 用 `deep_browse` 从 L00 搜索页出发，跟链接翻页进详情，产出证据链
- 展示证据链格式（每条带 URL+时间+快照）
- before/after 报告对比（纯搜索 vs 浏览取证）

详见 code.py。

---

## 7. 本课在两条主线上的位置

- **评估主线**：本课产出「引用可回访率」这个新指标——L11 收益表会有这一列（对照 L00 基线的 0%）。证据链也让 L08 mini-benchmark 的 T8（多步取证）能严格验收（查答案含 URL+时间）。本课的 2 个测试也是评估的一部分。
- **观察-行动接口主线**：本课把「行动」从单页扩展到多步串联——行动不止是 click，是 click 后跟链接、跨页、成链。观察也扩展：每步观察记成快照存档，不只喂给 LLM 还留给读者。这是观察-行动接口的「时间维度」——接口不只管单步，还管跨步的路径。

---

## 🎯 面试话术

> 「我的研究报告每个关键结论带 URL 和访问时间戳，页面有快照存档——读者能点开核对、能复走取证路径。数字可复算（frontier 代码解释器）+ 来源可回访（本课证据链），这是两次可信度升级。多步浏览用 deep_browse，从入口跟链接深入，每步过 allowlist、有步数预算控成本。和 L09 的 browse_for_evidence 分工：广度并行开多页、深度串联跟链接。」
