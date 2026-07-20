# Lesson 05 · 练习

## 练习 1（设计实验）：子窗份额的甜点位

子窗预算决定「谁能被干完」。扫参找甜点：

```python
from eval_agent.harness_runs import run_isolated_longhaul
for sub in (500, 900, 1200, 2000, 3000, 3500, 4000):
    r = run_isolated_longhaul(sub_window_tokens=sub)
    print(sub, "→ 完成:", r["completed_sources"], "失败:", r["failed_sources"],
          "在场:", r["presence"], "子窗峰值:", r["sub_peak_tokens"])
```

1. 画出「预算-失败源数」阶梯。每个台阶对应语料里的哪一批文档（对照 L00 的普通源 350–700 / 超长 2,800–3,400）？
2. 3,500 与 4,000 两档结果相同——最小安全预算由谁决定？写出公式（最大文档 + 指令开销 + 余量），并回答：如果明天来了一篇 6,000 token 的文档，你调预算还是开整形（练习 2 的组合）？两种选择的失败形态各是什么？
3. 「把子窗预算设成主窗一样大（8k）」有什么隐性代价？（提示：N 个子代理并行时的总 token 吞吐、以及「预算宽=浪费无感知」——份额的意义正是让超支可见。）

## 练习 2（设计实验）：组合矩阵——隔离 × 整形 × 登记

三个机制两两组合，跑一张 2×2 的诚实对照：

```python
from eval_agent.harness_runs import run_isolated_longhaul, run_compacted_longhaul
rows = [
    ("只隔离(1200)", run_isolated_longhaul(sub_window_tokens=1200)),
    ("隔离+整形(1200)", run_isolated_longhaul(sub_window_tokens=1200, shape_in_sub=True)),
    ("只压缩(登记)", run_compacted_longhaul(register_pins=True)),
    ("隔离(4000)", run_isolated_longhaul(sub_window_tokens=4000)),
]
for name, r in rows:
    peak = r.get("main_peak_tokens", r.get("peak_window_tokens"))
    print(f"{name:>14} | 完成 {r['completed_sources']}/30 | 主窗 {peak:,} "
          f"| 在场 {r['presence']} | 计费 {r['tokens_billed']:,}")
```

1. 四行里哪一行是「全指标最优」？它有软肋吗（提示：看 L00 的关键事实是谁登记的——隔离档的事实靠 worker 提炼进结论，worker 判定漏了怎么办？对照 L02 练习 3 的「登记漏报」）。
2. 给「隔离档」补一个 pinned 兜底：worker 结论里的事实同时登记进 Compactor 的 pinned 表——什么场景下这层冗余会救命？（提示：主窗未来也要压缩时——L09 的全套档。）
3. 用这张表回答一个架构问题：预算充足时先上哪个机制？预算紧张时先上哪个？写出你的决策树。

## 练习 3（实现）：批量子代理与失败率熔断

现在是一源一子代理、串行跑。实现 `run_batched(doc_ids, batch_size=5)`：

1. 每批 5 个子代理「并行」（用 asyncio.gather 或顺序模拟均可），批间检查失败率：**连续两批失败率 ≥ 50% → 熔断停止派发**，剩余源标注「未派发（熔断）」。
2. 熔断的失败注记和子代理自身的失败注记必须可区分（「没派」「派了没干成」「干成了」三态）。这与 agent-ops 的熔断器（breaker.py）什么关系——复用还是重写？说明理由。
3. 思考：什么真实故障会让子代理成批失败（提示：信源整体宕机/预算配错/worker 代码 bug）？熔断替你省下的是什么——钱、时间，还是「30 条一模一样的失败注记淹没报告」的注意力？

## 练习 4（思考）：结论 schema 的设计权衡

本课 worker 的结论 schema 是「标题+事实原句列表」。三个变体：
A）只回传事实 id 列表（最省，主窗自己查 KEY_FACTS 表）；
B）回传事实原句 + 一段 100 字的自由综述；
C）回传原句 + 综述 + 三条「值得深挖的线索」。

1. 三个变体的主窗成本各是多少量级？跨源矛盾发现能力有差别吗（提示：A 变体主窗里没有「原句」，probe 探测会失败——机械在场率和实际可用性在 A 上分道扬镳，说明了度量的什么局限）？
2. 「线索」字段（C）会诱发什么行为（提示：主窗看到线索→派新子代理→递归研究）？这是特性还是失控风险？用课程九的步数预算语言给它上笼头。
3. 给你的生产系统写一版结论 schema（字段+每字段的窗口预算），并标注哪个字段是「宁可超预算也不能省」的。
