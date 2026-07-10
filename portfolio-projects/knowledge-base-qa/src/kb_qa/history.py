"""多轮会话历史：sqlite 持久化（thread_id 隔离）。

为什么不用 LangGraph Checkpointer：研究助手是多节点图，检查点保存的是
图状态；本项目生成链是线性的，只需要「问答对历史」，一张 messages 表
就够了——用对工具的复杂度，也是生产判断力的一部分。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('human', 'ai')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages (thread_id, id);
"""


class ChatHistory:
    """每线程（thread_id）的问答历史。连接按操作开关，避免跨线程共享连接。"""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path or settings.sqlite_db_path)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def get(self, thread_id: str, limit: int = 8) -> list[tuple[str, str]]:
        """取最近 limit 条消息（时间正序），供 prompt 拼接。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM ("
                "  SELECT id, role, content FROM messages"
                "  WHERE thread_id = ? ORDER BY id DESC LIMIT ?"
                ") ORDER BY id ASC",
                (thread_id, limit),
            ).fetchall()
        return [(role, content) for role, content in rows]

    def append(self, thread_id: str, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (thread_id, role, content) VALUES (?, ?, ?)",
                (thread_id, role, content),
            )
