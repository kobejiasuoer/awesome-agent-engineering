"""线上评估闭环单测：抽样 / 阈值过滤 / 入队 / 反馈（LLMOps L03）。

全程不打真实 API：evaluate_sample 用 monkeypatch 替换，只验证逻辑。
入队写到 tmp_path 隔离，不污染真实 eval/review_queue.jsonl。
"""
from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path

import pytest

from kb_qa import online_eval
from kb_qa.config import settings
from kb_qa.online_eval import (
    enqueue_feedback,
    enqueue_review,
    is_low_quality,
    should_sample,
)


# ── 抽样 ──────────────────────────────────────────────────────────
def test_should_sample_rate_boundary():
    """rate=1.0 必抽中，rate=0.0 必不抽中（边界确定性）。"""
    assert should_sample(1.0) is True
    assert should_sample(0.0) is False


def test_should_sample_probabilistic_distribution():
    """rate=0.5 时大量样本约半数抽中（统计性，允许波动）。"""
    rng = random.Random(0)
    hits = sum(1 for _ in range(2000) if should_sample(0.5, rng))
    # 1000 ± 80（5σ 容忍）
    assert 920 < hits < 1080


# ── 阈值过滤 ──────────────────────────────────────────────────────
def test_is_low_quality_min_logic():
    """用 min：任一维度低于阈值即低分（不被高分拉平）。"""
    assert is_low_quality({"faithfulness": 0.2, "answer_relevancy": 0.95}, 0.5) is True
    # 两个都高 → 不低分
    assert is_low_quality({"faithfulness": 0.8, "answer_relevancy": 0.9}, 0.5) is False


def test_is_low_quality_none_treated_as_low():
    """judge 没出分（None）→ 判低分（异常值得人工看）。"""
    assert is_low_quality({"faithfulness": None, "answer_relevancy": 0.9}, 0.5) is True


# ── 入队格式 ──────────────────────────────────────────────────────
def test_enqueue_review_writes_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """入队写 jsonl：一行一条 JSON，含必需字段。"""
    queue = tmp_path / "review_queue.jsonl"
    monkeypatch.setattr(settings, "eval_review_queue_path", str(queue))
    enqueue_review(
        question="试用期多久", answer="3 个月",
        contexts=["试用期 3 个月"], scores={"faithfulness": 0.3, "answer_relevancy": 0.8},
        source="sample", thread_id="t1",
    )
    lines = queue.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["question"] == "试用期多久"
    assert rec["scores"]["faithfulness"] == 0.3
    assert rec["source"] == "sample"
    assert rec["thread_id"] == "t1"
    assert "ts" in rec


def test_enqueue_review_appends_not_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """多次入队追加写，不覆盖历史（jsonl 的核心优势）。"""
    queue = tmp_path / "review_queue.jsonl"
    monkeypatch.setattr(settings, "eval_review_queue_path", str(queue))
    for i in range(3):
        enqueue_review("q", f"a{i}", ["c"], {"faithfulness": 0.1, "answer_relevancy": 0.1},
                       source="sample")
    assert len(queue.read_text(encoding="utf-8").splitlines()) == 3


# ── 反馈路径 ──────────────────────────────────────────────────────
def test_enqueue_feedback_down_always_enqueues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """点踩 100% 入队（强信号，不抽样）。"""
    queue = tmp_path / "review_queue.jsonl"
    monkeypatch.setattr(settings, "eval_review_queue_path", str(queue))
    enqueue_feedback("q", "bad answer", ["c"], "down", thread_id="t1")
    rec = json.loads(queue.read_text(encoding="utf-8").splitlines()[0])
    assert rec["source"] == "feedback"
    assert rec["rating"] == "down"
    assert rec["scores"] is None  # 反馈不跑 judge


def test_enqueue_feedback_up_does_not_enqueue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """点赞不入队（那是好样本，不需要优化）。"""
    queue = tmp_path / "review_queue.jsonl"
    monkeypatch.setattr(settings, "eval_review_queue_path", str(queue))
    enqueue_feedback("q", "good answer", ["c"], "up")
    assert not queue.exists()


# ── 闭环主入口（mock judge）──────────────────────────────────────
def test_sample_and_evaluate_low_quality_enqueues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """抽中 + 低分 → 入队（mock evaluate_sample 返回低分）。"""
    queue = tmp_path / "review_queue.jsonl"
    monkeypatch.setattr(settings, "eval_review_queue_path", str(queue))
    monkeypatch.setattr(settings, "eval_sample_rate", 1.0)   # 100% 抽中

    async def fake_eval(q, a, c):
        return {"faithfulness": 0.2, "answer_relevancy": 0.3}  # 低分
    monkeypatch.setattr(online_eval, "evaluate_sample", fake_eval)

    asyncio.run(online_eval.sample_and_evaluate("q", "bad", ["c1"], thread_id="t1"))
    lines = queue.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["source"] == "sample"


def test_sample_and_evaluate_not_sampled_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """未抽中 → 不评估不入队。"""
    queue = tmp_path / "review_queue.jsonl"
    monkeypatch.setattr(settings, "eval_review_queue_path", str(queue))
    monkeypatch.setattr(settings, "eval_sample_rate", 0.0)   # 永不抽中
    asyncio.run(online_eval.sample_and_evaluate("q", "a", ["c"]))
    assert not queue.exists()


def test_sample_and_evaluate_high_quality_not_enqueued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """抽中但高分 → 不入队（pass）。"""
    queue = tmp_path / "review_queue.jsonl"
    monkeypatch.setattr(settings, "eval_review_queue_path", str(queue))
    monkeypatch.setattr(settings, "eval_sample_rate", 1.0)

    async def fake_eval(q, a, c):
        return {"faithfulness": 0.9, "answer_relevancy": 0.9}  # 高分
    monkeypatch.setattr(online_eval, "evaluate_sample", fake_eval)

    asyncio.run(online_eval.sample_and_evaluate("q", "good", ["c"]))
    assert not queue.exists()
