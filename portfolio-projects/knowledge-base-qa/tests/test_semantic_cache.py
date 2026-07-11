"""语义缓存单测：命中 / 不误命中 / 失效 / TTL（LLMOps L10）。

全程不打真实 API：用确定性 fake embed_fn（手工构造向量）控制相似度。
"""
from __future__ import annotations

import time

from kb_qa.semantic_cache import SemanticCache, _cosine


def test_cosine_basic():
    """cosine：相同向量=1，正交=0，相反=-1。"""
    assert _cosine([1, 0], [1, 0]) == 1.0
    assert _cosine([1, 0], [0, 1]) == 0.0
    assert _cosine([1, 0], [-1, 0]) == -1.0


def test_cache_miss_then_put_then_hit():
    """首次 miss，put 后同问题 hit。"""
    cache = SemanticCache(embed_fn=lambda q: [1.0, 0.0], threshold=0.9)
    hit, ans, _ = cache.get("试用期多久")
    assert hit is False  # 空 cache 必 miss
    cache.put("试用期多久", "3 个月")
    hit, ans, _ = cache.get("试用期多久")
    assert hit is True
    assert ans == "3 个月"


def test_cache_hit_synonymous_question():
    """同义问法（向量高相似）命中。"""
    # q1 和 q2 用几乎相同的向量（cosine≈0.99 > 0.9）
    vecs = {"试用期多久": [1.0, 0.1], "试用期几个月": [1.0, 0.05]}
    cache = SemanticCache(embed_fn=lambda q: vecs[q], threshold=0.9)
    cache.put("试用期多久", "3 个月", sources=[{"idx": 1, "source": "handbook.md"}])
    hit, ans, sources = cache.get("试用期几个月")
    assert hit is True
    assert ans == "3 个月"
    assert sources[0]["source"] == "handbook.md"  # sources 也复用


def test_cache_no_false_hit_on_different_question():
    """不同问题（向量低相似）不误命中。"""
    vecs = {"年假几天": [1.0, 0.0], "病假几天": [0.0, 1.0]}  # 正交，cosine=0
    cache = SemanticCache(embed_fn=lambda q: vecs[q], threshold=0.9)
    cache.put("年假几天", "5 天")
    hit, _, _ = cache.get("病假几天")
    assert hit is False  # 答案不同，绝不误命中


def test_invalidate_clears_cache():
    """invalidate 全量作废（文档更新后调）。"""
    cache = SemanticCache(embed_fn=lambda q: [1.0], threshold=0.9)
    cache.put("q1", "a1")
    cache.put("q2", "a2")
    assert cache.stats()["size"] == 2
    n = cache.invalidate()
    assert n == 2
    assert cache.stats()["size"] == 0
    # 作废后再查必 miss
    hit, _, _ = cache.get("q1")
    assert hit is False


def test_threshold_too_strict_blocks_hit():
    """阈值太高（0.99）→ cosine 0.98 的同义问法也不命中。"""
    # [1,0.1] vs [1,0.3] 的 cosine≈0.982 < 0.99
    vecs = {"试用期多久": [1.0, 0.1], "试用期几个月": [1.0, 0.3]}
    cache = SemanticCache(embed_fn=lambda q: vecs[q], threshold=0.99)
    cache.put("试用期多久", "3 个月")
    hit, _, _ = cache.get("试用期几个月")
    assert hit is False  # 0.982 < 0.99，太严不命中


def test_ttl_expires_entries():
    """TTL 过期后条目被淘汰。"""
    cache = SemanticCache(embed_fn=lambda q: [1.0], threshold=0.5, ttl_seconds=1)
    cache.put("q", "a")
    hit, _, _ = cache.get("q")
    assert hit is True
    time.sleep(1.1)
    hit, _, _ = cache.get("q")  # get 内部会淘汰过期条目
    assert hit is False
