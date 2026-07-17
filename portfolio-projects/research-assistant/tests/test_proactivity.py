"""Ambient L04 测试：打扰决策（判级 + 政策 + 配额）。

测试原则（对齐 conftest.py）：
    - LLM judge 用 FakeLLM（不联网）；规则降级路径显式测
    - 配额库用 tmp_path 隔离；「一天」用 FakeClock 拨表
    - 灵魂用例：解析失败降级 minor（宁攒勿丢）+ 配额尽 major 降 digest
"""
from __future__ import annotations

import pytest

from research_assistant import config, proactivity
from research_assistant.clock import FakeClock, DAY_SECONDS
from research_assistant.proactivity import (
    ADD_TO_DIGEST, NOTIFY_NOW, STAY_SILENT,
    Judgement, classify_change, decide, quota_used, day_key,
)

from tests.conftest import FakeLLM


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(proactivity, "_DB_PATH", str(tmp_path / "quota.db"))
    config.settings.__dict__["proactivity_policy"] = "threshold"
    config.settings.__dict__["daily_interrupt_quota"] = 2
    yield


# ── 判级：LLM judge ──────────────────────────────────────────

def test_classify_major_via_llm():
    llm = FakeLLM({}, default="major\n结论反转，直接影响选型决策")
    j = classify_change("✏️ 修正: 框架X撤回AGUI支持", llm=llm)
    assert j.level == "major" and not j.degraded
    assert "反转" in j.reason


def test_classify_none_via_llm():
    llm = FakeLLM({}, default="none\n无实质内容")
    j = classify_change("确认无变化", llm=llm)
    assert j.level == "none"


def test_classify_parse_failure_degrades_to_minor():
    """灵魂用例：LLM 输出解析不出级别 → minor + degraded（宁攒勿丢，不静默）。"""
    llm = FakeLLM({}, default="我觉得这个更新还挺重要的，建议看看")
    j = classify_change("某简报", llm=llm)
    assert j.level == "minor" and j.degraded
    assert "宁攒勿丢" in j.reason


def test_classify_llm_exception_falls_back_to_rules():
    class BoomLLM:
        def invoke(self, prompt):
            raise RuntimeError("LLM 挂了")
    j = classify_change("✏️ 更正: 旧结论已不成立", llm=BoomLLM())
    assert j.level == "major" and j.degraded    # 规则接住重大信号词


def test_empty_brief_is_none():
    assert classify_change("", llm=None).level == "none"


# ── 判级：规则降级 ───────────────────────────────────────────

def test_rule_classify_levels():
    assert classify_change("✏️ 修正：撤回支持", llm=None).level == "major"
    assert classify_change("🆕 新增：发布 0.3.2 补丁", llm=None).level == "minor"
    assert classify_change("天气不错", llm=None).level == "none"
    assert classify_change("🆕 x", llm=None).degraded   # 规则路径诚实标注降级


# ── 决策：threshold 政策 + 配额 ──────────────────────────────

def test_major_notifies_within_quota():
    clock = FakeClock()
    out = decide(Judgement("major", "r"), clock=clock)
    assert out["decision"] == NOTIFY_NOW
    assert out["quota_used"] == 1 and not out["quota_exhausted"]


def test_minor_goes_to_digest_without_consuming_quota():
    clock = FakeClock()
    out = decide(Judgement("minor", "r"), clock=clock)
    assert out["decision"] == ADD_TO_DIGEST
    assert quota_used(day_key(clock.now())) == 0


def test_none_stays_silent():
    out = decide(Judgement("none", "r"), clock=FakeClock())
    assert out["decision"] == STAY_SILENT


def test_quota_exhaustion_downgrades_major_to_digest():
    """配额纪律：第 3 个 major 降 digest，且 quota_exhausted 可审计。"""
    clock = FakeClock()
    assert decide(Judgement("major", "1"), clock=clock)["decision"] == NOTIFY_NOW
    assert decide(Judgement("major", "2"), clock=clock)["decision"] == NOTIFY_NOW
    out3 = decide(Judgement("major", "3"), clock=clock)
    assert out3["decision"] == ADD_TO_DIGEST
    assert out3["quota_exhausted"] is True
    assert out3["quota_used"] == 2      # 没有超发


def test_quota_resets_next_day():
    clock = FakeClock()
    decide(Judgement("major", "1"), clock=clock)
    decide(Judgement("major", "2"), clock=clock)
    clock.advance(DAY_SECONDS)          # 次日
    out = decide(Judgement("major", "3"), clock=clock)
    assert out["decision"] == NOTIFY_NOW and out["quota_used"] == 1


def test_quota_persists_in_sqlite():
    """配额是持久状态（daemon 重启不清零——不然崩一次就白嫖配额）。"""
    clock = FakeClock()
    decide(Judgement("major", "1"), clock=clock)
    assert quota_used(day_key(clock.now())) == 1   # 独立读取（新连接）


# ── 决策：其他政策 ───────────────────────────────────────────

def test_policy_all_notifies_even_minor():
    out = decide(Judgement("minor", "r"), clock=FakeClock(), policy="all")
    assert out["decision"] == NOTIFY_NOW


def test_policy_digest_only_never_interrupts():
    out = decide(Judgement("major", "r"), clock=FakeClock(), policy="digest_only")
    assert out["decision"] == ADD_TO_DIGEST


def test_policy_defaults_from_settings():
    config.settings.__dict__["proactivity_policy"] = "digest_only"
    out = decide(Judgement("major", "r"), clock=FakeClock())
    assert out["decision"] == ADD_TO_DIGEST
