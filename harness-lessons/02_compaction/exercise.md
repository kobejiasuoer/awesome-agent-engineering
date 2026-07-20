# Lesson 02 · 练习

## 练习 1（设计实验）：触发水位的经济学

「进警戒区就压」是课程约定。扫参验证它：

```python
from eval_agent.harness_runs import run_compacted_longhaul
for th in (0.30, 0.45, 0.60, 0.75, 0.90):
    r = run_compacted_longhaul(register_pins=True, threshold_pct=th)
    print(th, "→ 压缩次数:", r["compactions"], "丢弃项:", r["dropped_total"],
          "峰值:", r["peak_window_tokens"], "计费:", r["tokens_billed"],
          "在场:", r["presence"])
```

1. threshold 从 0.30 提到 0.90：压缩次数、单次丢弃量、峰值窗口各怎么变？画出「整理税（压缩次数）vs 单次损失量（丢弃项/次）」的取舍。
2. **陷阱题**：0.30 档触发了 26 次压缩，丢弃总量却和 0.60 档差不多，峰值反而更高——检查 threshold（触发线）与 target（目标线，默认 0.50）的大小关系，解释这些压缩为什么在「空转」。由此写出参数的健康约束（threshold 与 target 谁必须大、至少差多少才值得压一次），并给 Compactor 提一个防呆改进。
3. 0.90 档的峰值离 8k 还剩多少余量？结合「压缩过程本身要占窗口」论证：把 threshold 推到 0.9 以上，什么情况下会当场爆窗？
4. 在场率在所有档位都是 20/20——为什么触发时机影响的是成本与风险，而不是登记项的存活？（答案应指向：存活由登记契约保证，与何时压无关——这正是契约的意义。）

## 练习 2（设计实验）：摘要器质量的敏感性

对照组证明了「不登记」的下场。现在反过来：登记不变，摘要器从「留前 80 字」换成更好/更坏的实现，观察什么变、什么不变：

```python
from eval_agent.harness_runs import run_compacted_longhaul

def better_summarizer(texts):   # 假装更聪明：每段留前 200 字
    return "（摘要）" + " / ".join(t[:200] for t in texts)

def evil_summarizer(texts):     # 最坏情况：全丢
    return "（摘要）无。"

for name, s in [("head80", None), ("head200", better_summarizer), ("evil", evil_summarizer)]:
    r = run_compacted_longhaul(register_pins=True, summarizer=s)
    print(name, "→ 在场:", r["presence"], "峰值:", r["peak_window_tokens"],
          "压缩:", r["compactions"])
```

1. 三种摘要器下在场率都是 20/20——解释「契约层」与「质量层」的分工：摘要器质量影响的是**未登记内容**的残存信息量与窗口占用，不影响契约。
2. evil 摘要器下峰值反而更低——「摘要越差越省窗口」是好事吗？给出一个 evil 摘要器会造成实际伤害的场景（提示：报告需要引用未登记的背景细节时）。
3. 由此设计：如果只能监控一个指标来发现「摘要器变坏了」，你选什么？（在场率显然不行——它永远 20/20。）

## 练习 3（设计实验）：登记漏报——纪律的边界

纪律保证「登记的必活」，不保证「该登记的都登记了」。模拟一个只登记一半事实的「粗心判定器」：

```python
from eval_agent import harness_runs
from eval_agent.long_haul import KEY_FACTS

# 只登记 fact_id 为偶数的事实（F02/F04/…）——模拟 LLM 判定漏报 50%
full = harness_runs._FACTS_BY_DOC
harness_runs._FACTS_BY_DOC = {
    d: [f for f in fs if int(f.fact_id[1:]) % 2 == 0] for d, fs in full.items()
}
r = harness_runs.run_compacted_longhaul(register_pins=True)
harness_runs._FACTS_BY_DOC = full   # 恢复
print("漏报一半 → 在场:", r["presence"], "矛盾可发现:", r["contradiction_discoverable"])
```

1. 预测再验证：在场率是多少？矛盾对（F06 奇 / F16 偶）还可发现吗？
2. 这暴露了登记式压缩的真正软肋：**判定召回率**。给出两个工程上提高登记召回的手段（提示：宁多勿漏的登记倾向+定期全量校准；或者让「未登记但被丢」的内容保留可追溯指针——L06 的原文落盘正是终极解法）。
3. 对比三种失败模式的危害排序并说明理由：a) 登记漏报（本题）；b) 不登记纯摘要（对照组）；c) 硬截断（L00 A3）。

## 练习 4（思考）：压缩与 KV 缓存的紧张关系

压缩改写了窗口前缀——这会让 API 的 prompt cache 大面积失效（Manus 把 KV-cache 命中率当北极星指标，因此主张「只追加不改写」的上下文）。

1. 本课的压缩每次触发都重写窗口，缓存视角这是灾难。给出两个缓解设计（提示：压缩频率与缓存失效成本的权衡——攒大批次少压几次；或分段缓存——system/目录段永不改写，只重写可变段）。
2. 「只追加不改写」流派（Manus）与「登记压缩」流派（本课）各自的适用条件是什么？当任务长到追加必然爆窗时，前者靠什么活（提示：文件外置+窗口重建，而不是窗口内改写）？这为 L06 埋了什么伏笔？
