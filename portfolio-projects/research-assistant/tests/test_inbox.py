"""Ambient L05 测试：收件箱与自主级别。

测试原则（对齐 conftest.py）：
    - 收件箱/发布注册表用 tmp_path 隔离
    - submit_approval 用 monkeypatch 假体（不进真实图）
    - 灵魂用例：stay_silent 不产生条目 + agency 三级的副作用边界
"""
from __future__ import annotations

import asyncio

import pytest

from research_assistant import config, inbox, publish
from research_assistant.clock import FakeClock
from research_assistant.inbox import (
    KIND_ALERT, KIND_APPROVAL, KIND_DIGEST, KIND_NOTIFY, KIND_PROPOSAL,
    accept_proposal, add_entry, apply_agency, approve_entry, build_digest,
    deliver, file_approval_request, list_entries, mark_read,
    pending_approvals, resolve, unread_count,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "_DB_PATH", str(tmp_path / "inbox.db"))
    monkeypatch.setattr(publish, "_DB_PATH", str(tmp_path / "publish.db"))
    config.settings.__dict__["agency_level"] = "notify"
    config.settings.__dict__["publish_dry_run"] = False
    yield
    config.settings.__dict__["agency_level"] = "notify"


# ── 基础 CRUD ────────────────────────────────────────────────

def test_add_list_unread_mark_read():
    e = add_entry(KIND_NOTIFY, "主题", "标题", "正文", level="major")
    assert unread_count() == 1
    got = list_entries(kind=KIND_NOTIFY)[0]
    assert got["title"] == "标题" and got["level"] == "major" and not got["read"]
    mark_read(e["entry_id"])
    assert unread_count() == 0


def test_kind_filter_and_invalid_kind():
    add_entry(KIND_NOTIFY, "t", "n")
    add_entry(KIND_ALERT, "t", "a")
    assert len(list_entries(kind=KIND_ALERT)) == 1
    with pytest.raises(ValueError):
        add_entry("weird", "t", "x")


# ── deliver：L04 决策 → 收件箱 ───────────────────────────────

def _decision(d, level="major", **kw):
    return {"decision": d, "level": level, "reason": "理由", **kw}


def test_deliver_notify_now_creates_notify_entry():
    e = deliver(_decision("notify_now"), "主题", "简报内容", thread_id="t1")
    assert e["kind"] == KIND_NOTIFY and e["level"] == "major"
    assert e["thread_id"] == "t1"


def test_deliver_digest_creates_digest_entry():
    e = deliver(_decision("add_to_digest", level="minor"), "主题", "简报")
    assert e["kind"] == KIND_DIGEST


def test_deliver_silent_creates_nothing():
    """灵魂用例：沉默 = 不产生任何条目（不是「产生一条沉默条目」）。"""
    assert deliver(_decision("stay_silent", level="none"), "主题", "x") is None
    assert unread_count() == 0


def test_deliver_quota_exhausted_marks_title():
    e = deliver(_decision("add_to_digest", quota_exhausted=True), "主题", "x")
    assert e["title"].startswith("⚠ 配额尽降级")


# ── digest 日结 ──────────────────────────────────────────────

def test_build_digest_collects_and_marks_read():
    deliver(_decision("add_to_digest", level="minor"), "主题A", "a")
    deliver(_decision("add_to_digest", level="minor"), "主题B", "b")
    deliver(_decision("notify_now"), "主题C", "c")   # notify 不进摘要
    digest = build_digest(clock=FakeClock())
    assert "2 条" in digest and "主题A" in digest and "主题C" not in digest
    # 已汇总的标记已读：再次日结不重复
    assert "无条目" in build_digest(clock=FakeClock())
    # notify 条目不受影响
    assert unread_count(KIND_NOTIFY) == 1


# ── 隔夜审批（复用 submit_approval）──────────────────────────

def test_file_and_list_pending_approvals():
    e = file_approval_request("t-42", "主题", "要发布的摘要")
    assert e["kind"] == KIND_APPROVAL
    pend = pending_approvals()
    assert len(pend) == 1 and pend[0]["thread_id"] == "t-42"
    resolve(e["entry_id"], "approved")
    assert pending_approvals() == []


def test_approve_entry_resumes_via_submit_approval(monkeypatch):
    captured = {}

    async def fake_submit(thread_id, approved, comment=""):
        captured.update(thread_id=thread_id, approved=approved)
        return {"publish_result": {"status": "published"}}

    monkeypatch.setattr("research_assistant.service.submit_approval", fake_submit)
    e = file_approval_request("t-42", "主题", "摘要")
    out = asyncio.run(approve_entry(e["entry_id"], True))
    assert out["status"] == "resumed" and captured["thread_id"] == "t-42"
    assert inbox.get_entry(e["entry_id"])["resolution"] == "approved"


def test_approve_entry_reject_path(monkeypatch):
    async def fake_submit(thread_id, approved, comment=""):
        return {"publish_result": {"status": "rejected"}}
    monkeypatch.setattr("research_assistant.service.submit_approval", fake_submit)
    e = file_approval_request("t-1", "主题", "摘要")
    asyncio.run(approve_entry(e["entry_id"], False))
    assert inbox.get_entry(e["entry_id"])["resolution"] == "rejected"


def test_approve_entry_idempotent(monkeypatch):
    async def fake_submit(thread_id, approved, comment=""):
        return {}
    monkeypatch.setattr("research_assistant.service.submit_approval", fake_submit)
    e = file_approval_request("t-1", "主题", "摘要")
    asyncio.run(approve_entry(e["entry_id"], True))
    out2 = asyncio.run(approve_entry(e["entry_id"], True))
    assert out2["status"] == "already_resolved"   # 不重复 resume


# ── agency ladder：三级的副作用边界 ──────────────────────────

def test_agency_notify_touches_no_side_effect(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("notify 级别不该碰 publish")
    monkeypatch.setattr("research_assistant.publish.publish_report", boom)
    out = apply_agency("主题", "报告", "t-1")
    assert out == {"mode": "notify", "action": "none"}


def test_agency_act_publishes_and_leaves_trace():
    config.settings.__dict__["agency_level"] = "act"
    out = apply_agency("主题", "报告内容", "t-act")
    assert out["mode"] == "act" and out["publish"]["published"] is True
    trace = list_entries(kind=KIND_NOTIFY)
    assert any("已代你发布" in e["title"] for e in trace)   # 先斩后奏必须留痕


def test_agency_propose_then_accept():
    config.settings.__dict__["agency_level"] = "propose"
    out = apply_agency("主题", "草稿报告", "t-prop")
    assert out["mode"] == "propose"
    entry = inbox.get_entry(out["entry_id"])
    assert entry["kind"] == KIND_PROPOSAL and not entry["resolved"]
    # 人确认 → 真正发布 + 落章
    result = accept_proposal(out["entry_id"])
    assert result["publish"]["published"] is True
    assert inbox.get_entry(out["entry_id"])["resolution"] == "accepted"


def test_agency_act_replay_blocked_by_idempotency():
    """act 模式连发两次同内容：幂等键挡重放（复用 agent-ops L04 资产）。"""
    config.settings.__dict__["agency_level"] = "act"
    first = apply_agency("主题", "同一份报告", "t-same")
    second = apply_agency("主题", "同一份报告", "t-same")
    assert first["publish"]["idempotent_replay"] is False
    assert second["publish"]["idempotent_replay"] is True   # 重放被幂等键挡下
