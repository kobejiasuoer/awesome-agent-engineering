# Lesson 10 练习

> 改 `code.py` 里的代码，运行 `python code.py` 观察变化。本课零外部依赖。

---

## 练习 1：调阈值感受「命中率 vs 准确率」权衡

把 `threshold` 从 0.92 调成 0.80 和 0.99，分别跑演示 1 和 2：

```python
cache = SemanticCache(mock_embed, threshold=0.80)  # 试 0.80 / 0.99
```

观察：
- 0.80：演示 2 的「年假 vs 病假」会不会误命中？（相似度 0.5，不会；但更近的「年假几天」vs「年假有几天」呢）
- 0.99：演示 1 的同义问法还能命中吗？（几乎只有逐字相同才命中）

**思考**：阈值是语义缓存最关键的超参——**没有标准答案，要拿真实问法分布调**。生产里通常先收集一批真实问答对，人工标注「哪些该命中」，再找准确率最高的阈值。

---

## 练习 2：实现「按文档作废」而非全量作废

现在 `invalidate()` 全量清空。改进：只作废和「更新文档」相关的缓存条目。

提示：缓存条目存「命中时召回的 source 列表」，文档更新时只作废 source 含该文档的条目：

```python
def invalidate_by_doc(self, doc_source: str) -> int:
    before = len(self._store)
    self._store = [e for e in self._store if doc_source not in e.get("sources", [])]
    return before - len(self._store)
```

**思考**：精细失效提升命中率（只作废相关条目），但实现复杂、且「相关」判断可能漏（一个问题跨多文档）。全量作废粗暴但安全。**工程权衡：正确性优先，先全量，量大了再精细**。

---

## 练习 3：加缓存过期时间（TTL）

缓存除了文档更新要作废，还应有 TTL（生存时间）——即便文档没更新，太久没问的问题也该淘汰，避免缓存无限膨胀：

```python
def get(self, question):
    now = time.time()
    self._store = [e for e in self._store if now - e["ts"] < self.ttl]  # 过期淘汰
    # ... 再查相似度
```

**思考**：TTL 解决两个问题——① 内存无限增长 ② 知识库悄悄变了但没触发 ingest（外部直接改文件）。生产缓存必有 TTL + 上限条数（LRU 淘汰）。

---

## 绋试 4（进阶）：用真实 embedding-3 替换 mock

本课的 `mock_embed` 是词袋。落地版 `kb_qa/semantic_cache.py` 用真实 `ZhipuAIEmbeddings`。如果你有 API key，对比两者的相似度判断：

```bash
cd portfolio-projects/knowledge-base-qa
python -c "
import sys; sys.path.insert(0,'src')
from kb_qa.semantic_cache import SemanticCache
c = SemanticCache(threshold=0.92)
# put 一个，再用同义问法 get
"
```

**思考**：真实 embedding 比词袋准得多（理解「试用期多久」和「试用期是几个月」语义等价，不靠同义词表）。这也是为什么语义缓存要用 embedding 而非规则——**embedding 是语义的通用编码**，不需要手工列同义词。

---

## ✅ 完成本课后，你应该能回答

1. 精确缓存为什么不适合 LLM 应用？语义缓存怎么解决？
2. 相似度阈值太松/太紧各有什么后果？为什么没有标准答案？
3. 文档更新后为什么要作废缓存？全量作废 vs 精细作废怎么选？
4. 多轮对话里为什么有历史时要跳过缓存？
5. 缓存命中省了哪两步？各占多少延迟/成本？
6. （落地）kb-qa 的 stream_ask 在哪里查缓存？reset_kb 在哪里作废缓存？
