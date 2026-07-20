"""工具返回值整形测试（Harness 课程 L04）。

锁死四类契约：
    1. 省略必须显式：任何整形产物内容少于原文 ⇒ 标记在场（逐条锁死）
    2. 三板斧行为：截断含预算（标记也占预算）、分页无缝续读、引用无损外置
    3. 错误也是返回值：可行动短错误（现象+建议，无堆栈）
    4. researcher 集成：开=肥结果被截且带标记；关=prompt 逐字节现状
"""
from __future__ import annotations

import pytest

from research_assistant import tool_shaping as ts
from research_assistant.config import settings
from research_assistant.context_ledger import FakeTokenizer


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setitem(settings.__dict__, "enable_tool_shaping", False)
    monkeypatch.setitem(settings.__dict__, "tool_result_max_tokens", 600)
    yield


# ── 板斧一：截断 ─────────────────────────────────────────────
def test_passthrough_when_fits():
    """预算内原样放行——不加任何标记（没省略就不该有省略标记）。"""
    text = "短文本" * 10
    assert ts.shape_result(text, max_tokens=600) == text


def test_truncate_marker_is_explicit():
    """超预算截断：标记注明省略字数、原文总长、续读 offset。"""
    text = "字" * 4000                       # 1000 tok > 600
    out = ts.shape_result(text, max_tokens=600)
    assert "已截断" in out and "原文共 4000 字" in out
    assert "offset=" in out and "省略" in out


def test_truncate_respects_budget_including_marker():
    """预算含标记：返回值总 token ≤ max_tokens（标记不是免费的）。"""
    tk = FakeTokenizer()
    out = ts.shape_result("字" * 40000, max_tokens=600, tokenizer=tk)
    assert tk.count(out) <= 600


def test_truncate_with_ref_path():
    """全文已外置时标记附引用路径（L06 工作区形态）。"""
    out = ts.shape_result("字" * 4000, max_tokens=100, ref_path="workspace/sources/S17.txt")
    assert "workspace/sources/S17.txt" in out


def test_every_omission_has_marker():
    """验收条款逐条版：一批长短不一的输入，凡内容变少必有标记。"""
    for n in (10, 100, 500, 2400, 2401, 5000, 40000):
        text = "字" * n
        out = ts.shape_result(text, max_tokens=600)
        if len(out) < len(text) or out != text:
            assert "已截断" in out, f"n={n} 有省略却无标记"
        else:
            assert "已截断" not in out, f"n={n} 无省略却有标记"


# ── 板斧二：分页 ─────────────────────────────────────────────
def test_paginate_first_page():
    text = "字" * 5000
    page = ts.paginate(text, offset=0, page_tokens=400)   # 1600 字/页
    assert page["has_more"] and page["next_offset"] == 1600
    assert "第 1–1600 字 / 共 5000 字" in page["content"]
    assert "续读 offset=1600" in page["content"]


def test_paginate_seamless_continuation():
    """翻页无缝：第二页内容与第一页正好衔接（无缺口无重叠）。"""
    text = "".join(chr(0x4E00 + i % 500) for i in range(4000))   # 确定性变化文本
    p1 = ts.paginate(text, offset=0, page_tokens=300)
    p2 = ts.paginate(text, offset=p1["next_offset"], page_tokens=300)
    body1 = p1["content"].split("]\n", 1)[1].rsplit("\n[📄", 1)[0]
    body2 = p2["content"].split("]\n", 1)[1].rsplit("\n[📄", 1)[0]
    assert body1 + body2 == text[:2400]


def test_paginate_last_page():
    page = ts.paginate("字" * 100, offset=0, page_tokens=400)
    assert not page["has_more"] and page["next_offset"] is None
    assert "已到末尾" in page["content"]


# ── 板斧三：引用 ─────────────────────────────────────────────
def test_reference_lossless_dump(tmp_path):
    """引用=无损外置：文件内容逐字节等于原文，窗口只进指针+头部。"""
    text = "重要全文内容。" * 300
    ref = ts.reference(text, "S17", tmp_path)
    from pathlib import Path
    assert Path(ref["path"]).read_text(encoding="utf-8") == text
    assert ref["total_chars"] == len(text)
    assert "S17" in ref["pointer"] and len(ref["pointer"]) < 300


# ── 错误也是返回值 ───────────────────────────────────────────
def test_shape_error_actionable():
    err = ts.shape_error("404", "源已失效（HTTP 404）", "跳过或换源")
    assert err.startswith("⛔") and "建议：跳过或换源" in err
    assert "Traceback" not in err and len(err) < 200


# ── researcher 集成 ──────────────────────────────────────────
class _CaptureLLM:
    def __init__(self):
        self.last_prompt = ""

    def invoke(self, prompt, **kw):
        self.last_prompt = prompt

        class _M:
            content = "mock 发现"
        return _M()


async def _run_researcher(monkeypatch, fat_text: str) -> str:
    from research_assistant import nodes

    async def fake_search(q):
        return fat_text

    monkeypatch.setattr(nodes, "web_search", fake_search)
    llm = _CaptureLLM()
    await nodes.make_researcher(llm)({"subtopic": "测试子题"})
    return llm.last_prompt


async def test_researcher_shapes_fat_result(monkeypatch):
    """开=肥检索结果被截断且标记进 prompt（在场率之外窗口立省）。"""
    monkeypatch.setitem(settings.__dict__, "enable_tool_shaping", True)
    monkeypatch.setitem(settings.__dict__, "tool_result_max_tokens", 200)
    fat = "[检索结果] 资料正文。" * 500                  # ≈1500 tok
    prompt = await _run_researcher(monkeypatch, fat)
    assert "已截断" in prompt and "原文共" in prompt
    assert len(prompt) < len(fat)


async def test_researcher_untouched_when_disabled(monkeypatch):
    """关（默认）=检索结果全文直给，prompt 与现状逐字节一致。"""
    fat = "[检索结果] 资料正文。" * 500
    prompt = await _run_researcher(monkeypatch, fat)
    assert fat in prompt and "已截断" not in prompt


async def test_researcher_small_result_not_marked(monkeypatch):
    """开了开关但结果在预算内：原样放行（不该有标记）。"""
    monkeypatch.setitem(settings.__dict__, "enable_tool_shaping", True)
    small = "[检索结果] 短资料。"
    prompt = await _run_researcher(monkeypatch, small)
    assert small in prompt and "已截断" not in prompt


def test_determinism():
    a = ts.shape_result("字" * 9999, max_tokens=300)
    b = ts.shape_result("字" * 9999, max_tokens=300)
    assert a == b
