"""长途任务信源与裸基线测试（Harness 课程 L00）。

锁死三类契约：
    1. 语料确定性：双跑逐字节一致（收益矩阵可复现的地基）
    2. 事实埋点契约：probe 全语料唯一；early <450 字 / late >600 字；
       营销文档零事实（改道跳过不损失在场率）；矛盾对跨会话分布
    3. 裸基线结局：测量=物理不可能、强制=中途死亡、硬截断=活着但失忆、
       流水线参照=便宜但无契约——四行结论是之后每课收益对照的基准
"""
from __future__ import annotations

import hashlib
import json

from eval_agent.long_haul import (
    CONTRADICTION_PAIR, DOC_IDS, KEY_FACTS, N_SOURCES, OVERSIZED_DOC_IDS,
    SESSION_SPLIT, WINDOW_LIMIT_TOKENS, FakeTokenizer, LongHaulSource,
    build_docs, contradiction_discoverable, presence,
    run_naive_longhaul, run_pipeline_reference,
)


def _corpus_md5() -> str:
    docs = build_docs()
    joined = "".join(docs[d].content for d in DOC_IDS)
    return hashlib.md5(joined.encode("utf-8")).hexdigest()


# ── 语料契约 ─────────────────────────────────────────────────
def test_corpus_deterministic():
    """双跑逐字节一致——确定性是全部收益对照的地基。"""
    assert _corpus_md5() == _corpus_md5()


def test_corpus_shape():
    """30 源；3 个超长（>2000 假 token）；普通源在 300–800 之间。"""
    docs = build_docs()
    tk = FakeTokenizer()
    assert len(docs) == N_SOURCES == 30
    for doc_id in DOC_IDS:
        tokens = tk.count(docs[doc_id].content)
        if doc_id in OVERSIZED_DOC_IDS:
            assert tokens > 2000, f"{doc_id} 应为超长文档"
        else:
            assert 300 <= tokens <= 800, f"{doc_id} 普通源应在 300–800 token（实际 {tokens}）"


def test_probes_unique_in_corpus():
    """每个 probe 全语料恰好出现一次，且在自己的文档里（机械在场检测的前提）。"""
    docs = build_docs()
    corpus = "".join(docs[d].content for d in DOC_IDS)
    for f in KEY_FACTS:
        assert corpus.count(f.probe) == 1, f"{f.fact_id} probe 应全语料唯一"
        assert f.probe in docs[f.doc_id].content, f"{f.fact_id} 应埋在 {f.doc_id}"


def test_fact_placement_contract():
    """early 事实起始 <450 字（硬截断砍不掉）；late 事实起始 >600 字（只留开头必丢）。"""
    docs = build_docs()
    early_n = 0
    for f in KEY_FACTS:
        pos = docs[f.doc_id].content.index(f.probe)
        if f.early:
            early_n += 1
            assert pos < 450, f"{f.fact_id} early 埋点越界（{pos}）"
        else:
            assert pos > 600, f"{f.fact_id} late 埋点过浅（{pos}）"
    assert early_n == 8  # 8 early + 12 late（任务书 1.7）


def test_marketing_docs_carry_no_facts():
    """营销文档零关键事实——改道跳过它们不损失在场率（L07 的公平性前提）。"""
    docs = build_docs()
    fact_docs = {f.doc_id for f in KEY_FACTS}
    for doc_id in fact_docs:
        assert docs[doc_id].category != "marketing"


def test_contradiction_pair_spans_sessions():
    """矛盾对跨会话分布（F06 在会话 1，F16 在会话 2）——跨会话线才有考点。"""
    by_id = {f.fact_id: f for f in KEY_FACTS}
    a, b = (by_id[fid] for fid in CONTRADICTION_PAIR)
    assert int(a.doc_id[1:]) <= SESSION_SPLIT < int(b.doc_id[1:])


def test_fetch_counter():
    """fetch 计数器——「重复读取浪费」指标的数据源。"""
    src = LongHaulSource()
    src.fetch("S01")
    src.fetch("S01")
    src.fetch("S02")
    assert src.fetch_counts == {"S01": 2, "S02": 1}
    assert src.total_fetches == 3


def test_fake_tokenizer_convention():
    """len//4 口径（与 cost_budget 现有估算一致）；空串保底 1。"""
    tk = FakeTokenizer()
    assert tk.count("a" * 400) == 100
    assert tk.count("") == 1


# ── 裸基线结局 ────────────────────────────────────────────────
def test_naive_measure_mode():
    """测量模式：跑完 30 源但「物理不可能」——中途已越限，工具结果占大头。"""
    r = run_naive_longhaul("measure")
    assert r["completed_sources"] == 30 and r["died_at"] is None
    assert 10 <= r["first_overflow_source"] <= 12
    assert r["peak_window_tokens"] > 2 * WINDOW_LIMIT_TOKENS  # 终局窗口远超物理限制
    assert r["presence_hits"] == 20 and r["contradiction_discoverable"]
    comp = r["composition_at_overflow"]
    assert comp["tool_results"] / sum(comp.values()) > 0.6  # 最大消耗方


def test_naive_enforce_mode():
    """强制模式：越限即死——死亡点与测量模式的首次越限点一致，无合成无在场。"""
    m = run_naive_longhaul("measure")
    r = run_naive_longhaul("enforce")
    assert r["died_at"] == m["first_overflow_source"]
    assert r["completed_sources"] == r["died_at"] - 1
    assert r["presence_hits"] == 0 and not r["contradiction_discoverable"]


def test_hard_truncate_mode():
    """硬截断：活着但失忆——恰好只剩 8 个 early 事实，矛盾断一臂，且静默无标记。"""
    r = run_naive_longhaul("hard_truncate")
    assert r["completed_sources"] == 30 and r["died_at"] is None
    assert r["peak_window_tokens"] <= WINDOW_LIMIT_TOKENS  # 截断买到了「活着」
    assert r["presence_hits"] == 8                          # 但买不到「记得」
    assert set(r["missing_facts"]) == {f.fact_id for f in KEY_FACTS if not f.early}
    assert not r["contradiction_discoverable"]              # F16 被砍，矛盾不可见
    assert r["silent_omission"]                             # 截断处没有任何省略标记


def test_pipeline_reference():
    """v4 流水线参照：永不溢出、便宜，但无契约压缩=运气，跨源矛盾无保障。"""
    r = run_pipeline_reference()
    assert r["completed_sources"] == 30 and not r["over_limit"]
    assert r["peak_window_tokens"] < WINDOW_LIMIT_TOKENS
    assert r["presence_hits"] == 8          # 机制演示（规则公开：只留每篇开头）
    assert not r["contradiction_discoverable"]
    assert r["silent_omission"]             # 压缩丢弃同样无标记无审计


def test_all_modes_double_run_identical():
    """四种跑法双跑结果逐字段一致（收益矩阵确定性传统）。"""
    for run in (lambda: run_naive_longhaul("measure"),
                lambda: run_naive_longhaul("enforce"),
                lambda: run_naive_longhaul("hard_truncate"),
                run_pipeline_reference):
        a = json.dumps(run(), ensure_ascii=False, sort_keys=True)
        b = json.dumps(run(), ensure_ascii=False, sort_keys=True)
        assert a == b


def test_presence_helpers():
    """在场检测：probe 命中计数 + 矛盾需双方同时在场。"""
    by_id = {f.fact_id: f for f in KEY_FACTS}
    text_one_side = by_id["F06"].probe
    hits, missing = presence(text_one_side)
    assert hits == 1 and "F16" in missing
    assert not contradiction_discoverable(text_one_side)
    assert contradiction_discoverable(text_one_side + by_id["F16"].probe)
