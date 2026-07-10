"""服务编排：把 检索 → 生成 → 历史 串成 SSE 事件流。

事件协议（前端按 event 分发）：
    progress —— {stage, detail}   检索/改写进度
    sources  —— [{idx, source, section, preview}]  引用材料列表
    token    —— {content}         逐 token 输出
    done     —— {answer, thread_id, mode}  完整结果（落历史后发出）
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from .config import settings
from .generate import condense_question, stream_answer
from .history import ChatHistory
from .retriever import KBRetriever

_kb: KBRetriever | None = None
_kb_lock = asyncio.Lock()


async def get_kb() -> KBRetriever:
    """进程级单例：BM25 索引构建有成本，建一次答多次。"""
    global _kb
    async with _kb_lock:
        if _kb is None:
            _kb = await asyncio.to_thread(KBRetriever)
        return _kb


async def reset_kb() -> None:
    """文档上传/入库后调用：作废旧索引，下次请求重建。"""
    global _kb
    async with _kb_lock:
        _kb = None


def _event(name: str, data: dict | list) -> dict:
    return {"event": name, "data": json.dumps(data, ensure_ascii=False)}


async def stream_ask(
    question: str,
    thread_id: str,
    mode: str | None = None,
) -> AsyncIterator[dict]:
    """一次问答的完整事件流。"""
    history = ChatHistory()
    past = history.get(thread_id)

    # 追问改写：有历史时把问题补全成独立问题再检索
    search_query = question
    if past:
        yield _event("progress", {"stage": "condense", "detail": "改写追问为独立问题"})
        search_query = await condense_question(question, past)

    yield _event("progress", {"stage": "retrieve", "detail": f"混合检索中（mode={mode or 'default'}）"})
    kb = await get_kb()
    docs = await asyncio.to_thread(kb.retrieve, search_query, mode)

    yield _event(
        "sources",
        [
            {
                "idx": i,
                "source": d.metadata.get("source", "?"),
                "section": d.metadata.get("section", ""),
                "preview": d.page_content[:120],
            }
            for i, d in enumerate(docs, 1)
        ],
    )

    answer_parts: list[str] = []
    async for token in stream_answer(question, docs, past):
        answer_parts.append(token)
        yield _event("token", {"content": token})

    answer = "".join(answer_parts)
    history.append(thread_id, "human", question)
    history.append(thread_id, "ai", answer)

    yield _event(
        "done",
        {
            "answer": answer,
            "thread_id": thread_id,
            "mode": mode or ("rerank" if settings.enable_rerank else "hybrid"),
        },
    )
