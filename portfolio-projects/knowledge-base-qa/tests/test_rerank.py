"""rerank：降级策略与稳定排序（不打真实 API，httpx 全 mock）。"""
from __future__ import annotations

import httpx
import pytest
from langchain_core.documents import Document

import kb_qa.rerank as rerank_mod
from kb_qa.rerank import rerank_documents


def _docs(n: int) -> list[Document]:
    return [Document(page_content=f"内容{i}", metadata={"source": "x.md", "idx": i}) for i in range(n)]


def test_empty_returns_empty():
    assert rerank_documents("q", []) == []


def test_single_doc_short_circuits():
    docs = _docs(1)
    assert rerank_documents("q", docs, top_n=4) == docs


def test_api_failure_falls_back_to_truncation(monkeypatch: pytest.MonkeyPatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(rerank_mod.httpx, "post", boom)
    docs = _docs(5)
    out = rerank_documents("q", docs, top_n=3)
    assert out == docs[:3]  # 降级为原序截断


def _resp(payload: dict) -> httpx.Response:
    """带 request 的 200 响应（raise_for_status 需要 request 存在）。"""
    return httpx.Response(200, json=payload, request=httpx.Request("POST", "http://test"))


def test_tie_scores_keep_upstream_order(monkeypatch: pytest.MonkeyPatch):
    # 三条候选全部 =1.0（分数饱和），乱序返回
    def fake_post(*a, **k):
        return _resp({"results": [
            {"index": 2, "relevance_score": 1.0},
            {"index": 0, "relevance_score": 1.0},
            {"index": 1, "relevance_score": 1.0},
        ]})

    monkeypatch.setattr(rerank_mod.httpx, "post", fake_post)
    out = rerank_documents("q", _docs(3), top_n=3)
    # 同分退回上游顺序（按 index 升序）
    assert [d.metadata["idx"] for d in out] == [0, 1, 2]
    assert all("rerank_score" in d.metadata for d in out)


def test_higher_score_wins(monkeypatch: pytest.MonkeyPatch):
    def fake_post(*a, **k):
        return _resp({"results": [
            {"index": 0, "relevance_score": 0.2},
            {"index": 1, "relevance_score": 0.9},
            {"index": 2, "relevance_score": 0.5},
        ]})

    monkeypatch.setattr(rerank_mod.httpx, "post", fake_post)
    out = rerank_documents("q", _docs(3), top_n=2)
    assert [d.metadata["idx"] for d in out] == [1, 2]  # 按分数降序取 top-2
