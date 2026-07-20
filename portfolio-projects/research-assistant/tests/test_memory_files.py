"""跨会话记忆文件测试（Harness 课程 L03）。

锁死四类契约：
    1. 写入纪律 gate：临时参数拒收、已记录拒收、空候选拒收、合规通过
    2. 文件与索引：单事实单文件、同名 upsert 不重复、删除可反悔、索引=文件视图
    3. 召回：trigger 命中才读正文、注入块自带防污染提示、未命中零注入
    4. writer 集成：开关开=偏好进 prompt（跨会话生效）；关=零差异
"""
from __future__ import annotations

import pytest

from research_assistant import memory_files as mf
from research_assistant.config import settings


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """每测隔离：记忆目录指向 tmp_path，开关显式关（默认态）。"""
    monkeypatch.setitem(settings.__dict__, "memory_files_dir", str(tmp_path / "mem"))
    monkeypatch.setitem(settings.__dict__, "enable_memory_files", False)
    yield


def _pref(name="report-style", body="报告必须用中文撰写；正文控制在 500 字以内。",
          triggers="报告,写作,格式", **kw) -> mf.MemoryCandidate:
    return mf.MemoryCandidate(name=name, description="报告语言与长度偏好（用户纠正）",
                              body=body, triggers=triggers, **kw)


# ── 写入纪律 ─────────────────────────────────────────────────
def test_gate_accepts_durable_preference():
    ok, reason = mf.gate_memory(_pref())
    assert ok and reason == "通过"


def test_gate_rejects_session_scope():
    """「这次先查 3 个来源」只对本轮有意义——拒收。"""
    ok, reason = mf.gate_memory(_pref(name="temp", body="本轮只查 3 个来源",
                                      scope="session"))
    assert not ok and "临时参数" in reason


def test_gate_rejects_already_recorded():
    """仓库/代码已记录的事实不重复存储（记忆不是代码的镜像）。"""
    ok, reason = mf.gate_memory(_pref(already_recorded=True))
    assert not ok and "已记录" in reason


def test_gate_rejects_empty_and_unknown_type():
    assert not mf.gate_memory(_pref(body="  "))[0]
    assert not mf.gate_memory(_pref(mtype="diary"))[0]


def test_rejected_candidate_writes_nothing():
    path, reason = mf.write_memory(_pref(scope="session"))
    assert path is None and mf.list_memories() == []


# ── 文件与索引 ───────────────────────────────────────────────
def test_write_creates_file_and_index():
    path, verb = mf.write_memory(_pref())
    assert path is not None and path.exists() and verb == "写入"
    idx = mf.load_index()
    assert "[report-style]" in idx and "报告语言与长度偏好" in idx


def test_upsert_updates_not_duplicates():
    """用户改主意是常态：同名=更新原文件，索引仍只有一行。"""
    mf.write_memory(_pref())
    _, verb = mf.write_memory(_pref(body="报告改为 800 字以内。"))
    assert verb == "更新"
    assert len(mf.list_memories()) == 1
    assert "800 字" in mf.read_memory("report-style")
    assert mf.load_index().count("[report-style]") == 1


def test_delete_memory_and_index_sync():
    """记错了删（可反悔），索引同步消行。"""
    mf.write_memory(_pref())
    assert mf.delete_memory("report-style")
    assert mf.list_memories() == [] and "[report-style]" not in mf.load_index()
    assert not mf.delete_memory("report-style")     # 再删=False（幂等）


def test_index_sorted_deterministic():
    """索引按名排序——双写顺序不同，索引逐字节一致（确定性传统）。"""
    mf.write_memory(_pref(name="b-mem", triggers="x"))
    mf.write_memory(_pref(name="a-mem", triggers="y"))
    idx1 = mf.load_index()
    mf.delete_memory("a-mem")
    mf.delete_memory("b-mem")
    mf.write_memory(_pref(name="a-mem", triggers="y"))
    mf.write_memory(_pref(name="b-mem", triggers="x"))
    assert mf.load_index() == idx1


# ── 召回 ─────────────────────────────────────────────────────
def test_match_by_trigger_only():
    """trigger 命中才召回：正文再相关，触发词不中就不读（按需的机械层）。"""
    mf.write_memory(_pref())
    assert mf.match_memories("请写一份研究报告") == ["report-style"]
    assert mf.match_memories("查一下天气") == []


def test_recall_block_has_pollution_guard():
    """注入块自带「过时以当前对话为准」——记忆是背景不是指令。"""
    mf.write_memory(_pref())
    block = mf.recall_block("写报告")
    assert "500 字" in block and "以当前对话为准" in block
    assert mf.recall_block("无关查询") == ""


def test_index_far_cheaper_than_bodies():
    """索引常驻的经济性：索引 token 远小于正文总量（账本量证）。"""
    from research_assistant.context_ledger import FakeTokenizer
    for i in range(5):
        mf.write_memory(_pref(name=f"mem-{i}", body="很长的正文。" * 200,
                              triggers=f"t{i}"))
    tk = FakeTokenizer()
    index_cost = tk.count(mf.load_index())
    bodies_cost = sum(tk.count(mf.read_memory(f"mem-{i}")) for i in range(5))
    assert index_cost < bodies_cost / 10


# ── writer 集成 ──────────────────────────────────────────────
class _CaptureLLM:
    """捕获 prompt 的假 LLM（验证注入内容）。"""

    def __init__(self):
        self.last_prompt = ""

    def invoke(self, prompt, **kw):
        self.last_prompt = prompt

        class _M:
            content = "mock 报告"
        return _M()


def _run_writer(llm) -> None:
    from research_assistant import nodes
    nodes.make_writer(llm)({"research_summary": "关于 Agent 生态的研究报告摘要",
                            "feedback": "", "truncated": False})


def test_writer_injects_memory_when_enabled(monkeypatch):
    """跨会话生效：会话 1 写入的偏好，会话 2 的 writer prompt 里在场。"""
    mf.write_memory(_pref())
    monkeypatch.setitem(settings.__dict__, "enable_memory_files", True)
    llm = _CaptureLLM()
    _run_writer(llm)
    assert "500 字" in llm.last_prompt and "以当前对话为准" in llm.last_prompt


def test_writer_clean_when_disabled():
    """开关关（默认）：写过记忆也不注入——prompt 与现状逐字节一致。"""
    mf.write_memory(_pref())
    llm = _CaptureLLM()
    _run_writer(llm)
    assert "500 字" not in llm.last_prompt and "跨会话操作记忆" not in llm.last_prompt


def test_writer_no_injection_when_no_trigger_hit(monkeypatch):
    """开了开关但 trigger 未命中：同样零注入（按需不是常注入）。"""
    mf.write_memory(_pref(triggers="财务,预算"))
    monkeypatch.setitem(settings.__dict__, "enable_memory_files", True)
    llm = _CaptureLLM()
    _run_writer(llm)
    assert "跨会话操作记忆" not in llm.last_prompt
