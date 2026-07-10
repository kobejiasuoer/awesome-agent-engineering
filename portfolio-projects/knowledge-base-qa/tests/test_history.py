"""history：多轮会话持久化与 thread 隔离。"""
from __future__ import annotations

from pathlib import Path

from kb_qa.history import ChatHistory


def test_append_and_get_ordered(tmp_path: Path):
    h = ChatHistory(tmp_path / "h.db")
    h.append("t1", "human", "问题一")
    h.append("t1", "ai", "回答一")
    h.append("t1", "human", "问题二")
    assert h.get("t1") == [("human", "问题一"), ("ai", "回答一"), ("human", "问题二")]


def test_threads_isolated(tmp_path: Path):
    h = ChatHistory(tmp_path / "h.db")
    h.append("t1", "human", "甲")
    h.append("t2", "human", "乙")
    assert h.get("t1") == [("human", "甲")]
    assert h.get("t2") == [("human", "乙")]


def test_get_limit_returns_recent(tmp_path: Path):
    h = ChatHistory(tmp_path / "h.db")
    for i in range(10):
        h.append("t1", "human", f"m{i}")
    recent = h.get("t1", limit=3)
    assert [c for _, c in recent] == ["m7", "m8", "m9"]
