"""子代理：过程隔离，结论回传（Harness 课程 L05）。

为什么需要它（注意力杠杆）：
    长程单窗模式里，每篇全文都要过主窗口（L02 的压缩循环：峰值 5,272——
    压缩管住了「留下的」，管不住「路过的」）。子代理把「过程」关进独立
    子窗口：满额干活，结束只回传**结构化结论**——主窗口只付结论的钱。
    N 个子代理各自满窗 = 总注意力 N×窗口，主窗口只涨 N×结论。

隔离契约（本课的红线，测试锁死）：
    1. **回传结论不回传过程**：SubagentResult 只含结论/引用指针/诊断数字
       （子窗口峰值、计费），原文与中间摘录永不渗入主窗口。
    2. **失败结构化回传**：子代理溢出/异常死自己，外面收到 ok=False +
       可读原因（不是堆栈、不是空结论）——「子代理失败 ≠ 空结论」，
       与课程十「没能看到 ≠ 没有变化」同宗：静默吞掉失败是最危险的谎言。
    3. **子窗口有物理预算**：独立 WindowLedger（enforce=True），
       subagent_window_tokens 就是它的全部空间——份额思维（L01）的落地。

何时不外包（Cognition 的警示）：
    需要全局上下文的判断不能下放——各持一角窄上下文的子代理做全局决策
    是灾难。拆分标准：**过程重、结论轻**的任务才外包（读一篇文档提事实=
    过程 3,400 结论 60，杠杆 57 倍；跨源矛盾裁决=需要两端同窗，留在主窗）。

与 v4 的诚实关系：
    v4 的 researcher（Send 并行 + 只回传 finding）在窗口层面**已经做对了**
    「回传结论不回传过程」——这是 map-reduce 架构的礼物。本课把礼物变成
    显式契约（SubagentRunner），并补齐它缺的三件：子窗口物理预算、
    结构化 failed、账本份额。运行时消费方是长程单窗模式（eval 侧本课接入，
    v5/L09 接管）。默认关：行为零差异。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import settings
from .context_ledger import (
    ContextOverflowError, FakeTokenizer, Tokenizer, WindowLedger,
)
from .logging_config import get_logger

log = get_logger("subagent")

# worker 契约：worker(subject, payload, ledger) -> (conclusion, refs)
#   - 材料只在 worker 内部流动；每次「调用」前必须过 ledger.measure（enforce 边界）
#   - 返回的 conclusion 是回传主窗口的唯一正文（结论 schema，短）
Worker = Callable[[str, str, WindowLedger], tuple[str, tuple[str, ...]]]


@dataclass(frozen=True)
class SubagentResult:
    """子代理的回传物——主窗口能看到的全部。

    ok=True：conclusion/refs 有效；ok=False：error 说明原因（结构化短文本）。
    window_peak/tokens_billed 是诊断数字：过程的「账」回传，过程本身不回传。
    """
    ok: bool
    subject: str
    conclusion: str = ""
    refs: tuple[str, ...] = ()
    error: str = ""
    window_peak: int = 0
    tokens_billed: int = 0

    def brief(self) -> str:
        """进主窗口的一行形态。"""
        if self.ok:
            return self.conclusion
        return f"⛔ [{self.subject}] 子代理失败：{self.error}——不等于该源无内容"


class SubagentRunner:
    """子代理运行器：独立子窗口（enforce）+ 结构化失败 + 结论回传。

    用法：
        runner = SubagentRunner(worker, window_tokens=4000)
        result = runner.run("S17", full_text)
        main_items.append(result.brief())      # 主窗口只进这一行
    """

    def __init__(self, worker: Worker, *, window_tokens: int | None = None,
                 tokenizer: Tokenizer | None = None, name: str = "subagent"):
        self.worker = worker
        self.window_tokens = (window_tokens if window_tokens is not None
                              else settings.subagent_window_tokens)
        self.tokenizer = tokenizer or FakeTokenizer()
        self.name = name

    def run(self, subject: str, payload: str = "") -> SubagentResult:
        """跑一个子任务：无论里面发生什么，外面只见 SubagentResult。"""
        ledger = WindowLedger(tokenizer=self.tokenizer,
                              limit=self.window_tokens, enforce=True)
        try:
            conclusion, refs = self.worker(subject, payload, ledger)
            return SubagentResult(
                ok=True, subject=subject, conclusion=conclusion, refs=tuple(refs),
                window_peak=ledger.peak(),
                tokens_billed=sum(r.total for r in ledger.records),
            )
        except ContextOverflowError as e:
            # 溢出死自己：主流程收结构化 failed，不被污染、不必陪葬
            log.warning(f"{self.name}[{subject}] 子窗口越限：{e}")
            return SubagentResult(
                ok=False, subject=subject,
                error=f"子窗口越限（预算 {self.window_tokens} token）",
                window_peak=ledger.peak(),
                tokens_billed=sum(r.total for r in ledger.records),
            )
        except Exception as e:  # noqa: BLE001 —— 隔离边界：任何异常都不外溢
            log.warning(f"{self.name}[{subject}] 失败：{type(e).__name__}: {e}")
            return SubagentResult(
                ok=False, subject=subject,
                error=f"{type(e).__name__}：{str(e)[:120]}",
                window_peak=ledger.peak(),
                tokens_billed=sum(r.total for r in ledger.records),
            )
