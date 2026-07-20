# Lesson 06 · 练习

## 练习 1（设计实验）：崩溃点扫参——工作区的保值曲线

```python
import tempfile
from eval_agent.harness_runs import run_workspace_longhaul
for crash in (3, 10, 18, 25, 29):
    r = run_workspace_longhaul(workspace_base=tempfile.mkdtemp(), run_id=f"c{crash}",
                               crash_at=crash)
    saved = r["refetch_waste_without_ws"] - r["total_fetches"]
    print(f"崩溃于 S{crash:02d} → fetch {r['total_fetches']}（无工作区 "
          f"{r['refetch_waste_without_ws']}），省 {saved} 次，完成 {r['completed_sources']}/30")
```

1. 画「崩溃点-节省量」曲线。越晚崩溃省得越多——这说明工作区的价值和什么成正比？对照课程十 L06 的 catch-up（「补最近一班就够」）：两边的「恢复经济学」有什么不同（提示：那边世界状态以最新为准、旧班次无需补；这边每源劳动都是不可替代的资产）？
2. 把 crash_at 换成连环崩溃（跑 5 源崩一次、共崩 5 次）改造 runner 验证：fetch 总数仍是 30 吗？「有笔记=已研完」的判定在什么条件下会失效（提示：崩在 add_note 之前——研完了但笔记没落盘）？
3. 由 2 设计「至多重做一源」的保证：note 落盘与结论产出的顺序该怎么排？这和课程九幂等发布的「先登记后执行还是先执行后登记」是同一个问题吗？

## 练习 2（实现）：读回整形——外置不是免费回读

writer 合成时想核查 S07 与 S23 的矛盾细节，从工作区读回两篇原文。直接 `ws.read()` 会把 2,000+ token 灌回窗口——违背整课的努力。实现 `read_shaped(ws, rel_path, query, budget_tokens)`：

1. 组合 L04 的板斧：优先检索式（query 命中段±100 字），fallback 截断+显式标记；返回值带指针（「全文见 …」）。
2. 用它读回 S07/S23 验证矛盾对（F06/F16 的 probe 都要在返回值里），并量出窗口开销 vs 全文读回的对比。
3. 思考：什么时候必须全文读回、不能省（提示：法务审查/逐字引用场景）？这时候该用什么机制保护主窗（提示：L05——派个子代理去读全文，回传核查结论）。

## 练习 3（设计实验）：recitation 的频率与位置

现在是「后半程每步复述」。做两个变体实验并对比机械开销：

A）全程每步复述（S01 起）；B）只在每 5 源的边界复述；C）不复述（L05 现状）。

1. 三档的复述次数与 token 开销各是多少（改 runner 的 `no > SESSION_SPLIT` 条件即可）？
2. mock 测不出「漂移改善」，但可以推理：任务前半程窗口还浅（目标离尾部近），复述的边际价值低——用 lost-in-the-middle 的「首尾高、中段低」解释为什么「后半程才复述」是合理的默认。
3. 复述块该放窗口哪里？本课放 task_state（尾部）。如果放 system（头部）会怎样——结合 L02 压缩的「system 不可压」与 KV 缓存（前缀稳定=缓存友好）分析两种放法的代价。

## 练习 4（思考）：工作区的治理

工作区是文件，就有文件的全部麻烦：

1. **膨胀**：30 源 91k 字已落盘；长期运行的 agent 一个月攒 500 个 run 目录。写三条清理策略（按 run 年龄/按引用计数/归档压缩），并说明哪些文件永远不能自动删（提示：被 memory_files 或审计行引用的）。
2. **并发**：两个 run 同时写同一 run_id 会怎样？「run_id 唯一性由谁保证」——对照课程九 jobs 注册表的做法给出方案。
3. **敏感内容**：sources/ 里落盘的原文可能含密钥或隐私（L03 练习 2 的延长线）。落盘前扫描？目录加密？还是 .gitignore 兜底？给出你的分层方案——并检查本仓库：课程运行产物该不该进 .gitignore（这正是 L09 收官清单的一项）。
