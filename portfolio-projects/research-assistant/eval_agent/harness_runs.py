"""Harness 机制的长途任务跑法集（逐课扩展，L09 收益矩阵的原料）。

L00 的裸基线住 long_haul.py（冻结不动）；本模块从 L02 起逐课新增
「装了第 N 层机制」的跑法：
    L02  run_compacted_longhaul   登记式压缩：裸奔死于 S11 → 30 源跑完，
                                  在场率 8/20（硬截断）→ 20/20（登记契约）

诚实标注：
    - 摘要器为确定性假实现（head_summarizer 只留前 80 字）——mock 测的是
      机械纪律（登记存活/审计完整），不是摘要语义保真（L09 真模型章抽查）。
    - 「研究中登记哪些事实」在真实系统里是 LLM 的判断（判断交给模型）；
      本跑法用剧本代演（研读到某源时登记该源的 KEY_FACTS）——机制演示，
      判定质量另议：登记漏了的事实同样会丢，L02 README 讲清这个边界。
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJ = Path(__file__).resolve().parent.parent
if str(_PROJ / "src") not in sys.path:
    sys.path.insert(0, str(_PROJ / "src"))

from research_assistant.compactor import (  # noqa: E402
    Compactor, PinnedFact, WindowItem, head_summarizer,
)
from research_assistant.context_ledger import FakeTokenizer  # noqa: E402

from eval_agent.long_haul import (  # noqa: E402
    DOC_IDS, KEY_FACTS, N_SOURCES, SYSTEM_PROMPT, WINDOW_LIMIT_TOKENS,
    LongHaulSource, contradiction_discoverable, presence,
)

_STUDY_INSTR = "请研读下一篇文档并记录要点。"
_SYNTHESIS_INSTR = (
    "全部信源已研读完毕。现在基于以上全部材料撰写最终综合报告："
    "覆盖关键事实、指出信源间的矛盾（若有）、给出结论。"
)

_FACTS_BY_DOC: dict[str, list] = {}
for _f in KEY_FACTS:
    _FACTS_BY_DOC.setdefault(_f.doc_id, []).append(_f)


def run_compacted_longhaul(*, register_pins: bool = True,
                           window_limit: int = WINDOW_LIMIT_TOKENS,
                           threshold_pct: float = 0.60,
                           target_pct: float = 0.50,
                           summarizer=None,
                           tokenizer: FakeTokenizer | None = None) -> dict:
    """长程单窗 + 登记式压缩：L02 的主角跑法。

    register_pins=True   研读到某源时登记该源关键事实（剧本代演 LLM 判定）
    register_pins=False  对照组：同样压缩、同样摘要，**只是不登记**——
                         演示「无契约压缩=运气」（关键事实随原文一起蒸发）
    """
    tk = tokenizer or FakeTokenizer()
    src = LongHaulSource()
    catalog = src.catalog_text()
    base = tk.count(SYSTEM_PROMPT) + tk.count(catalog) + tk.count(_STUDY_INSTR)
    comp = Compactor(tokenizer=tk, limit=window_limit, threshold_pct=threshold_pct,
                     target_pct=target_pct, summarizer=summarizer or head_summarizer)

    items: list[WindowItem] = []
    peak = 0
    tokens_billed = 0
    died_at = None

    for no, doc_id in enumerate(DOC_IDS, start=1):
        text = src.fetch(doc_id)
        if register_pins:
            for f in _FACTS_BY_DOC.get(doc_id, []):
                comp.register(PinnedFact(f.fact_id, f.statement))
        incoming = tk.count(text)
        # 水位检查在装入新文档前：留出新文档的位置（extra=基座+新文档）
        if comp.should_compact(sum(tk.count(i.text) for i in items) + base + incoming):
            items, _ = comp.compact(items, extra_tokens=base + incoming)
        items.append(WindowItem(doc_id, "tool_result", text))
        items.append(WindowItem(f"note-{no}", "note",
                                f"已研读 {doc_id}《{src.doc(doc_id).title}》，要点已记。"))
        total = base + sum(tk.count(i.text) for i in items)
        peak = max(peak, total)
        tokens_billed += total
        if total > window_limit:      # 压缩后仍越限=设计失败（本跑法不应发生）
            died_at = no
            break

    completed = (died_at - 1) if died_at else N_SOURCES
    if died_at is None:
        # 合成前最后一次水位检查（合成指令也要占位）
        syn_extra = tk.count(SYSTEM_PROMPT) + tk.count(catalog) + tk.count(_SYNTHESIS_INSTR)
        if comp.should_compact(sum(tk.count(i.text) for i in items) + syn_extra):
            items, _ = comp.compact(items, extra_tokens=syn_extra)
        syn_text = (SYSTEM_PROMPT + catalog + "".join(i.text for i in items)
                    + _SYNTHESIS_INSTR)
        syn_window = tk.count(syn_text)
        peak = max(peak, syn_window)
        tokens_billed += syn_window
        hits, missing = presence(syn_text)
        contradiction = contradiction_discoverable(syn_text)
    else:
        syn_window = 0
        hits, missing = 0, [f.fact_id for f in KEY_FACTS]
        contradiction = False

    return {
        "mode": f"compacted({'pinned' if register_pins else 'no-pin'})",
        "completed_sources": completed,
        "died_at": died_at,
        "peak_window_tokens": peak,
        "synthesis_window_tokens": syn_window,
        "presence": f"{hits}/{len(KEY_FACTS)}",
        "presence_hits": hits,
        "missing_facts": missing,
        "contradiction_discoverable": contradiction,
        "compactions": len(comp.records),
        "dropped_total": sum(len(r.dropped_items) for r in comp.records),
        "pinned_verified_all": all(r.pinned_verified for r in comp.records),
        "audit_report": comp.audit_report(),
        "tokens_billed": tokens_billed,
        "total_fetches": src.total_fetches,
    }
