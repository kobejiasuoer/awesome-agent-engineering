# Lesson 05 — 视觉路线：GLM-4V 看截图操作

> 本课目标：**跑通视觉路线（SoM 标注截图喂 glm-4v-plus），与文本路线做同任务对照实验。三路线（文本/视觉/混合）同任务实测对比成功率/token/耗时，落地选混合路线。**

学完你能回答：**「文本派和视觉派到底谁强？什么时候该用视觉？」**——答案是同任务实测对比，视觉贵且 grounding 难但处理得了文本派处理不了的场景，落地选混合（文本为主、卡住才截图）。

---

## 0. 视觉路线为什么必须单独讲

L04 跑通了文本路线——元素编号列表喂 LLM。但有些场景文本路线**根本处理不了**：

- canvas/图片里的信息（DOM 没有文本）
- 复杂布局里元素编号漏了（动态生成、shadow DOM）
- 纯视觉的验证性 UI（颜色变化表示状态、图表数据）

这些场景下，**页面真正的「观察」是它的像素**，不是 DOM。视觉路线就是把截图直接喂给视觉语言模型（VLM），让它「看图说话」。这是 L00 三大流派里视觉派的实现。

> 🎯 **核心认知**：文本和视觉不是二选一，是互补。文本便宜稳但漏视觉信息；视觉所见即所得但贵且 grounding 难。落地的最优解是**混合**——文本为主，遇到文本处理不了的场景才截图求助。本课用同任务对照实验证明这个取舍。

---

## 1. 流派对比（本课灵魂）

| 路线 | 观察 | 行动 | 成本 | grounding | 适用场景 |
|---|---|---|---|---|---|
| ① **文本派** | 元素编号列表（L02） | `click(n)` DSL | 低（文本 token 便宜） | ✅ 稳（编号即目标） | DOM 完整、交互元素可提取 |
| ② **视觉派** | 截图（像素） | 坐标点击 / SoM 编号 | 高（图片 token 贵） | 🚫 难（坐标飘、看懂点不准） | canvas/复杂布局/纯视觉 UI |
| ③ **混合派**（落地选它） | 文本为主，卡住截图 | DSL 为主，截图时 SoM 编号 | 中（偶尔截图） | ✅ 平衡 | 通用（research-assistant） |

**选 ③ 的理由**：research-assistant 的硬任务（翻页取证）绝大多数是 DOM 可提取的，文本路线够用且便宜。只有遇到「搜索结果以图表呈现」「按钮是图标无文本」这类场景才需要视觉。混合派 = 文本派的成本 + 视觉派的兜底，性价比最优。

---

## 2. 视觉路线的命门：grounding

> 📖 **SeeAct**（Zheng et al. 2024, [arXiv:2401.01614](https://arxiv.org/abs/2401.01614)）证明：GPT-4V 级 VLM 当 web agent 的瓶颈在 **grounding**——它「看得懂」页面（能复述内容），但「说不准」该点哪个坐标。直接让 VLM 输出 `(x=347, y=512)`，飘得很。

### SoM：通用 VLM 的救星

> 📖 **Set-of-Mark**（Yang et al. 2023, [arXiv:2310.11441](https://arxiv.org/abs/2310.11441)）证明：给图片里每个可操作对象画框 + 编号标注，VLM 就能精确指对象——答编号不答坐标，grounding 准确率大幅提升。

```
原始截图：                          SoM 标注截图：
┌─────────────────────┐            ┌─────────────────────┐
│ [搜索框]  [搜索]     │            │ ①[搜索框] ②[搜索]    │
│ LangGraph            │            │ ③LangGraph           │
│ CrewAI               │            │ ④CrewAI              │
└─────────────────────┘            └─────────────────────┘
VLM 输出：点 (347, 512)  ← 飘       VLM 输出：click(2)  ← 准
```

**SoM 的本质**：把视觉派的「坐标点击」退化成「编号点击」——和文本派的 `click(n)` DSL **同构**。所以本课视觉路线复用 L03 的 DSL，只是观察从「元素编号列表」换成「标注截图」。这是三派在行动层统一的关键。

### 专用模型派：不用 SoM 也强

> 📖 **CogAgent**（Hong et al. 2023, [arXiv:2312.08914](https://arxiv.org/abs/2312.08914)）是智谱系高分辨率 GUI 专用 VLM；**UI-TARS**（Qin et al. 2025, [arXiv:2501.12326](https://arxiv.org/abs/2501.12326)）是端到端 GUI 模型，证明**专训能大幅超过通用 VLM+脚手架**——它们不靠 SoM，直接从截图学动作。

专用模型派是 L12 的主角——它们可能让「手写脚手架」路线过时。本课只对照，不部署。

---

## 3. SoM 标注实现

手写 `annotate_screenshot(page, elements)`：用 Pillow 在截图上给每个可交互元素画框 + 编号。

```python
from PIL import Image, ImageDraw

def annotate_screenshot(screenshot_path, elements, out_path):
    """在截图上给每个元素画框 + 编号。"""
    img = Image.open(screenshot_path)
    draw = ImageDraw.Draw(img)
    for el in elements:
        bbox = el["bbox"]  # 元素的边界框 (x1,y1,x2,y2)
        draw.rectangle(bbox, outline="red", width=3)
        draw.text((bbox[0], bbox[1]-20), str(el["idx"]), fill="red")
    img.save(out_path)
```

**bbox 来源**：Playwright 的 `element.bounding_box()` 返回元素在视口里的位置。viewport 固定（L01 的 1280×800）保证截图和 bbox 坐标对齐——这是 L01 强调 viewport 固定的原因之一。

### 视觉成本控制（任务书硬约束）

截图送 VLM 前降采样（宽 ≤1280）：`img.resize((1280, ...))`。图片 token 随分辨率涨，1280 宽够 VLM 看清又不太贵。viewport 已固定 1280，截图基本不需要额外缩。

---

## 4. 三路线同任务对照实验

对同一本地任务（翻页取证），跑三路线，记录成功率/token/耗时：

| 路线 | 观察 | 成功率 | token | 耗时 | 说明 |
|---|---|---|---|---|---|
| 文本 | 元素编号列表 | 实测/mock | 低 | 快 | L04 已跑 |
| 视觉 | SoM 截图 | 实测/mock | 高 | 慢（VLM 推理） | 本课跑 |
| 混合 | 文本+卡住截图 | 实测/mock | 中 | 中 | 本课跑 |

**对照要点**：
- **token**：视觉路线每步送一张图（~几百-上千 token），文本路线每步几百文本 token——视觉贵 N 倍。
- **成功率**：在 DOM 完整的本地页上，文本路线应不输视觉（甚至更好，因为编号精确）；视觉的优势在 DOM 不完整场景。
- **耗时**：VLM 推理比文本 LLM 慢。

> ⚠️ **诚实标注**：无 API key 时三路线均用 mock（视觉路线 mock VLM 的动作输出），标注「mock 演示」。真实 glm-4v-plus 跑出的成功率/耗时见 `--real` 路径，但本地任务上文本路线预计不输视觉——视觉的真正价值在 DOM 不完整的真实复杂页，本地测试页造不出那种复杂度。

---

## 5. 落地清单

本课是视觉路线课，**无 research-assistant 代码改动**（落地在 L09 混合路线）。产出：

| 文件 | 说明 |
|---|---|
| `README.md`（本文件） | 三路线对比 + SoM 导读 + grounding 命门 + 成本控制 |
| `code.py` | SoM 标注 + 视觉路线 agent + 三路线对照实验（mock + 可选 real） |
| `som_demo.png` | SoM 标注图存档（实测产出） |
| `exercise.md` | 练习 |

### 验收

```bash
cd gui-agent-lessons/00_overview/test_pages && python -m http.server 8765

cd gui-agent-lessons/05_vision
python code.py            # mock 三路线对比 + 生成 som_demo.png

# 预期输出：
#  - 生成 som_demo.png（截图上画框编号，存档）
#  - 三路线对照表（成功率/token/耗时，mock 标注）
#  - 文本路线在本地 DOM 完整页上不输视觉（验证落地选混合的依据）
```

> ⚠️ 需 playwright + pillow + L00 服务。视觉路线 mock 不调真实 VLM；`--real` 需 `ZHIPUAI_API_KEY` 且用 glm-4v-plus。

---

## 6. 本课在两条主线上的位置

- **评估主线**：本课产出三路线的 token/耗时对照数据——这是 L11 收益表「文本 vs 视觉」成本列的来源。没有本课的量化，落地选混合就是拍脑袋。本课的「本地任务上文本不输视觉」也是评估主线的一个结论：视觉的收益要专门找 DOM 不完整的场景才能显出来（L08 mini-benchmark 会造这类场景）。
- **观察-行动接口主线**：本课扩展了观察空间——从「元素编号列表」（L02 文本）扩展到「SoM 标注截图」（视觉）。关键统一：SoM 让视觉路线的行动也用 `click(n)` DSL，和文本路线同构——观察空间变了，行动空间不变。混合派是观察空间的「按需切换」：文本观察为主，卡住切视觉观察。

---

## 🎯 面试话术

> 「文本和视觉路线我同任务实测对比过——视觉贵（图片 token 是文本 N 倍）、grounding 难，但处理得了 canvas/DOM 不完整的场景。通用 VLM 的 grounding 命门我用 SoM 解决：截图上画框编号，VLM 答编号不答坐标，和文本派的 click(n) 同构。落地我选混合：文本为主，卡住才花钱截图。我也知道 UI-TARS 这类专用模型为什么强（专训），但 L12 才讨论它会不会淘汰脚手架。」
