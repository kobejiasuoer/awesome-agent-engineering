"""generate：上下文拼接与引用格式（纯函数，不打 LLM）。"""
from __future__ import annotations

from langchain_core.documents import Document

from kb_qa.generate import build_context


def test_context_numbered_with_source():
    docs = [
        Document(page_content="年假 5 天", metadata={"source": "hb.md", "section": "手册 > 假期"}),
        Document(page_content="报销 30 天内", metadata={"source": "fin.md", "section": ""}),
    ]
    ctx = build_context(docs)
    assert "【材料1】" in ctx and "【材料2】" in ctx
    assert "hb.md · 手册 > 假期" in ctx
    assert "fin.md" in ctx and "· \n" not in ctx  # 无 section 时不留孤零点
    assert "年假 5 天" in ctx
