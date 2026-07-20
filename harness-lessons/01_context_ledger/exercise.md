# Lesson 01 · 练习

## 练习 1（概念）：归桶判断

以下六段内容进 researcher/writer 调用的 prompt，各归哪一桶（system/task_state/tool_results/history）？说明理由，注意「谁生产的」比「长什么样」更重要：

1. `web_search` 返回的五条搜索摘要
2. 上一轮 reviewer 给的修改意见（feedback）
3. skill_loader 加载的「报告格式规范」正文
4. MemoryStore.recall 命中的三条旧研究结论
5. 「你是研究员。针对子问题……提炼 2-3 句核心发现」这段指令模板
6. TaskLedger 注入的 prior_context（已确认的历史结论）

对照 `nodes.py` 里 `_ledger_measure` 的实际归桶验证你的答案。哪一条你和课程口径不一致？口径本身有唯一正确答案吗——统一口径为什么比「归得对」更重要？

## 练习 2（设计实验）：你的水位阈值该定在哪

课程约定 caution=60%、danger=85%，这不是真理。做一个扫参实验：

```python
from research_assistant import context_ledger as cl
from eval_agent.long_haul import DOC_IDS, SYSTEM_PROMPT, LongHaulSource

def first_zone_hit(caution: float, danger: float, limit=8000):
    cl.SAFE_MAX, cl.CAUTION_MAX = caution, danger   # 实验性改阈值
    src = LongHaulSource(); tools = []; hits = {}
    for no, d in enumerate(DOC_IDS, 1):
        text = src.fetch(d)
        led = cl.WindowLedger(limit=limit)
        rec = led.measure("study", system=SYSTEM_PROMPT,
                          task_state=src.catalog_text(),
                          tool_results="".join(tools) + text)
        hits.setdefault(rec.zone, no)
        tools.append(text)
    return hits

for caution in (0.4, 0.5, 0.6, 0.7):
    print(caution, first_zone_hit(caution, 0.85))
```

1. caution 阈值从 0.4 提到 0.7，「首次告警的源号」怎么移动？结合 L00 的死亡点 S11，每档阈值给压缩留了几源的「操作余量」？
2. 假设一次压缩本身要消耗约 800 token 的窗口（装下摘要指令+被压内容的索引），danger=85% 时还装得下这次压缩吗？由此论证「太晚动手连自救动作都放不下」。
3. 给两类真实场景各选一组阈值并说明理由：a) 每步都很贵的深度研究（单源 3k token）；b) 大量小步快跑的工具型 agent（单步 200 token）。

## 练习 3（设计实验）：份额超标检测器

给账本加一个「份额告警」用法（不改库，只写调用方代码）：researcher 单调用份额 1500 token，超了就打印上游整改建议。

```python
led = cl.WindowLedger(limit=8000)
QUOTA = {"researcher": 1500}
# 跑若干次 measure 后：
for r in led.records:
    if r.node in QUOTA and r.total > QUOTA[r.node]:
        print(f"⚠️ {r.node} #{r.call_no} 超份额：{r.total}>{QUOTA[r.node]}，"
              f"大头在 {max(r.parts, key=r.parts.get)}——该整形还是该外置？")
```

用 L00 的超长文档 S17（≈3,400 token）触发它。回答：超份额时「换更大的窗口」为什么是错误答案？（提示：S17 明天可能是 34,000——上游设计问题下游扛不住。）

## 练习 4（思考）：两笔账的对账

`cost_budget` 在调用**后**从 usage 回执记「钱」，`context_ledger` 在调用**前**从 prompt 记「空间」。假设某天对账发现：回执的 input_tokens 稳定地是账本估算的 1.6 倍。

1. 给出至少两个可能原因（提示：中文 token 密度；框架注入的隐藏内容——工具 schema/消息包装）。
2. 该怎么修：改 FakeTokenizer 的除数？给账本加一个「校准系数」配置？还是在 L09 真模型章记录偏差并只信结构性结论？三种方案各在什么场景下是对的？
