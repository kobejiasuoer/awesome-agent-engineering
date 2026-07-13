# L00 练习

## 练习 1：用三遍读法读一篇 GUI Agent 论文（方法练习）

选一篇课程未细读的 GUI agent 论文（推荐：Mind2Web, Deng et al. 2023, [arXiv:2306.06070](https://arxiv.org/abs/2306.06070)），按第六门课的三遍读法产出笔记：

- 第一遍（5 分钟）：用一句话说它解决了什么问题、什么方法、结果好不好。
- 第二遍（30 分钟）：画出它的核心组件图（输入→处理→输出，观察空间和行动空间分别是什么）。
- 第三遍（复现意图）：写出「最小复现计划」——核心 idea 是什么、最小实现需要哪些组件、消融实验怎么做（去掉观察空间的哪一部分看掉多少）。

**验收**：笔记里第三遍的「最小复现计划」要具体到能照着写代码（不是「实现一个 web agent」，而是「HTML→元素编号列表→click(n) DSL→while 循环」这种粒度），并指出它属于三大流派里的哪一派。

---

## 练习 2：扩展 test_pages，让裸基线暴露更多 gap（设计实验类）

本课的 `test_pages/` 初版只有 index/search/detail 三个页面，gap 表只有 7 行。扩展它让 gap 更完整：

1. **假设**：搜索摘要拿不到的，不止版本号/日期/要点——还有「弹窗拦截后的内容」「慢加载页面的最终态」「需要交互才能显现的字段」。
2. **实验设计**：
   - 在 `test_pages/` 新增 `slow.html`（用 JS `setTimeout` 延迟 2 秒渲染关键内容）和 `popup.html`（页面加载即弹一个 cookie 提示遮罩，需点「同意」才显正文）。
   - 改 `code.py` 的 `run_baseline`，把 gap 表扩到覆盖这两类（慢加载/弹窗后的内容，摘要是否拿得到）。
   - 跑裸基线，确认这两类 gap 也被记录进 `baseline_gui.jsonl`。
3. **预期**：摘要对慢加载的「最终态」和弹窗后的「正文」都拿不到（因为搜索 API 根本不执行 JS、不点弹窗）。

**验收**：`baseline_gui.jsonl` 的 `gap` 字段新增至少 2 项（如 `has_slow_loaded_content`、`has_after_popup_content`，均 `false`）。诚实标注这是 mock 演示还是真实跑出的。

<details>
<summary>提示：慢加载页怎么造</summary>

```html
<div id="late"></div>
<script>
setTimeout(() => { document.getElementById('late').textContent = '2秒后才出现的版本号 v9.9.9'; }, 2000);
</script>
```
搜索 API 不执行 JS，永远看不到 `v9.9.9`；浏览器等 2 秒就能拿到——这正是「会搜索 ≠ 会上网」的又一证据。
</details>

---

## 练习 3：流派归属判断（理解类）

把以下 5 个真实系统/论文归入三大流派（文本派/视觉派/专用模型派），并各用一句话说理由：

1. browser-use（开源 web agent 框架，默认把 DOM 文本喂给 LLM）
2. Anthropic Computer Use（Claude 看截图操作整个桌面）
3. CogAgent（智谱系，高分辨率 GUI 专用 VLM）
4. WebVoyager（早期把截图+SoM 标注喂 GPT-4V 的研究）
5. AutoGLM（智谱网页/手机 agent，端到端专训）

**验收**：每个归属正确，理由点中「观察空间+行动空间」的组合（如「视觉派：观察是截图，行动是坐标/SoM 编号」），而不是泛泛说「因为它看图」。

---

## 练习 4：思考题——为什么不用 browser-use 直接落地（取舍类）

任务书要求「browser-use 等现成 agent 框架只作对比参照，不作实现依赖」。请回答：

1. 直接用 browser-use 落地 research-assistant 的 browse 能力，能省多少代码？省的是什么？
2. 不自己实现会失去什么？（提示：从安全主线——动作白名单/域名 allowlist/敏感动作确认——和评估主线——可复现 mini-benchmark——两个角度想）
3. 这个取舍和第六门课「手写 ReAct 而非直接用 LangGraph 预置 agent」的取舍，是不是同构的？

**验收**：能说出「现成框架省的是脚手架代码，但失去的是对观察/行动/安全层的控制权，而 GUI 场景的安全控制权是压舱石」。并能指出与手写 ReAct 的同构性——「学原理 vs 用轮子」的边界。
