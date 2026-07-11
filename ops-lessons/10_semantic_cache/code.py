"""
Lesson 10 — 语义缓存：相似问题不重复烧钱
==========================================
本脚本【零外部依赖】实现语义缓存核心：
    ① 用 embedding 余弦相似度判命中（非字符串相等）
    ② 阈值权衡（太松答错、太紧不命中）
    ③ 文档更新后作废缓存（防过时答案）
    ④ 多轮上下文跳过缓存（追问不能复用）

用 mock embedding（基于词袋的简单位向量）演示，看清数据流。
落地版（kb_qa/semantic_cache.py）用真实 embedding-3，逻辑同构。

运行：python code.py
依赖：仅标准库
"""
from __future__ import annotations

import math
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ════════════════════════════════════════════════════════════════
# 1. Mock embedding：把句子转成词袋位向量（教学用，真实用 embedding-3）
# ════════════════════════════════════════════════════════════════
# 用固定的词表把句子映射成位向量：句子含某词→该维=1。
# 同义词归一化（「多久/几个月/多长时间」→ 同一维），让同义问法向量接近，
# 模拟真实 embedding「语义近=向量近」的特性。
_VOCAB = ["试用", "期", "多久", "年假", "病假", "几天", "工资", "转正",
          "报销", "公司", "云帆", "科技"]
# 同义/近义词归一化映射：都映射到「多久」这一维
_SYNONYMS = {"几个月": "多久", "多长时间": "多久", "多长": "多久"}


def _normalize(text: str) -> str:
    """把同义表达归一化（模拟 embedding 捕捉语义等价）。"""
    for syn, std in _SYNONYMS.items():
        text = text.replace(syn, std)
    return text


def mock_embed(text: str) -> list[float]:
    """词袋位向量：句子含 vocab[i] 则该维=1（同义词先归一化）。"""
    text = _normalize(text)
    vec = [0.0] * len(_VOCAB)
    for i, w in enumerate(_VOCAB):
        if w in text:
            vec[i] = 1.0
    return vec


def cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度。语义缓存用它判命中。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ════════════════════════════════════════════════════════════════
# 2. 语义缓存
# ════════════════════════════════════════════════════════════════
class SemanticCache:
    """按 embedding 余弦相似度判命中的缓存。

    - get(q)：算 q 的 embedding，和已存的比 cosine，max_sim > 阈值 → 命中
    - put(q, answer)：miss 后回填（存 embedding + answer + 时间）
    - invalidate()：全量作废（文档更新时调）
    """

    def __init__(self, embed_fn, threshold: float = 0.92) -> None:
        self.embed = embed_fn
        self.threshold = threshold
        self._store: list[dict] = []  # [{embedding, question, answer, ts}]

    def get(self, question: str) -> tuple[bool, str | None]:
        """查缓存。返回 (命中, 答案)。"""
        q_vec = self.embed(question)
        best_sim, best_entry = 0.0, None
        for entry in self._store:
            sim = cosine(q_vec, entry["embedding"])
            if sim > best_sim:
                best_sim, best_entry = sim, entry
        if best_entry and best_sim >= self.threshold:
            return True, best_entry["answer"]
        return False, None

    def put(self, question: str, answer: str) -> None:
        """miss 后回填缓存。"""
        self._store.append({
            "embedding": self.embed(question),
            "question": question,
            "answer": answer,
            "ts": time.time(),
        })

    def invalidate(self) -> None:
        """全量作废（文档更新后调）。宁可少命中，不能答过时。"""
        n = len(self._store)
        self._store.clear()
        return n

    def stats(self) -> dict:
        return {"size": len(self._store)}


# ════════════════════════════════════════════════════════════════
# 3. 演示
# ════════════════════════════════════════════════════════════════
def fake_rag_answer(question: str) -> str:
    """模拟走完整管线（检索+生成）的耗时调用。"""
    time.sleep(0.3)  # 假装检索+生成要 300ms
    return f"[针对「{question}」的答案]"


def handle_ask(cache: SemanticCache, question: str, has_history: bool = False) -> tuple[str, bool]:
    """模拟带缓存的问答入口。返回 (答案, 是否缓存命中)。"""
    # 有历史（追问）→ 跳过缓存（上下文相关，不能复用）
    if has_history:
        return fake_rag_answer(question), False

    hit, cached = cache.get(question)
    if hit:
        return cached, True  # 命中：直接返回，跳过管线
    answer = fake_rag_answer(question)
    cache.put(question, answer)  # miss：回填
    return answer, False


def main() -> None:
    cache = SemanticCache(mock_embed, threshold=0.92)

    print("=" * 60)
    print("演示 1：同义问法命中（第二次相似问题 cache_hit）")
    print("=" * 60)
    q1 = "试用期多久"
    a1, hit1 = handle_ask(cache, q1)
    print(f"  Q1: {q1} → hit={hit1}（首次必 miss，走管线）")

    q2 = "试用期是几个月"  # 同义换说法
    t0 = time.perf_counter()
    a2, hit2 = handle_ask(cache, q2)
    dt = (time.perf_counter() - t0) * 1000
    print(f"  Q2: {q2} → hit={hit2}（{dt:.0f}ms，命中跳过管线，快很多）")

    q3 = "试用期多长时间"  # 又一种说法
    a3, hit3 = handle_ask(cache, q3)
    print(f"  Q3: {q3} → hit={hit3}（同义也命中）")

    print("\n" + "=" * 60)
    print("演示 2：近义但不误命中（年假 vs 病假，答案不同不该命中）")
    print("=" * 60)
    handle_ask(cache, "年假几天")  # 先存
    hit, _ = cache.get("病假几天")  # 病假≠年假，不该命中
    sim = cosine(mock_embed("年假几天"), mock_embed("病假几天"))
    print(f"  「年假几天」vs「病假几天」相似度={sim:.3f}（< 0.92，不误命中 ✅）")
    print(f"  命中={hit}（正确：答案不同，不能复用）")

    print("\n" + "=" * 60)
    print("演示 3：文档更新后作废缓存（防过时答案）")
    print("=" * 60)
    print(f"  作废前缓存条数：{cache.stats()['size']}")
    n = cache.invalidate()
    print(f"  模拟文档更新 → invalidate() 清空 {n} 条")
    print(f"  作废后缓存条数：{cache.stats()['size']}")
    a, hit = handle_ask(cache, "试用期多久")
    print(f"  再问「试用期多久」→ hit={hit}（作废后重新走管线，不会返回旧答案）")

    print("\n" + "=" * 60)
    print("演示 4：有历史（追问）跳过缓存")
    print("=" * 60)
    handle_ask(cache, "试用期多久")
    a, hit = handle_ask(cache, "试用期多久", has_history=True)
    print(f"  有历史时问「试用期多久」→ hit={hit}（追问跳过缓存，走管线）")
    print("  → 追问依赖上下文，缓存可能答错，所以不缓存。")

    print("\n💡 语义缓存：同义命中省 LLM 调用，近义不误命中保准确，"
          "文档更新作废防过时，追问跳过避上下文冲突。")


if __name__ == "__main__":
    main()
