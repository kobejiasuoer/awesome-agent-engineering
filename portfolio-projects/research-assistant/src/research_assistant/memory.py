"""记忆系统：Agent 的情景记忆 + 语义记忆（Frontier L01）。

与前五门课的 Checkpointer（对话状态持久化）本质不同：
    - Checkpointer：按 thread_id 存取【完整 State 快照】，无检索/无遗忘/不跨 thread
    - MemoryStore：按语义检索【提炼后的经验】，可跨会话共享，有遗忘策略

两层记忆（受认知科学启发，对应 MemGPT 的分层思想）：
    - 情景记忆（episodic）：发生过的事件，原始度高，用 Chroma 向量检索
    - 语义记忆（semantic）：沉淀的事实结论，结构化（主题→结论→依据→时间）

核心接口：
    - remember(event)：写入一条情景记忆
    - recall(query, k)：检索最相关的 k 条记忆（情景 + 语义合并）
    - consolidate()：把多条同主题情景记忆归纳成语义结论（L02 实现提炼逻辑）

零 API 降级：ZhipuAIEmbeddings 不可用时，用字符重合度假 embedding，
保证 code.py / 测试不依赖网络和 key 也能跑（教学价值 > 真实精度）。
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import settings
from .logging_config import get_logger

log = get_logger("memory")


# ════════════════════════════════════════════════════════════
# 数据结构
# ════════════════════════════════════════════════════════════
@dataclass
class EpisodicMemory:
    """情景记忆：一次具体事件/发现。

    高保真但低密度——原始信息多，检索时需要向量相似度来找相关的。
    """
    id: str
    content: str          # 事件内容（如"查了X，发现Y"）
    topic: str            # 关联主题（便于 consolidate 按主题分组）
    timestamp: float      # 发生时间（Unix ts）
    source: str = "research"  # 来源标记
    retrieval_count: int = 0  # 被检索次数（遗忘策略用：频次高的保留）


@dataclass
class SemanticMemory:
    """语义记忆：沉淀的事实结论。

    低保真但高密度——从多条情景记忆归纳出的结论，结构化、可复用。
    """
    id: str
    topic: str            # 主题
    conclusion: str       # 结论
    evidence: str         # 依据（怎么得出的）
    timestamp: float
    confidence: float = 0.5  # 置信度（L02 反思式写入时 LLM 给）
    retrieval_count: int = 0


# ════════════════════════════════════════════════════════════
# Embedding 抽象：真实 / 假 两条路
# ════════════════════════════════════════════════════════════
class _Embedder:
    """embedding 抽象层：有 key 用智谱，没 key 用字符重合度降级。

    降级 embedding 精度差但能跑——教学场景优先保证「机制可演示」。
    生产必须用真实 embedding（recall 质量天差地别）。
    """

    def __init__(self):
        self._real = None
        if settings.zhipuai_api_key:
            try:
                from langchain_community.embeddings import ZhipuAIEmbeddings
                self._real = ZhipuAIEmbeddings(
                    model="embedding-3",
                    api_key=settings.zhipuai_api_key,
                )
                log.info("记忆 embedding：使用智谱 embedding-3")
            except Exception as e:
                log.warning(f"智谱 embedding 初始化失败，降级假 embedding：{e}")
                self._real = None
        else:
            log.info("记忆 embedding：无 API key，用字符重合度假 embedding")

    def embed(self, text: str) -> list[float]:
        """返回向量。真实走智谱，降级走字符哈希（固定维度伪向量）。"""
        if self._real is not None:
            try:
                return self._real.embed_query(text)
            except Exception as e:
                log.warning(f"embedding 调用失败，本次降级：{e}")
        return _fake_embed(text)

    @property
    def is_real(self) -> bool:
        return self._real is not None


def _fake_embed(text: str, dim: int = 64) -> list[float]:
    """假 embedding：基于字符频次的固定维度向量。

    不是真语义，但保证：相似文本→相似向量（字符重叠多→向量接近）。
    教学演示「recall 命中」够用；生产必须换真 embedding。
    """
    vec = [0.0] * dim
    for ch in text:
        # 用字符 ord 映射到维度，频次累加
        vec[ord(ch) % dim] += 1.0
    # L2 归一化（余弦相似度需要）
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度（向量已归一化时等价于点积）。"""
    return sum(x * y for x, y in zip(a, b))


# ════════════════════════════════════════════════════════════
# MemoryStore：核心实现
# ════════════════════════════════════════════════════════════
class MemoryStore:
    """Agent 记忆系统：情景 + 语义两层。

    设计取舍：
        - 情景记忆用 Chroma（成熟向量库，支持持久化 + 相似度检索）
        - 语义记忆用内存 list（结构化、量小、需要 LLM 归纳，不适合塞向量库）
        - 不引入 mem0 等第三方记忆库——手写才能看清机制（任务书硬约束）
        - 不可变风格：remember/consolidate 返回新对象，不原地改（仓库约定）

    降级路径：
        - Chroma 不可用时，情景记忆退化为内存 list + 线性扫描（仍能 recall）
        - 这样测试和无 chromadb 环境也能跑
    """

    def __init__(self, persist_path: str | None = None):
        """初始化记忆库。

        Args:
            persist_path: Chroma 持久化目录；None 则读 config.memory_db_path
        """
        self._embedder = _Embedder()
        self._persist_path = persist_path or settings.memory_db_path or "memory_store"
        self._semantic: list[SemanticMemory] = []  # 语义记忆（内存）
        self._episodic: list[EpisodicMemory] = []  # 情景记忆降级用（无 chroma 时）
        self._chroma = None  # Chroma collection（可用时）
        self._init_chroma()

    def _init_chroma(self):
        """初始化 Chroma collection，失败则降级内存模式。"""
        try:
            import chromadb
            client = chromadb.PersistentClient(path=self._persist_path)
            self._chroma = client.get_or_create_collection(
                name="episodic_memory",
                metadata={"hnsw:space": "cosine"},
            )
            log.info(f"情景记忆：Chroma 持久化 @ {self._persist_path}")
        except Exception as e:
            log.warning(f"Chroma 不可用，情景记忆降级为内存模式：{e}")
            self._chroma = None

    # ── 写入 ──────────────────────────────────────────────
    def remember(self, content: str, topic: str = "", source: str = "research") -> EpisodicMemory:
        """写入一条情景记忆。

        Args:
            content: 事件内容（如"研究了X，发现Y"）
            topic: 关联主题（consolidate 按主题分组用）
            source: 来源标记

        Returns:
            写入的 EpisodicMemory（不可变，调用方持有引用）
        """
        mem = EpisodicMemory(
            id=_new_id(content),
            content=content,
            topic=topic or content[:20],
            timestamp=time.time(),
            source=source,
        )

        if self._chroma is not None:
            try:
                self._chroma.add(
                    ids=[mem.id],
                    documents=[mem.content],
                    embeddings=[self._embedder.embed(mem.content)],
                    metadatas=[{"topic": mem.topic, "timestamp": mem.timestamp, "source": mem.source}],
                )
                log.debug(f"remember(Chroma): {mem.content[:40]}")
                return mem
            except Exception as e:
                log.warning(f"Chroma 写入失败，降级内存：{e}")
                self._chroma = None

        # 内存降级
        self._episodic.append(mem)
        log.debug(f"remember(mem): {mem.content[:40]}")
        return mem

    def add_semantic(self, topic: str, conclusion: str, evidence: str,
                     confidence: float = 0.5) -> SemanticMemory:
        """直接写入一条语义记忆（L02 的 consolidate 调用）。"""
        mem = SemanticMemory(
            id=_new_id(conclusion),
            topic=topic,
            conclusion=conclusion,
            evidence=evidence,
            timestamp=time.time(),
            confidence=confidence,
        )
        self._semantic.append(mem)
        log.debug(f"add_semantic: {topic} → {conclusion[:40]}")
        return mem

    # ── 检索 ──────────────────────────────────────────────
    def recall(self, query: str, k: int = 3) -> dict[str, list]:
        """检索与 query 相关的记忆，返回情景 + 语义两类。

        这是 researcher 节点研究前调用的入口——把旧记忆注入 prompt，
        实现"第 2 次运行记得第 1 次"（硬任务的核心要求）。

        Returns:
            {"episodic": [EpisodicMemory...], "semantic": [SemanticMemory...]}
            每条记忆的 retrieval_count 会 +1（遗忘策略用）
        """
        # 情景记忆检索
        episodic_hits = self._recall_episodic(query, k)

        # 语义记忆检索（按 topic 相似度 + 时间衰减，简化版）
        semantic_hits = self._recall_semantic(query, k)

        # 命中记忆的检索频次 +1（遗忘策略：常用的保留）
        for m in episodic_hits:
            m.retrieval_count += 1
        for m in semantic_hits:
            m.retrieval_count += 1

        if episodic_hits or semantic_hits:
            log.info(f"recall('{query[:30]}'): episodic={len(episodic_hits)}, semantic={len(semantic_hits)}")
        return {"episodic": episodic_hits, "semantic": semantic_hits}

    def _recall_episodic(self, query: str, k: int) -> list[EpisodicMemory]:
        """情景记忆检索：Chroma 走向量，降级走内存余弦。"""
        if not self._has_episodic():
            return []

        if self._chroma is not None:
            try:
                qvec = self._embedder.embed(query)
                res = self._chroma.query(query_embeddings=[qvec], n_results=min(k, self._episodic_count()))
                hits = []
                for i, doc_id in enumerate(res["ids"][0]):
                    doc = res["documents"][0][i]
                    meta = res["metadatas"][0][i] if res.get("metadatas") else {}
                    hits.append(EpisodicMemory(
                        id=doc_id,
                        content=doc,
                        topic=meta.get("topic", ""),
                        timestamp=meta.get("timestamp", 0),
                        source=meta.get("source", "research"),
                    ))
                return hits
            except Exception as e:
                log.warning(f"Chroma 查询失败，降级内存：{e}")

        # 内存降级：线性扫描余弦相似度
        qvec = self._embedder.embed(query)
        scored = [(m, _cosine(qvec, self._embedder.embed(m.content))) for m in self._episodic]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in scored[:k]]

    def _recall_semantic(self, query: str, k: int) -> list[SemanticMemory]:
        """语义记忆检索：按 topic 文本相似度排序（语义记忆量小，简化处理）。"""
        if not self._semantic:
            return []
        qvec = self._embedder.embed(query)
        scored = [(m, _cosine(qvec, self._embedder.embed(f"{m.topic} {m.conclusion}"))) for m in self._semantic]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in scored[:k]]

    def _has_episodic(self) -> bool:
        """是否有情景记忆数据。"""
        if self._chroma is not None:
            try:
                return self._chroma.count() > 0
            except Exception:
                pass
        return len(self._episodic) > 0

    def _episodic_count(self) -> int:
        if self._chroma is not None:
            try:
                return self._chroma.count()
            except Exception:
                pass
        return len(self._episodic)

    # ── 巩固（L02 实现提炼逻辑，这里只留接口）─────────────
    def consolidate(self, llm=None) -> list[SemanticMemory]:
        """把多条同主题情景记忆归纳成语义结论。

        L02 会接入 LLM 做反思式提炼。这里提供骨架：
        按主题分组 → 每组生成一条语义记忆。
        无 LLM 时用简单拼接（降级，教学演示用）。
        """
        # 收集所有情景记忆（Chroma 模式需要先拉全量）
        all_episodic = self._all_episodic()
        if not all_episodic:
            return []

        # 按主题分组
        groups: dict[str, list[EpisodicMemory]] = {}
        for m in all_episodic:
            groups.setdefault(m.topic, []).append(m)

        results: list[SemanticMemory] = []
        for topic, mems in groups.items():
            if len(mems) < 1:
                continue
            contents = "\n".join(f"- {m.content}" for m in mems)

            if llm is not None:
                # L02 接入：让 LLM 提炼结论
                resp = llm.invoke(
                    f"以下是关于「{topic}」的多条研究记录，请提炼成一条结论性事实"
                    f"（含依据、置信度0-1）：\n{contents}\n"
                    f"格式：结论 | 依据 | 置信度"
                )
                parts = resp.content.split("|")
                conclusion = parts[0].strip() if parts else resp.content.strip()
                evidence = parts[1].strip() if len(parts) > 1 else contents[:100]
                conf = 0.6
                if len(parts) > 2:
                    try:
                        conf = float(parts[2].strip())
                    except ValueError:
                        pass
            else:
                # 降级：简单拼接（无 LLM）
                conclusion = f"{topic}：共 {len(mems)} 条记录，核心是 {contents[:60]}"
                evidence = contents[:120]
                conf = 0.4

            sm = self.add_semantic(topic, conclusion, evidence, conf)
            results.append(sm)

        log.info(f"consolidate: {len(groups)} 个主题 → {len(results)} 条语义记忆")
        return results

    def _all_episodic(self) -> list[EpisodicMemory]:
        """拉取全部情景记忆（consolidate 用）。"""
        if self._chroma is not None:
            try:
                res = self._chroma.get()
                return [
                    EpisodicMemory(
                        id=i,
                        content=d,
                        topic=(m or {}).get("topic", ""),
                        timestamp=(m or {}).get("timestamp", 0),
                        source=(m or {}).get("source", "research"),
                    )
                    for i, d, m in zip(res["ids"], res["documents"], res.get("metadatas") or [{}] * len(res["ids"]))
                ]
            except Exception as e:
                log.warning(f"Chroma get 失败：{e}")
        return list(self._episodic)

    # ── 遗忘（L02 接入，这里留接口）───────────────────────
    def forget(self, max_episodic: int | None = None, decay_days: float | None = None):
        """遗忘策略：超过上限或太旧且不被检索的情景记忆淘汰。

        L02 配置 memory_max_episodic / memory_decay_days 后生效。
        语义记忆不遗忘（沉淀的结论，量小价值高）。
        """
        max_episodic = max_episodic or settings.memory_max_episodic
        decay_days = decay_days or settings.memory_decay_days
        if max_episodic <= 0 and decay_days <= 0:
            return  # 都关了

        all_episodic = self._all_episodic()
        now = time.time()
        keep: list[EpisodicMemory] = []
        for m in all_episodic:
            age_days = (now - m.timestamp) / 86400
            # 保留条件：未超上限 且 （较新 或 被检索过）
            too_old = decay_days > 0 and age_days > decay_days and m.retrieval_count == 0
            if not too_old:
                keep.append(m)

        # 超上限：按 (频次, 新鲜度) 排序，保留 top-N
        if max_episodic > 0 and len(keep) > max_episodic:
            keep.sort(key=lambda m: (m.retrieval_count, m.timestamp), reverse=True)
            keep = keep[:max_episodic]

        forgotten = len(all_episodic) - len(keep)
        if forgotten > 0:
            log.info(f"forget: 淘汰 {forgotten} 条情景记忆（保留 {len(keep)}）")
            # 内存模式直接重建；Chroma 模式删差异（简化：全清重写）
            self._rebuild_episodic(keep)

    def _rebuild_episodic(self, kept: list[EpisodicMemory]):
        """重建情景记忆存储（forget 用）。"""
        if self._chroma is not None:
            try:
                self._chroma.delete(ids=self._chroma.get()["ids"])
            except Exception:
                pass
            self._chroma = None  # 降级内存，避免复杂重建
        self._episodic = list(kept)

    # ── 格式化（供 prompt 注入）──────────────────────────
    def format_recall_for_prompt(self, hits: dict[str, list]) -> str:
        """把 recall 结果格式化成可注入 prompt 的文本。

        researcher 节点用：recall → format → 拼进研究 prompt。
        """
        if not hits["episodic"] and not hits["semantic"]:
            return ""

        lines = ["【记忆命中】以下是之前研究的相关记忆，请在此基础上深化而非重复："]
        for m in hits["semantic"]:
            lines.append(f"  [旧结论·{m.topic}] {m.conclusion}（依据：{m.evidence[:50]}，置信度{m.confidence}）")
        for m in hits["episodic"]:
            lines.append(f"  [旧记录·{m.topic}] {m.content}")
        return "\n".join(lines)


def _new_id(text: str) -> str:
    """生成记忆 id：内容 hash + 时间戳，保证唯一且可去重。"""
    return hashlib.md5(f"{text}{time.time()}".encode()).hexdigest()[:12]


# ════════════════════════════════════════════════════════════
# 反思式写入（Frontier L02）：任务结束后让 LLM 提炼值得记的东西
# ════════════════════════════════════════════════════════════
def reflect_and_store(
    trajectory: list[dict] | str,
    topic: str,
    store: MemoryStore,
    llm=None,
) -> list[EpisodicMemory]:
    """反思式写入：给定一次任务轨迹 → LLM 提炼记忆条目 → 写入 MemoryStore。

    核心思想（Generative Agents 的 reflection tree）：
        原始对话全存会淹没检索——Agent 要自己回答「这次学到了什么值得下次复用？」
        生成结构化记忆条目（含类型/置信度），只存提炼后的高密度信息。

    Args:
        trajectory: 任务轨迹（findings 列表或文本）。可以是 L00 基线格式或 findings 字符串列表
        topic: 本次研究主题
        store: 目标 MemoryStore
        llm: 用于提炼的 LLM（None 时降级为关键词抽取）

    Returns:
        写入的 EpisodicMemory 列表

    流派对比：
        ① 全存：检索被噪音淹没
        ② 规则抽取：脆，覆盖不了开放场景
        ③ 反思式写入（本课选它）：LLM 提炼，灵活但依赖 LLM 质量
    """
    # 把轨迹整理成文本
    if isinstance(trajectory, list):
        if trajectory and isinstance(trajectory[0], dict):
            # L00 轨迹格式：提取 output 字段
            traj_text = "\n".join(
                f"[{s.get('node', '?')}] {s.get('output', '')}"
                for s in trajectory if s.get("output")
            )
        else:
            # findings 字符串列表
            traj_text = "\n".join(str(s) for s in trajectory)
    else:
        traj_text = str(trajectory)

    if not traj_text.strip():
        log.warning("reflect_and_store: 轨迹为空，跳过")
        return []

    written: list[EpisodicMemory] = []

    if llm is not None:
        # 让 LLM 提炼 3-5 条记忆条目
        resp = llm.invoke(
            f"你是记忆整理助手。以下是一次关于「{topic}」的研究轨迹。"
            f"请提炼 3-5 条【值得下次研究复用】的记忆条目，每条一行，"
            f"格式：内容 | 置信度(0-1) | 类型(事实/方法/结论)。\n"
            f"要求：只记有复用价值的，不要记流水账。\n\n{traj_text}"
        )
        lines = resp.content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            content = parts[0].strip()
            if not content:
                continue
            confidence = 0.6
            if len(parts) > 1:
                try:
                    confidence = float(parts[1].strip())
                except ValueError:
                    pass
            mem_type = parts[2].strip() if len(parts) > 2 else "结论"
            # 写入情景记忆（带类型标记）
            tagged = f"[{mem_type}·置信{confidence}] {content}"
            mem = store.remember(tagged, topic=topic, source="reflection")
            written.append(mem)
        log.info(f"reflect_and_store(LLM): 从轨迹提炼 {len(written)} 条记忆")
    else:
        # 降级：无 LLM 时用简单规则抽取（取每条 finding 的核心句）
        findings_lines = [l.strip() for l in traj_text.split("\n") if l.strip() and "发现" in l]
        if not findings_lines:
            findings_lines = [l.strip() for l in traj_text.split("\n") if l.strip()][:5]
        for line in findings_lines[:5]:
            mem = store.remember(f"[规则提炼] {line}", topic=topic, source="reflection_rule")
            written.append(mem)
        log.info(f"reflect_and_store(规则降级): 抽取 {len(written)} 条记忆")

    return written
