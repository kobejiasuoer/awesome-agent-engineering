"""语义缓存：相似问题不重复调 LLM（LLMOps L10）。

用问题 embedding 的余弦相似度判命中（非字符串相等），
同义问法（「试用期多久」vs「试用期几个月」）命中后跳过检索+生成，
降延迟降成本。

设计要点：
    - 复用现有 get_embeddings()（embedding-3），不引新依赖
    - 阈值可配（默认 0.92）：太松答错、太紧不命中
    - 文档更新时全量作废（reset_kb 调 invalidate）：防过时答案
    - 内存存储 + cosine 暴力扫：量级小（千级问答对）够用；
      百万级应换向量库（复用 Chroma 存问答对 embedding）
    - 有历史（追问）时调用方应跳过缓存（service.py 已处理）
"""
from __future__ import annotations

import time
from typing import Callable

from .observability import get_logger, log_event

_log = get_logger("kb_qa.semantic_cache")


def _cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度。语义缓存用它判「语义相等」。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SemanticCache:
    """按 embedding 余弦相似度判命中的缓存。

    get(q) → 算 q 的 embedding，和已存条目比 cosine，max_sim >= 阈值 → 命中。
    put(q, answer, sources) → miss 后回填。
    invalidate() → 全量作废（文档更新时调）。
    """

    def __init__(
        self,
        embed_fn: Callable[[str], list[float]] | None = None,
        threshold: float = 0.92,
        ttl_seconds: int = 3600,
    ) -> None:
        self._embed_fn = embed_fn
        self.threshold = threshold
        self.ttl = ttl_seconds
        self._store: list[dict] = []  # [{embedding, question, answer, sources, ts}]

    def _embed(self, question: str) -> list[float]:
        """算问题的 embedding。embed_fn 延迟注入（避免无 API key 时 import 崩）。"""
        if self._embed_fn is None:
            from .ingest import get_embeddings
            emb = get_embeddings()
            self._embed_fn = lambda q: emb.embed_query(q)
        return self._embed_fn(question)

    def get(self, question: str) -> tuple[bool, str | None, list[dict] | None]:
        """查缓存。返回 (命中, 答案, sources)。

        sources 一并返回（命中时复用引用材料，前端能显示出处）。
        """
        now = time.time()
        # TTL 过期淘汰
        self._store = [e for e in self._store if now - e["ts"] < self.ttl]

        q_vec = self._embed(question)
        best_sim, best_entry = 0.0, None
        for entry in self._store:
            sim = _cosine(q_vec, entry["embedding"])
            if sim > best_sim:
                best_sim, best_entry = sim, entry

        if best_entry and best_sim >= self.threshold:
            log_event(_log, "cache.hit", question=question[:40],
                      similarity=round(best_sim, 3))
            return True, best_entry["answer"], best_entry["sources"]
        if best_entry:
            log_event(_log, "cache.miss", question=question[:40],
                      best_similarity=round(best_sim, 3))
        return False, None, None

    def put(self, question: str, answer: str, sources: list[dict] | None = None) -> None:
        """miss 后回填缓存。sources 存引用材料（命中时复用）。"""
        self._store.append({
            "embedding": self._embed(question),
            "question": question,
            "answer": answer,
            "sources": sources or [],
            "ts": time.time(),
        })

    def invalidate(self) -> int:
        """全量作废（文档更新后调）。返回清空的条数。

        粗暴但安全：宁可少命中，不能返回过时答案。
        """
        n = len(self._store)
        self._store.clear()
        if n:
            log_event(_log, "cache.invalidated", cleared=n)
        return n

    def stats(self) -> dict:
        return {"size": len(self._store), "threshold": self.threshold}


# 进程级单例
_cache: SemanticCache | None = None


def get_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        from .config import settings
        _cache = SemanticCache(threshold=settings.cache_similarity_threshold)
    return _cache


def reset_cache() -> None:
    """重置单例（测试用：换阈值后重建）。"""
    global _cache
    _cache = None
