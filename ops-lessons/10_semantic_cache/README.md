# Lesson 10 — 语义缓存：相似问题不重复烧钱

> 本课目标：**用语义缓存让「换个说法的相同问题」命中缓存，跳过检索+生成，降延迟降成本**。
>
> 学完你能回答面试官那句：**「怎么控成本？」**——这是最直接的一招：相似问题不重复调 LLM。

---

## 1. 精确缓存 vs 语义缓存

普通缓存按「key 完全相等」命中。但用户问知识库时，同一个意思有无数种问法：

```
「试用期多久」
「试用期是多长时间」
「试用期有几个月」
「新员工试用期多久」
```

精确缓存这四条是四个不同的 key，全 miss。但它们语义相同，应该返回同一个答案。**语义缓存**用 embedding 相似度判命中——问法不同但意思一样就复用：

| | 精确缓存 | 语义缓存 |
|---|---|---|
| 判定方式 | 字符串完全相等 | embedding 余弦相似度 > 阈值 |
| 「试用期多久」vs「试用期几个月」 | ❌ miss | ✅ hit |
| 实现复杂度 | 简单（dict） | 中（要算向量相似度） |
| 适合 LLM 场景 | 不适合（问法千变万化） | ✅ 适合 |

> 🎯 **核心认知**：LLM 应用的缓存不能用传统 KV 缓存——用户输入是自然语言，自然语言的「相等」是语义相等不是字符相等。语义缓存就是用 embedding 把「语义相等」变成可计算的相似度。

---

## 2. 缓存键设计 + 相似度阈值

语义缓存的核心是「**用问题的 embedding 当 key，用余弦相似度判命中**」：

```
   存：question → embedding(q) → 存 (embedding, answer, sources, ts)
   查：new_q → embedding(new_q) → 和所有存的 embedding 算余弦相似度
                                        │
                                   max_sim > 阈值？
                                   /          \
                                 是            否
                                 │              │
                            返回缓存的 answer   miss → 走正常管线 → 回填缓存
```

### 阈值的权衡（最关键的超参）

| 阈值 | 效果 | 风险 |
|---|---|---|
| 太松（如 0.80） | 命中率高，省钱 | 🚫 把「年假几天」和「病假几天」判同（语义近但答案不同）→ 答错 |
| 太紧（如 0.99） | 几乎不命中 | 🚫 缓存形同虚设，没省到 |
| **0.92~0.95** | 平衡点 | ✅ 只命中真正同义的 |

> 💡 **阈值是经验值**，要拿真实问法调。本课默认 0.92（embedding-3 + cosine），README 验收里让你试不同阈值看命中率/准确率变化。**没有放之四海皆准的阈值**——这是语义缓存最难调的参数。

```
相似度谱（embedding-3, cosine）：
   0.99 ─── 几乎逐字相同：「试用期多久」vs「试用期多久？」
   0.95 ─── 同义换说法：「试用期多久」vs「试用期几个月」     ← 缓存目标区
   0.90 ─── 近义但有风险：「年假几天」vs「年假有几天」       ← 边界
   0.85 ─── 相关但不同：「年假几天」vs「病假几天」           ← 错命中区！
   0.70 ─── 同领域：「年假几天」vs「加班费怎么算」
```

---

## 3. 缓存失效：文档更新后要作废

缓存有一个致命陷阱：**文档更新了，旧答案还在缓存里 = 返回过时信息**。

```
   T1: 问"试用期多久" → 答"3个月" → 缓存
   T2: 上传新文档，试用期改成 6 个月
   T3: 问"试用期多久" → 缓存命中 → 返回过时的"3个月" ❌
```

解法：**文档 ingest 后作废整个缓存**（kb-qa 的 `reset_kb` 已经在文档变更时调用，本课在那里加 `cache.invalidate()`）。粗暴但安全——宁可少命中，不能答错。

> 🎯 **缓存正确性 > 命中率**。语义缓存最大的风险就是「该失效时没失效」。生产级实现可以做更精细的失效（只作废相关 embedding 的缓存），但教学版全量作废最稳。

---

## 4. 缓存与多轮上下文的冲突

另一个坑：**多轮对话里，相同问题在不同上下文答案可能不同**。

```
   轮1: 问"试用期多久" → 答"3个月"
   轮2: 问"那专业版呢" → （追问，依赖上下文=试用期）
   轮3: 又问"试用期多久" → 直接命中缓存？但这次可能是有上下文的追问...
```

本课的解法：**有历史（追问场景）时跳过缓存**。缓存只对「独立问题」生效——这正好和 kb-qa 的 condense-question 逻辑呼应：无历史=独立问题=可缓存；有历史=追问=不缓存（走 condense 改写后正常管线）。

```
   有 past（历史）？ ─是─▶ 跳过缓存（追问依赖上下文，不能复用）
        │
        否
        │
   查语义缓存 ─命中─▶ 返回缓存答案（cache_hit=true）
        │
       miss
        │
   走正常管线（检索+生成）→ 回填缓存
```

---

## 5. 成本/延迟收益

缓存命中时跳过了最贵的两步：

| 步骤 | 耗时 | 成本 | 缓存命中时 |
|---|---|---|---|
| embedding（查缓存用） | ~100ms | 极低（embedding 便宜） | 仍要算（判命中） |
| 检索（BM25+向量+rerank） | ~300-500ms | rerank 调用 | ✅ 跳过 |
| 生成（glm-4 流式） | ~1-2s | **glm-4 token 费**（主要成本） | ✅ 跳过 |

命中一次省：~1.5s 延迟 + 一次 glm-4 调用（约 ¥0.05）。高频问答场景（很多用户问类似问题）命中率能到 30-50%，成本立省。

> 💡 这正是 L02 trace 里记 `cache_hit` 字段的意义——面板能统计「命中率」「缓存省了多少成本」，让缓存收益可量化。

---

## 6. 本课代码会做什么

### `code.py`（教学，零依赖）
- 实现语义缓存核心：embed + cosine 相似度 + 阈值判定 + 回填
- 用 mock embedding 演示「同义问法命中、近义不误命中、文档更新作废」

### 落地到 kb-qa
- 新增 `src/kb_qa/semantic_cache.py`：`SemanticCache`（embedding + cosine + 阈值 + invalidate）
- `config.py`：加 `enable_cache` / `cache_similarity_threshold`
- `service.py`：`stream_ask` 入口查缓存（无历史时），miss 走管线后回填；命中时 `done` 事件标 `cache_hit=true`
- `service.py` 的 `reset_kb`：文档变更时调 `cache.invalidate()`
- `tests/test_semantic_cache.py`：测命中/不误命中/失效（全 mock embedding）

---

## 7. 跑起来

### 教学代码（零依赖）

```bash
cd ops-lessons/10_semantic_cache
python code.py
```

预期：演示同义问法命中（第二次相似问题 cache_hit）、近义不误命中、文档更新作废。

### 落地验证（kb-qa）

```bash
cd portfolio-projects/knowledge-base-qa
python -m pytest tests/test_semantic_cache.py -q
# 真实命中（需 API key）：连问两次相似问题，第二次日志标 cache_hit=true
python -c "
import asyncio, sys
sys.stdout.reconfigure(encoding='utf-8')
from kb_qa.service import stream_ask
async def go():
    async for _ in stream_ask('试用期多久', 't1'): pass
    print('--- 第二次（相似问法）---')
    async for ev in stream_ask('试用期是几个月', 't2'):
        if ev['event']=='done': print('cache_hit=', __import__('json').loads(ev['data']).get('cache_hit'))
asyncio.run(go())
"
```

---

## 🎯 面试话术

> 「我加了语义缓存：用问题的 embedding 余弦相似度判命中，阈值 0.92——同义问法（『试用期多久』vs『试用期几个月』）命中后跳过检索+生成，直接返回缓存答案。有历史（追问）时跳过缓存避免上下文冲突；文档 ingest 后全量作废缓存防过时。命中一次省 ~1.5s 延迟和一次 glm-4 调用，高频问答场景命中率能到 30-50%。」

---

## 落地清单

| 文件 | 改动 | 如何验证 |
|---|---|---|
| `src/kb_qa/semantic_cache.py` | **新增**：`SemanticCache`（embed+cosine+阈值+invalidate+回填） | `python -c "from kb_qa.semantic_cache import SemanticCache; print('ok')"` |
| `src/kb_qa/config.py` | 加 `enable_cache` / `cache_similarity_threshold` | — |
| `src/kb_qa/service.py` | 入口查缓存（无历史时）；miss 回填；命中标 cache_hit；reset_kb 作废缓存 | done 事件含 cache_hit 字段 |
| `tests/test_semantic_cache.py` | **新增**：命中/不误命中/失效（全 mock embedding） | `pytest tests/test_semantic_cache.py -q` 全绿 |

下一课 [Lesson 11 — 压测与并发](../11_loadtest/) 量化服务的 QPS 天花板。
