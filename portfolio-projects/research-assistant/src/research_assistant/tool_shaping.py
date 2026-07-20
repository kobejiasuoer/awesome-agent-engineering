"""工具返回值工程：控源胜于止损（Harness 课程 L04）。

为什么需要它（账本的证据）：
    L00/L01 的账本证明工具结果是窗口最大消耗方（长程形态 95%，RA 集成 75%）。
    L02 的压缩是「已经进来的太多」的止损；本模块是「别让它进来那么多」的
    控源——治理顺序：先控源，再止损。

三板斧：
    截断  truncate    只留预算内的头部 + **显式省略标记**（省略多少字、原文
                      多长、怎么拿全文——翻页 offset / 引用路径）
    分页  paginate    offset/limit 取片段，页边界双标记——把「要不要看更多」
                      变成 agent 的决策，而不是 harness 的猜测
    引用  reference   全文落文件（无损外置），窗口只进路径+头部摘要——
                      L06 工作区的前奏

省略必须显式（本课诚实纪律，与 L02「压缩必须留审计」并列）：
    静默掐尾的截断会让模型把半篇当全篇引用——比溢出更隐蔽的失败
    （L00 的 A3 基线、本课的「谎报案例」都是它的现场）。任何整形产物，
    只要内容少于原文，标记必须在场——测试逐条锁死。

错误也是返回值：
    给 agent 的错误要可行动（「404：源已失效；建议：跳过或换源」），
    不是 40 行堆栈——呼应 agent-ops L03 的结构化降级：错误信息是给
    调用方的接口，不是给人的日志。

运行时集成：researcher 在 enable_tool_shaping 下对检索结果过 shape_result
（纯截断形态，无文件副作用）；引用板斧供显式调用（demo/L06 工作区接管）。
默认关：行为零差异。
"""
from __future__ import annotations

from pathlib import Path

from .config import settings
from .context_ledger import FakeTokenizer, Tokenizer
from .logging_config import get_logger

log = get_logger("tool_shaping")

# 省略标记模板（显式三要素：略了多少、原文多长、怎么拿全文）
_MARKER_TRUNC = "\n…[⚠️ 已截断：省略 {omitted} 字（原文共 {total} 字）；续读 offset={next_offset}{ref}]"
_MARKER_PAGE_HEAD = "[📄 第 {start}–{end} 字 / 共 {total} 字]\n"
_MARKER_PAGE_TAIL = "\n[📄 {more}]"


def _tk(tokenizer: Tokenizer | None) -> Tokenizer:
    return tokenizer or FakeTokenizer()


# ── 板斧一：截断（显式省略）──────────────────────────────────
def shape_result(text: str, *, max_tokens: int | None = None,
                 tokenizer: Tokenizer | None = None,
                 ref_path: str | None = None) -> str:
    """预算内原样放行；超预算截断并加显式省略标记。

    ref_path：全文已外置时（L06 工作区）标记里附引用路径；否则给翻页 offset。
    标记本身占预算——返回值总长（含标记）不超过 max_tokens。
    """
    tk = _tk(tokenizer)
    limit = max_tokens if max_tokens is not None else settings.tool_result_max_tokens
    if tk.count(text) <= limit:
        return text
    budget_chars = limit * 4
    ref = f" / 全文见 {ref_path}" if ref_path else ""
    # 两轮定长：先按占位标记估长度，再用真实数字重排（保证总长不超预算）
    for _ in range(2):
        marker = _MARKER_TRUNC.format(
            omitted=max(0, len(text) - budget_chars), total=len(text),
            next_offset=budget_chars, ref=ref)
        keep = max(0, budget_chars - len(marker))
        marker = _MARKER_TRUNC.format(
            omitted=len(text) - keep, total=len(text), next_offset=keep, ref=ref)
        budget_chars = limit * 4  # 重算基准不漂移
    kept = text[:keep]
    log.debug(f"工具结果截断：{len(text)}→{len(kept)} 字（标记显式）")
    return kept + marker


# ── 板斧二：分页（翻页权交给 agent）─────────────────────────
def paginate(text: str, *, offset: int = 0, page_tokens: int = 400,
             tokenizer: Tokenizer | None = None) -> dict:
    """按 offset/limit 取片段，页边界双标记。

    返回 {content, offset, next_offset(None=最后一页), total_chars, has_more}——
    「要不要看更多」是 agent 的决策：它拿着 next_offset 自己翻。
    """
    page_chars = page_tokens * 4
    total = len(text)
    start = max(0, min(offset, total))
    end = min(start + page_chars, total)
    has_more = end < total
    head = _MARKER_PAGE_HEAD.format(start=start + 1, end=end, total=total)
    tail = _MARKER_PAGE_TAIL.format(
        more=f"未完：续读 offset={end}" if has_more else "已到末尾")
    return {
        "content": head + text[start:end] + tail,
        "offset": start,
        "next_offset": end if has_more else None,
        "total_chars": total,
        "has_more": has_more,
    }


# ── 板斧三：引用（无损外置，窗口只进指针）────────────────────
def reference(text: str, name: str, dump_dir: str | Path, *,
              head_chars: int = 160) -> dict:
    """全文落文件（无损），返回 {path, head, total_chars}。

    窗口里只进「路径 + 头部摘要」；要用时按需读回（读回也该过整形——
    外置不是免费回读）。L06 工作区把落盘位置正规化。
    """
    base = Path(dump_dir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{name}.txt"
    path.write_text(text, encoding="utf-8")
    return {
        "path": str(path),
        "head": text[:head_chars],
        "total_chars": len(text),
        "pointer": f"📎 [{name}] 全文 {len(text)} 字已存 {path.name}；开头：{text[:head_chars]}…",
    }


# ── 错误也是返回值 ───────────────────────────────────────────
def shape_error(kind: str, detail: str, suggestion: str) -> str:
    """可行动的短错误：现象 + 建议动作，没有堆栈。

    错误信息是给调用方（agent）的接口，不是给人的日志——
    40 行 traceback 在窗口里是纯租金，agent 需要的是「下一步怎么办」。
    """
    return f"⛔ {kind}：{detail[:120]}；建议：{suggestion}"
