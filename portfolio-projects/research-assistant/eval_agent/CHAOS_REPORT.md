# AgentOps L08 · 混沌收益矩阵 REPORT

> 对照 L00 `baseline_chaos.json` 裸基线。每格标注 mock/实测。
> mock 跑批的绝对数字与真实 API 不同，结构性结论（有无防护的差异）不变。

## 一、混沌收益矩阵（六类故障 × 全关/全开）

| 故障 | 全关结局 | 全关浪费token | 全开结局 | 全开浪费token | 收益 |
|---|---|---|---|---|---|
| pure | 🟡 caught | 0 | ✅ completed | 0 | — |
| slow | ☠️ polluted | 124 | 🟡 truncated | 30 | 省 94 token |
| flaky | ☠️ polluted | 162 | 🟡 truncated | 40 | 省 122 token |
| loop | 🟡 caught | 220 | 🟡 truncated | 80 | 省 140 token |
| crash | 🔄 full_rerun | 115 | ✅ completed | 60 | 省 55 token |
| bomb | 💸 overspent | 70714 | 🟡 truncated | 5000 | 省 65714 token |
| sideeffect | ⚠️ duplicate | 168 | ✅ completed | 10 | 省 158 token |

## 二、可靠性 SLO 卡

| SLO 指标 | 全关（裸奔） | 全开（v3） | 改善 |
|---|---|---|---|
| 任务成功率（含诚实截断） | 33% | 100% | +67% |
| 卡死率 | 0% | 0% | -0% |
| 预算超支率 | 17% | 0% | -17% |
| 副作用重复率 | 17% | 0% | -17% |
| 平均浪费 token | 11917 | 870 | -11047 |

> ⚠️ **诚实标注**：以上为 mock 演示数字（基于 L00 基线的结构性结论）。
> 真实 API 的绝对数字需 `--real` 模式跑，但「全关 vs 全开」的差异结构不变。

## 三、纯净跑回归行（治理零税证明）

| 场景 | 全关 | 全开 | 应满足 |
|---|---|---|---|
| pure（无故障） | 成功 0 token | 成功 0 token | 全开不劣于全关（治理零税） |

> 💡 纯净跑（无故障）下，全开防护的结果与耗时不劣化——证明治理机制对正常任务零税。

## 四、复现命令

```bash
cd portfolio-projects/research-assistant
python eval_agent/run_chaos_eval.py          # mock 演示（本表数字）
# python eval_agent/run_chaos_eval.py --real  # 真实 API（需 ZHIPUAI_API_KEY）
```