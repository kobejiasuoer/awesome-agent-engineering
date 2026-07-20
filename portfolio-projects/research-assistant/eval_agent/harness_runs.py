"""Harness 机制的长途任务跑法集（逐课扩展，L09 收益矩阵的原料）。

L00 的裸基线住 long_haul.py（冻结不动）；本模块从 L02 起逐课新增
「装了第 N 层机制」的跑法：
    L02  run_compacted_longhaul   登记式压缩：裸奔死于 S11 → 30 源跑完，
                                  在场率 8/20（硬截断）→ 20/20（登记契约）
    L05  run_isolated_longhaul    子代理隔离：过程在子窗口烧，主窗口只涨
                                  结论——主窗峰值 5,272（压缩）→ ~1.7k（隔离），
                                  溢出的子代理结构化失败，主流程不陪葬

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
from research_assistant.context_ledger import FakeTokenizer, WindowLedger  # noqa: E402
from research_assistant.subagent import SubagentRunner  # noqa: E402
from research_assistant.tool_shaping import shape_result  # noqa: E402

from eval_agent.long_haul import (  # noqa: E402
    DOC_IDS, KEY_FACTS, N_SOURCES, SESSION_SPLIT, SYSTEM_PROMPT, TOPIC,
    WINDOW_LIMIT_TOKENS, LongHaulSource, contradiction_discoverable, presence,
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


_WORKER_INSTR = "你是子代理研究员。研读这一篇文档，提取可核查的关键事实，回传结论（不回传原文）。"


def run_isolated_longhaul(*, sub_window_tokens: int | None = None,
                          shape_in_sub: bool = False,
                          window_limit: int = WINDOW_LIMIT_TOKENS,
                          tokenizer: FakeTokenizer | None = None) -> dict:
    """长程主窗 + 每源一个隔离子代理：L05 的主角跑法。

    子代理 worker（剧本代演 LLM 提炼——判断交给模型，机制是本课交付物）：
        - 子窗口 enforce：instr+全文超出 sub_window_tokens ⇒ ContextOverflowError
          → SubagentRunner 兜成结构化 failed（主流程不陪葬）
        - shape_in_sub=True 时先过 L04 整形再研读（机制组合：截断保住完赛，
          代价是深埋事实随被截部分丢失——诚实呈现）
        - 结论 schema：标题 + 文中在场的关键事实原句（probe 命中即收录）
    主窗口只涨结论/失败注记——全程无压缩也稳在低位���
    """
    tk = tokenizer or FakeTokenizer()
    sub_limit = sub_window_tokens if sub_window_tokens is not None else 4000
    src = LongHaulSource()
    catalog = src.catalog_text()

    def worker(subject: str, payload: str, ledger) -> tuple[str, tuple[str, ...]]:
        text = payload
        if shape_in_sub:
            budget = max(50, sub_limit - tk.count(_WORKER_INSTR) - 100)
            text = shape_result(text, max_tokens=budget, tokenizer=tk)
        ledger.measure("sub-study", system=_WORKER_INSTR, tool_results=text)
        facts = [f.statement for f in KEY_FACTS
                 if f.doc_id == subject and f.probe in text]
        title = src.doc(subject).title
        parts = [f"[{subject}]《{title}》"]
        parts += [f"事实：{s}" for s in facts]
        if not facts:
            parts.append("要点：无可核查关键事实（背景性内容）")
        if shape_in_sub and "已截断" in text:
            parts.append("（注：原文超子窗预算，已按显式截断研读——深部内容未覆盖）")
        return "；".join(parts), (subject,)

    runner = SubagentRunner(worker, window_tokens=sub_limit, tokenizer=tk)
    main_ledger = WindowLedger(tokenizer=tk, limit=window_limit, enforce=False)

    conclusions: list[str] = []
    failed: list[str] = []
    sub_peak = 0
    tokens_billed = 0

    for doc_id in DOC_IDS:
        full = src.fetch(doc_id)                      # fetch 在主流程记账（一次）
        result = runner.run(doc_id, full)
        sub_peak = max(sub_peak, result.window_peak)
        tokens_billed += result.tokens_billed
        conclusions.append(result.brief())
        if not result.ok:
            failed.append(doc_id)
        rec = main_ledger.measure("main-step", system=SYSTEM_PROMPT,
                                  task_state=catalog + _STUDY_INSTR,
                                  history="\n".join(conclusions))
        tokens_billed += rec.total

    syn_text = (SYSTEM_PROMPT + catalog + "\n".join(conclusions) + _SYNTHESIS_INSTR)
    syn_rec = main_ledger.measure("synthesis", system=SYSTEM_PROMPT,
                                  task_state=catalog + _SYNTHESIS_INSTR,
                                  history="\n".join(conclusions))
    tokens_billed += syn_rec.total
    hits, missing = presence(syn_text)
    # 隔离契约的探针：原文（过程）不得渗入主窗口——取 S01 正文中段一截
    # 纯填充文本（避开标题与事实原句），它若出现在合成窗口=过程泄漏
    leak_probe = src.doc("S01").content[35:70]

    return {
        "mode": f"isolated(sub={sub_limit}{',shaped' if shape_in_sub else ''})",
        "completed_sources": N_SOURCES - len(failed),
        "failed_sources": failed,
        "main_peak_tokens": main_ledger.peak(),
        "sub_peak_tokens": sub_peak,
        "presence": f"{hits}/{len(KEY_FACTS)}",
        "presence_hits": hits,
        "missing_facts": missing,
        "contradiction_discoverable": contradiction_discoverable(syn_text),
        "process_leaked": leak_probe in syn_text,
        "compactions": 0,
        "tokens_billed": tokens_billed,
        "total_fetches": src.total_fetches,
    }


def run_workspace_longhaul(*, workspace_base, run_id: str = "longhaul-demo",
                           crash_at: int | None = None,
                           sub_window_tokens: int = 4000,
                           window_limit: int = WINDOW_LIMIT_TOKENS,
                           tokenizer: FakeTokenizer | None = None) -> dict:
    """长程主窗 + 子代理 + 文件工作区：L06 的主角跑法。

    在 L05 隔离档之上加三件：
        ①原文无损落盘（sources/）——fetch 一次终身可回读，重复 fetch=0
        ②结论落笔记（notes/）——「有笔记=已研完」是断点续跑的进度事实源
        ③后半程 recitation——每步现读 plan.md 进窗口尾部（对抗漂移）
    crash_at=k：第 k 源后模拟进程死亡，随即「新进程」attach 同一工作区续跑
    ——fetch 总数仍为 30（无工作区的重启=前功尽弃，fetch=crash_at+30）。
    """
    from research_assistant.workspace import Workspace

    tk = tokenizer or FakeTokenizer()
    src = LongHaulSource()                     # 跨「进程」共享=fetch 计数器连续
    recitations = 0
    pointer_chars = 0
    full_chars = 0

    def worker(subject, payload, ledger):
        ledger.measure("sub-study", system=_WORKER_INSTR, tool_results=payload)
        facts = [f.statement for f in KEY_FACTS
                 if f.doc_id == subject and f.probe in payload]
        title = src.doc(subject).title
        parts = [f"[{subject}]《{title}》"] + [f"事实：{s}" for s in facts]
        if not facts:
            parts.append("要点：无可核查关键事实（背景性内容）")
        return "；".join(parts), (subject,)

    runner = SubagentRunner(worker, window_tokens=sub_window_tokens, tokenizer=tk)

    def process(ws: Workspace, main_ledger: WindowLedger, stop_after: int | None):
        nonlocal recitations, pointer_chars, full_chars
        billed = 0
        done = set(ws.note_names())            # 进度事实源：有笔记=已研完
        for no, doc_id in enumerate(DOC_IDS, start=1):
            if doc_id in done:
                continue
            if ws.has_source(doc_id):          # 原文已落盘：回读，不重 fetch
                full = ws.read(f"sources/{doc_id}.txt")
            else:
                full = src.fetch(doc_id)
                ws.save_source(doc_id, full)
            pointer_chars += len(ws.pointer(f"sources/{doc_id}.txt"))
            full_chars += len(full)
            result = runner.run(doc_id, full)
            ws.add_note(doc_id, result.brief())
            recite = ws.recitation_block() if no > SESSION_SPLIT else ""
            if recite:
                recitations += 1
            conclusions = [ws.read(f"notes/{n}.md") for n in ws.note_names()]
            rec = main_ledger.measure(
                "main-step", system=SYSTEM_PROMPT,
                task_state=src.catalog_text() + _STUDY_INSTR + recite,
                history="\n".join(conclusions))
            billed += rec.total + result.tokens_billed
            if stop_after is not None and no >= stop_after:
                return billed, True            # 模拟进程死亡
        return billed, False

    ws1 = Workspace(run_id, workspace_base)
    ws1.write_plan(f"目标：{TOPIC}——30 源全研、提取关键事实、指出跨源矛盾。\n"
                   f"改道后以最新计划为准（L07）。")
    main_ledger = WindowLedger(tokenizer=tk, limit=window_limit, enforce=False)
    tokens_billed, crashed = process(ws1, main_ledger, crash_at)
    if crashed:
        ws2 = Workspace.attach(run_id, workspace_base)     # 新进程：挂载工作区
        more, _ = process(ws2, main_ledger, None)
        tokens_billed += more
        ws_final = ws2
    else:
        ws_final = ws1

    conclusions = [ws_final.read(f"notes/{n}.md") for n in ws_final.note_names()]
    syn_text = (SYSTEM_PROMPT + ws_final.recitation_block()
                + "\n".join(conclusions) + _SYNTHESIS_INSTR)
    syn_rec = main_ledger.measure("synthesis", system=SYSTEM_PROMPT,
                                  task_state=_SYNTHESIS_INSTR + ws_final.recitation_block(),
                                  history="\n".join(conclusions))
    tokens_billed += syn_rec.total
    hits, missing = presence(syn_text)
    ws_final.write_draft(f"（合成草稿）关键事实在场 {hits}/{len(KEY_FACTS)}。")

    return {
        "mode": f"workspace(crash_at={crash_at})",
        "completed_sources": len(ws_final.note_names()),
        "crashed_and_resumed": crashed,
        "main_peak_tokens": main_ledger.peak(),
        "presence": f"{hits}/{len(KEY_FACTS)}",
        "presence_hits": hits,
        "contradiction_discoverable": contradiction_discoverable(syn_text),
        "recitations": recitations,
        "total_fetches": src.total_fetches,
        "refetch_waste_without_ws": (crash_at + N_SOURCES) if crash_at else N_SOURCES,
        "pointer_chars": pointer_chars,
        "full_chars": full_chars,
        "tokens_billed": tokens_billed,
        "workspace_tree": ws_final.tree().splitlines()[:8],
    }
