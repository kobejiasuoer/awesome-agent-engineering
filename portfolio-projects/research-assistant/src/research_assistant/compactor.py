"""压缩器：有损，但有纪律（Harness 课程 L02）。

为什么需要它（现状缺口）：
    长程运行的窗口只增不减（L00：裸奔死于 S11；L01：第 5 源就进 caution）。
    压缩是「已经进来的太多」的止损手段——但无纪律的压缩比溢出更危险：
    溢出会报错，无痕压缩不报错，模型引用自己已经丢掉的东西而不自知。

三步纪律：登记 → 摘要 → 验证（「判断交给模型、纪律交给代码」的窗口版）：
    登记  压缩前把 must-survive 事实登记 pinned——机械保留，代码保证：
          pinned 块永远不进摘要器、永远不可压缩。
    摘要  其余内容交给摘要器（生产=LLM，判断交给模型；测试=确定性假摘要器，
          只测机械纪律不测语义保真——诚实边界）。
    验证  压缩后逐条验证登记项仍在窗口文本里（纪律交给代码；构造上已保证，
          验证是「带子加背带」——任何实现回归都会被当场抓住）。

分层可压性（谁先被压）：
    tool_result（工具原文，已被提炼过的可丢）→ note（过程笔记）
    → conclusion / pinned / summary 不可压（结论层是研究的资产，不是缓存）。

压缩必须留审计（本课诚实纪律之一）：
    每次压缩记 CompactionRecord——压掉多少 token、丢了哪些 item（id 可追溯）、
    摘要多长、登记项验证结果。「压缩过」是一等公民信息，无痕压缩=篡史。

递归漂移警告（README 展开）：摘要的摘要会累积失真。审计行里的 dropped_items
保留了被丢内容的 id——配合 L06 工作区（原文落盘）就能做「全量校准」：
定期从原文重建认知，而不是在残片的残片上继续推理。

运行时集成：v4 主链路（map-reduce）各调用无跨调用累积，压缩的主战场是
长程单窗形态——eval 侧 harness_runs.py 先接（本课），v5 长途模式（L09）接管。
模块本身随时可独立调用；enable_compaction 默认关。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .config import settings
from .context_ledger import FakeTokenizer, Tokenizer, zone
from .logging_config import get_logger

log = get_logger("compactor")

# 分层可压性：按顺序先压第一类，不够再压第二类；不在表内的一律不可压
COMPRESS_ORDER = ("tool_result", "note")


@dataclass(frozen=True)
class PinnedFact:
    """一条 must-survive 事实（登记即契约：压缩后必须原文在场）。"""
    fact_id: str
    statement: str


@dataclass(frozen=True)
class WindowItem:
    """可压缩窗口的一个片段。

    kind 决定可压性：tool_result/note 可压（按 COMPRESS_ORDER 先后），
    conclusion/pinned/summary 不可压。
    """
    item_id: str
    kind: str
    text: str


@dataclass(frozen=True)
class CompactionRecord:
    """一次压缩的审计行（压缩必须可追溯——无痕压缩=篡史）。"""
    seq: int
    before_tokens: int
    after_tokens: int
    dropped_items: tuple[str, ...]     # 被压掉的 item_id（可追溯）
    summary_tokens: int
    pinned_count: int
    pinned_verified: bool              # 登记项压缩后逐条在场（代码保证+验证兜底）


def make_llm_summarizer(llm) -> Callable[[list[str]], str]:
    """生产摘要器：把被压内容交给 LLM 提炼（判断交给模型）。

    诚实边界：FakeLLM 下摘要没有语义——mock 测试只锁机械纪律
    （登记存活/审计完整），语义保真在 L09 可选真模型章抽查。
    """
    def summarize(texts: list[str]) -> str:
        joined = "\n\n".join(texts)
        resp = llm.invoke(
            f"你是研究档案员。把以下 {len(texts)} 段材料压缩成一段要点摘要"
            f"（保留具体数字与结论，丢弃套话）：\n\n{joined}"
        )
        return resp.content.strip()
    return summarize


def head_summarizer(texts: list[str]) -> str:
    """确定性假摘要器（测试/演示）：各段只留前 80 字。

    刻意有损——它就是「无登记压缩丢关键事实」对照组的凶器（规则公开）。
    """
    return "（摘要）" + " / ".join(t[:80] for t in texts)


class Compactor:
    """水位触发的登记式压缩器。

    用法（长程循环里）：
        c = Compactor(tokenizer=FakeTokenizer(), limit=8000)
        c.register(PinnedFact("F01", "……"))          # 研究中随时登记
        if c.should_compact(current_total):
            items, rec = c.compact(items, extra_tokens=base)
    """

    def __init__(self, tokenizer: Tokenizer | None = None,
                 limit: int | None = None,
                 threshold_pct: float | None = None,
                 target_pct: float | None = None,
                 summarizer: Callable[[list[str]], str] | None = None):
        self.tokenizer = tokenizer or FakeTokenizer()
        self.limit = limit if limit is not None else settings.window_limit_tokens
        self.threshold_pct = (threshold_pct if threshold_pct is not None
                              else settings.compact_threshold_pct)
        self.target_pct = (target_pct if target_pct is not None
                           else settings.compact_target_pct)
        self.summarizer = summarizer or head_summarizer
        self.pinned: dict[str, PinnedFact] = {}
        self.records: list[CompactionRecord] = []

    # ── 登记（契约的建立）─────────────────────────────────────
    def register(self, fact: PinnedFact) -> None:
        """登记 must-survive 事实（同 id 重复登记=更新，幂等）。"""
        self.pinned[fact.fact_id] = fact

    def pinned_block(self) -> str:
        """pinned 块文本：机械保留的关键事实清单（永不进摘要器）。"""
        if not self.pinned:
            return ""
        lines = [f"  [{f.fact_id}] {f.statement}"
                 for f in sorted(self.pinned.values(), key=lambda x: x.fact_id)]
        return "🔒 已登记关键事实（压缩不可丢）：\n" + "\n".join(lines)

    # ── 触发（水位驱动）───────────────────────────────────────
    def should_compact(self, total_tokens: int) -> bool:
        """进警戒区就压，不等危险区（太早浪费摘要成本，太晚一次大压丢更多）。"""
        return total_tokens >= self.limit * self.threshold_pct

    # ── 压缩（三步纪律的执行）─────────────────────────────────
    def _tokens(self, items: list[WindowItem]) -> int:
        return sum(self.tokenizer.count(i.text) for i in items if i.text)

    def compact(self, items: list[WindowItem],
                extra_tokens: int = 0) -> tuple[list[WindowItem], CompactionRecord]:
        """压缩到目标水位以下：分层可压、oldest-first、登记机械保留、留审计。

        extra_tokens：窗口里不归本压缩器管的部分（system/目录/即将进来的新文档），
        目标是 items_tokens + extra_tokens ≤ limit × target_pct。
        """
        before = self._tokens(items) + extra_tokens
        target = int(self.limit * self.target_pct)

        dropped: list[WindowItem] = []
        kept: list[WindowItem] = list(items)
        # 分层：先压 tool_result（oldest-first），不够再压 note
        for kind in COMPRESS_ORDER:
            if self._tokens(kept) + extra_tokens <= target:
                break
            for it in [x for x in kept if x.kind == kind]:      # 列表序=时间序
                if self._tokens(kept) + extra_tokens <= target:
                    break
                kept.remove(it)
                dropped.append(it)

        # 摘要：被丢内容交给摘要器（pinned 块永不进这里——机械保证的一半）
        summary_text = self.summarizer([d.text for d in dropped]) if dropped else ""
        new_items: list[WindowItem] = []
        pin_text = self.pinned_block()
        if pin_text:
            new_items.append(WindowItem(f"pinned-{len(self.records) + 1}",
                                        "pinned", pin_text))
        if summary_text:
            new_items.append(WindowItem(f"summary-{len(self.records) + 1}",
                                        "summary", summary_text))
        new_items.extend(kept)

        # 验证：登记项逐条在场（构造已保证；验证是回归的哨兵）
        window_text = "".join(i.text for i in new_items)
        verified = all(f.statement in window_text for f in self.pinned.values())
        if not verified:  # 纪律交给代码：万一实现回归，机械补回并告警
            log.warning("压缩验证失败：登记项缺席，机械补回 pinned 块")
            new_items.insert(0, WindowItem("pinned-repair", "pinned", pin_text))
            verified = all(f.statement in "".join(i.text for i in new_items)
                           for f in self.pinned.values())

        rec = CompactionRecord(
            seq=len(self.records) + 1,
            before_tokens=before,
            after_tokens=self._tokens(new_items) + extra_tokens,
            dropped_items=tuple(d.item_id for d in dropped),
            summary_tokens=(self.tokenizer.count(summary_text) if summary_text else 0),
            pinned_count=len(self.pinned),
            pinned_verified=verified,
        )
        self.records.append(rec)
        log.info(f"压缩 #{rec.seq}：{rec.before_tokens}→{rec.after_tokens} token，"
                 f"丢 {len(rec.dropped_items)} 项，登记 {rec.pinned_count} 条"
                 f"{'✓' if verified else '✗'}")
        return new_items, rec

    def audit_report(self) -> str:
        """审计报表：每次压缩一行（「压缩过」是一等公民信息）。"""
        if not self.records:
            return "（无压缩记录）"
        lines = []
        for r in self.records:
            lines.append(
                f"  压缩#{r.seq}  {r.before_tokens:,}→{r.after_tokens:,} token"
                f"（水位 {zone(r.before_tokens, self.limit)}→{zone(r.after_tokens, self.limit)}）"
                f"  丢弃 {len(r.dropped_items)} 项[{','.join(r.dropped_items[:6])}"
                f"{'…' if len(r.dropped_items) > 6 else ''}]"
                f"  摘要 {r.summary_tokens} tok  登记 {r.pinned_count} 条"
                f"{'✅' if r.pinned_verified else '❌'}")
        return "\n".join(lines)
