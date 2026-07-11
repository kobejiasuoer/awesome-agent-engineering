"""记忆系统测试（Frontier L01）。

测试原则（对齐 conftest）：
    - 不调真实 LLM（用 mock）
    - 不联网（embedding 降级假向量）
    - 不依赖 API key（无 key 时 _Embedder 自动降级）
    - 不污染生产记忆库（用临时目录）
"""
from __future__ import annotations

import time

import pytest

from research_assistant.memory import (
    MemoryStore,
    EpisodicMemory,
    SemanticMemory,
    _fake_embed,
    _cosine,
)


@pytest.fixture
def mem_store(tmp_path, monkeypatch):
    """临时目录的记忆库（隔离，测试完自动清理）。

    强制用假 embedding：测试环境可能有过期 key，真实 embedding 会 401 降级（慢+噪声）。
    直接把 _Embedder 的真实路径堵掉，保证纯假向量、零网络。
    """
    import research_assistant.memory as mem_mod
    # 让 _Embedder 认为没有 key → 直接用假 embedding（零网络、零 401 噪声）
    monkeypatch.setattr(mem_mod.settings, "zhipuai_api_key", "")
    store = MemoryStore(persist_path=str(tmp_path / "test_mem"))
    # 确保走假 embedding
    assert not store._embedder.is_real, "测试必须用假 embedding"
    return store


# ── 假 embedding ──────────────────────────────────────────────
def test_fake_embed_normalized():
    """假 embedding 应是归一化向量（余弦相似度需要）。"""
    vec = _fake_embed("hello world")
    norm = sum(v * v for v in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-6, "假 embedding 应 L2 归一化"


def test_cosine_similar_text_higher():
    """相似文本的余弦相似度应高于不相关文本。"""
    vec1 = _fake_embed("MCP 协议演进")
    vec2 = _fake_embed("MCP 协议发展")
    vec3 = _fake_embed("今天天气不错")
    sim_same = _cosine(vec1, vec2)
    sim_diff = _cosine(vec1, vec3)
    assert sim_same > sim_diff, "相似文本相似度应更高"


# ── remember + recall ─────────────────────────────────────────
def test_remember_and_recall_returns_hit(mem_store):
    """写入后 recall 同主题 query 应命中。"""
    mem_store.remember("研究了 MCP 协议，发现它基于 JSON-RPC", topic="MCP")
    mem_store.remember("查了天气，今天晴", topic="天气")

    hits = mem_store.recall("MCP 协议", k=3)
    assert len(hits["episodic"]) > 0, "应命中情景记忆"
    # MCP 的记忆应排在天气前面（更相关）
    contents = [h.content for h in hits["episodic"]]
    assert any("MCP" in c for c in contents)


def test_recall_empty_when_no_memory(mem_store):
    """空记忆库 recall 应返回空列表。"""
    hits = mem_store.recall("anything", k=3)
    assert hits["episodic"] == []
    assert hits["semantic"] == []


def test_recall_k_limit(mem_store):
    """recall 应受 k 限制。"""
    for i in range(5):
        mem_store.remember(f"MCP 第{i}条记录", topic="MCP")
    hits = mem_store.recall("MCP", k=2)
    assert len(hits["episodic"]) <= 2


def test_recall_increases_retrieval_count(mem_store):
    """recall 命中后 retrieval_count 应 +1（遗忘策略用）。

    内存模式下 _episodic 对象被原地 +1；
    Chroma 模式下 recall 重建对象（计数不持久化，这是已知简化）。
    这里测内存模式：把 _chroma 置 None 强制走内存路径。
    """
    mem_store._chroma = None  # 强制内存模式
    mem_store.remember("一条记忆", topic="test")
    mem_store.recall("一条记忆", k=1)
    assert mem_store._episodic[0].retrieval_count >= 1


# ── 语义记忆 ──────────────────────────────────────────────────
def test_add_semantic_and_recall(mem_store):
    """写入语义记忆后 recall 应命中。"""
    mem_store.add_semantic("MCP", "MCP 是标准化工具协议", "基于 JSON-RPC", 0.8)
    hits = mem_store.recall("MCP 协议", k=3)
    assert len(hits["semantic"]) > 0
    assert "标准化" in hits["semantic"][0].conclusion


# ── consolidate ───────────────────────────────────────────────
def test_consolidate_without_llm(mem_store):
    """无 LLM 时 consolidate 应降级为简单拼接。"""
    mem_store.remember("MCP 发现1", topic="MCP")
    mem_store.remember("MCP 发现2", topic="MCP")
    results = mem_store.consolidate(llm=None)
    assert len(results) >= 1
    assert any("MCP" in r.topic for r in results)


def test_consolidate_with_mock_llm(mem_store):
    """有 mock LLM 时 consolidate 应调用 LLM 提炼。"""
    mem_store.remember("MCP 发现1", topic="MCP")
    mem_store.remember("MCP 发现2", topic="MCP")

    class MockLLM:
        def invoke(self, prompt):
            class R:
                content = "MCP是工具协议 | 基于JSON-RPC | 0.9"
            return R()

    results = mem_store.consolidate(llm=MockLLM())
    assert len(results) >= 1
    assert "工具协议" in results[0].conclusion


# ── format_recall_for_prompt ──────────────────────────────────
def test_format_recall_empty(mem_store):
    """无命中时 format 应返回空串（不污染 prompt）。"""
    hits = {"episodic": [], "semantic": []}
    assert mem_store.format_recall_for_prompt(hits) == ""


def test_format_recall_has_content(mem_store):
    """有命中时 format 应包含【记忆命中】标记。"""
    hits = {
        "episodic": [EpisodicMemory("id1", "旧记录内容", "MCP", time.time())],
        "semantic": [SemanticMemory("id2", "MCP", "MCP是协议", "依据", time.time(), 0.8)],
    }
    text = mem_store.format_recall_for_prompt(hits)
    assert "记忆命中" in text
    assert "旧结论" in text
    assert "旧记录" in text


# ── 不可变风格 ────────────────────────────────────────────────
def test_remember_returns_new_object(mem_store):
    """remember 应返回新的 EpisodicMemory 对象（不可变风格）。"""
    mem = mem_store.remember("内容", topic="t")
    assert isinstance(mem, EpisodicMemory)
    assert mem.content == "内容"
    assert mem.timestamp > 0
