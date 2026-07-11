# Lesson 02 — 反思式写入与巩固：记忆不是录像是提炼

> 本课目标：**解决「存什么」——手写反思式写入（reflect_and_store）让 Agent 自己提炼值得记的东西，手写巩固（consolidate）把多条情景记忆归纳成语义结论，加遗忘策略防止记忆库膨胀。**

学完你能回答：**「Agent 记忆存什么？全存对话历史不行吗？」**——全存会淹没检索，记忆是提炼不是录像。

---

## 0. 起点：L01 的遗留问题

L01 建了 MemoryStore，能 remember + recall。但 L01 的 `remember` 存的是**原始内容**——researcher 产出的 finding 原文直接塞进去。这有两个问题：

1. **噪音淹没**：一次研究产出 3-5 条 finding，每条几十字，混着来源标记、格式符号。下次 recall 时这些噪声会降低命中率。
2. **没有沉淀**：多次研究同一主题，情景记忆越积越多，但没有从多条记录里**归纳出结论**——每次都得 recall 一堆原始片段让 LLM 重新综合。

本课解决这两个问题：①写入时就提炼（反思式写入）；②定期把多条归纳成一条（巩固）。

---

## 1. 记忆不是录像

### 录像 vs 提炼

```
录像式（全存）                     提炼式（反思式写入）
─────────────                     ──────────────────
存：原始对话/finding 全文          存：LLM 提炼的"学到了什么"
密度：低（含格式/来源/噪声）        密度：高（只有复用价值的信息）
检索：被噪声淹没                   检索：命中精准
量：线性增长，爆炸                  量：每次 3-5 条，可控
```

> 🎯 **核心认知**：记忆的价值不在"记了多少"，在"记的是不是值得复用的高密度信息"。一段 200 字的 finding，可能只有一句话值得记——"MCP 基于 JSON-RPC 2.0"。录像式存 200 字，提炼式存一句话。下次 recall 时，前者要在 200 字噪声里找，后者直接命中。

### Generative Agents 的 reflection tree

> **论文**：Generative Agents: Interactive Simulacra of Human Behavior（Park et al. 2023, [arXiv:2304.03442](https://arxiv.org/abs/2304.03442)）

**一句话说它证明了什么**：让 Agent 定期对自己的经历做反思（"我最近观察到的重要事情是什么"），生成更高层级的抽象记忆，形成"情景→反思→更深层反思"的反思树，能让 Agent 在需要时调回更结构化的认知而非原始流水账。

论文里的反思树是**多层**的：第 0 层是原始观察，第 1 层是对观察的反思，第 2 层是对反思的反思……每上一层，信息更抽象、更可复用。本课实现的是**两层**（情景→语义），是最小但够用的版本：

```
第 0 层（情景记忆）：每次研究的原始发现 → reflect_and_store 提炼后存入
                          ↓ consolidate（定期巩固）
第 1 层（语义记忆）：多条情景归纳成一条结论 → 高密度、可复用
```

---

## 2. 流派对比

**问题**：记忆写入时存什么？

| 流派 | 做法 | 取舍 |
|---|---|---|
| ① 全存 | 原始对话/finding 全存 | ✅ 不丢信息；🚫 检索被噪音淹没、量爆炸 |
| ② 规则抽取 | 用正则/关键词模板抽要点 | ✅ 便宜可控；🚫 脆，开放场景覆盖不了 |
| ③ 反思式写入（本课选它） | LLM 回答"这次学到了什么"生成结构化条目 | ✅ 灵活、密度高；🚫 依赖 LLM 质量、有成本 |

**选 ③ 的理由**：研究助手的发现是开放文本（不像日志有固定格式），规则抽不干净。LLM 提炼能处理任意内容，而且我们已经有 smart_llm（glm-4），成本可控（每次研究只调一次反思，不是每个 token 都调）。降级路径：LLM 不可用时回退到规则抽取（取含"发现"关键词的行），不丢记忆只是质量低些。

---

## 3. 手写 reflect_and_store

### 核心逻辑

```python
def reflect_and_store(trajectory, topic, store, llm):
    # 1. 把轨迹整理成文本
    traj_text = format(trajectory)
    # 2. 让 LLM 提炼 3-5 条记忆条目
    #    prompt: "提炼值得下次复用的，格式：内容 | 置信度 | 类型(事实/方法/结论)"
    resp = llm.invoke(reflect_prompt)
    # 3. 解析每行，写入 MemoryStore
    for line in resp:
        content, confidence, mem_type = parse(line)
        store.remember(f"[{mem_type}·置信{confidence}] {content}", topic)
```

### 关键设计：结构化记忆条目

每条提炼的记忆带两个元数据：
- **置信度（0-1）**：LLM 自评这条记忆有多可信（有来源支撑→高，推断→低）
- **类型（事实/方法/结论）**：事实=可验证的客观信息，方法=怎么做某事，结论=综合判断

这两个元数据在 L05 的冲突检测里有用：高置信事实与新信息冲突时才触发修正，低置信的可以安静替换。

### 降级路径

```python
if llm is not None:
    # LLM 提炼
else:
    # 规则降级：取含"发现"的行，前 5 条
    findings_lines = [l for l in traj_text if "发现" in l][:5]
```

> ⚠️ **诚实标注**：规则降级的质量明显低于 LLM 提炼——它只能机械抓"发现"关键词，理解不了语义。生产必须开 LLM；降级只保证"机制不崩"，不保证"质量好"。

---

## 4. 巩固（consolidate）：多条情景 → 一条语义

### 类比人脑的记忆巩固

人睡眠时，海马体会把白天的情景记忆（今天发生了什么）重新激活，提炼成语义记忆（学到了什么），存入大脑皮层。这个过程叫**记忆巩固（memory consolidation）**。

我们的 `consolidate` 做同样的事：

```python
def consolidate(self, llm=None):
    # 1. 按主题分组所有情景记忆
    groups = group_by_topic(all_episodic)
    # 2. 每组让 LLM 归纳成一条语义结论
    for topic, mems in groups:
        conclusion = llm.invoke(f"归纳这{len(mems)}条记录的结论：{mems}")
        self.add_semantic(topic, conclusion, evidence, confidence)
```

### 巩固的触发时机

本课在 `service.py` 每次研究结束后调用 `consolidate`（和 reflect_and_store 一起）。这对应"每次经历后巩固"。更真实的做法是**定期**巩固（如每 N 次研究、或低峰期批量），但本课简化为每次都做——量不大时开销可接受。

### 巩固前后的检索差异

```
巩固前：recall("MCP 协议") → 命中 3 条情景记忆（各自独立的事实片段）
巩固后：recall("MCP 协议") → 命中 1 条语义结论（已综合 3 条情景）+ 情景
         语义结论密度更高，LLM 直接可用，不用自己再综合
```

---

## 5. 遗忘策略

### 为什么需要遗忘

不遗忘的记忆库会无限膨胀：
- 检索变慢（向量库越大查询越慢）
- 噪音累积（旧的不准确信息淹没新的）
- 成本上升（每次 recall 返回一堆过时记忆）

### 遗忘规则

```python
def forget(self, max_episodic, decay_days):
    for mem in all_episodic:
        age = now - mem.timestamp
        # 淘汰条件：太旧 且 从没被 recall 过（没人需要它）
        if age > decay_days and mem.retrieval_count == 0:
            remove(mem)
    # 超上限：按 (检索频次, 新鲜度) 排序，保留 top-N
    if len(kept) > max_episodic:
        sort by (retrieval_count, timestamp) desc
        keep top max_episodic
```

两个维度：
- **时间衰减**：超过 `memory_decay_days` 天且未被检索的淘汰（没人用的旧记忆）
- **频次保留**：超上限时，被检索多的优先保留（常用的记忆价值高）

> 🎯 **只遗忘情景记忆，不遗忘语义记忆**：语义记忆是沉淀的结论，量小价值高，且已经是"巩固后"的精华——再遗忘就没意义了。情景记忆是原料，归纳成语义后就可以淘汰原始片段。

### config 配置

```python
memory_max_episodic: int = 100     # 情景记忆上限
memory_decay_days: float = 30.0    # 衰减天数
```

---

## 6. 落地清单

### 改了哪些文件

| 文件 | 改动 | 说明 |
|---|---|---|
| `src/research_assistant/memory.py` | 新增 `reflect_and_store` | 反思式写入：LLM 提炼记忆条目 |
| `src/research_assistant/memory.py` | `consolidate` 已支持 LLM（L01 留的接口） | 多条情景→一条语义结论 |
| `src/research_assistant/memory.py` | `forget` 实现 | 时间衰减 + 频次保留 |
| `src/research_assistant/service.py` | invoke + stream 研究后触发 reflect + consolidate + forget | 异步、失败降级不阻塞主流程 |
| `tests/test_memory.py` | +6 个测试 | reflect_and_store / 遗忘策略 |

### 如何验证

```bash
cd portfolio-projects/research-assistant

# 1. 全量测试（25 原有 + 18 记忆 = 43 全绿）
.venv/Scripts/python.exe -m pytest tests/ -q
# 预期：43 passed

# 2. 演示反思式写入
cd ../../frontier-lessons/02_reflection_write
PYTHONIOENCODING=utf-8 ../../.venv/Scripts/python.exe code.py
# 预期：原始 findings → LLM 提炼 → 结构化记忆条目；对比"存原文 vs 存提炼"的检索质量

# 3. 真实跑（需 API key + ENABLE_MEMORY=true）
# 跑一次研究后检查 memory_store/ 库里是提炼条目而非原文
```

---

## 7. 本课在两条主线上的位置

- **评估主线**：本课引入了"记忆质量"的概念——提炼 vs 全存的检索质量差异。但**还没量化**。L09 的 harness 会对比"全存记忆 vs 反思式记忆"在硬任务上的指标差异（recall 命中率、报告增量价值）。
- **上下文工程主线**：反思式写入是上下文工程的**写侧**——"该往外部存储写什么"。L01 的 recall 是**读侧**（"该从外部存储调回什么"）。读写两侧合起来才是完整的"上下文外置与按需调回"。巩固则是"外部存储内部的压缩"——把多条低密度情景压成一条高密度语义，减少未来调回时的上下文消耗。

---

## 🎯 面试话术

> 「记忆写入我用反思式提炼而非全存——任务结束让 LLM 回答"这次学到了什么值得复用"，生成带置信度和类型的结构化条目。多条情景记忆定期巩固成语义结论，就像人睡眠时的记忆巩固。还有遗忘策略：时间衰减加频次保留，只淘汰旧且没人用的。这样检索才不会被噪音淹没——记忆是提炼，不是录像。」
