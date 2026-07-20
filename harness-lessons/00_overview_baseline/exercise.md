# Lesson 00 · 练习

## 练习 1（概念）：四种死法的现场辨认

四种死法——硬溢出、截断失忆、迷航、中毒——各举一个你在真实使用 AI 编程助手/深度研究工具时可能遇到的具体场景，并回答：

1. 为什么说「截断失忆」比「硬溢出」更危险？（提示：从「谁知道出了事」的角度想——A2 和 A3 哪个的报告会被人当真？）
2. 四种死法里哪两种是 FakeLLM 演不出来的？为什么本课程坚持把「mock 能测什么/不能测什么」写在结论旁边，而不是只报好看的数字？

## 练习 2（设计实验）：窗口翻倍，能多活几源？

「大窗口硬扛」流派的隐含承诺是：窗口够大就不用 harness。用实验检验它的成本曲线：

```python
from eval_agent.long_haul import run_naive_longhaul
for limit in (4000, 8000, 16000, 32000):
    r = run_naive_longhaul("enforce", window_limit=limit)
    print(limit, "→ died_at:", r["died_at"], "completed:", r["completed_sources"],
          "billed:", r["tokens_billed"])
```

1. 记录死亡点随窗口的移动。窗口每翻一倍，大约多活几源？为什么不是线性的两倍？（提示：观察 S05/S17/S28 三篇超长文档落在哪个区间。）
2. 32k 窗口下裸奔能跑完 30 源吗？如果任务变成 100 源呢？由此写一句话反驳「窗口够大就不用 harness」。
3. 对比各档 `tokens_billed`（每轮重付全窗的口径）：窗口变大后，「活得更久」的每一源边际成本发生了什么？这解释了为什么大窗口流派「贵」不只贵在单价。

## 练习 3（设计实验）：截断的帕累托——活着 vs 记得

```python
from eval_agent.long_haul import run_naive_longhaul
for tc in (200, 500, 900, 1500, 3000):
    r = run_naive_longhaul("hard_truncate", truncate_chars=tc)
    print(tc, "→ peak:", r["peak_window_tokens"], "presence:", r["presence"],
          "contradiction:", r["contradiction_discoverable"])
```

1. 画出 truncate_chars 从 200 到 3000 的「峰值窗口 vs 在场率」取舍表。哪一档开始触碰 8k 物理限制？哪一档起矛盾对重新可发现（F16 埋点约在 S23 全文 62% 深度处）？
2. 存在某个 truncate_chars 让「峰值 < 8k 且在场率 = 20/20」吗？用埋点契约（12 条 late 事实在 60% 深度之后）解释为什么**均匀硬截断**在这个任务上没有帕累托最优解——这正是 L02 登记压缩与 L04 显式省略要解决的问题。

## 练习 4（思考）：计费口径的诚实性

本课的 `tokens_billed` 按「每轮重付全窗、无 KV 缓存减免」计。查一下你所用 LLM API 的 prompt caching 定价（例如缓存命中价通常是全价的 10% 左右），然后回答：

1. 有缓存时，A1 裸奔 378,889 的账单大约会缩到什么量级？（粗算即可：每轮的「旧前缀」按缓存价、新增部分按全价。）
2. 缓存能救「成本」，能救「窗口装不下」吗？能救「迷航」吗？由此区分：KV 缓存优化的是**价格**维度，harness 优化的是**空间与注意力**维度——为什么 Manus 把 KV-cache 命中率当北极星指标，却仍然要做文件外置与 recitation？
