"""上下文账本：给每次 LLM 调用记「窗口账」（Harness 课程 L01）。

为什么需要它（现状缺口）：
    cost_budget（agent-ops L02）管的是**钱**——一次运行烧多少 token 计费；
    没人管**空间**——单次调用的 prompt 在窗口里装了什么、离物理上限多远。
    钱和空间是两种预算：花得起钱也可能装不下（L00 基线：30 源全文 2.3 万
    token，8k 窗口第 11 源溢出）。窗口管理第一步是记账不是压缩——
    不知道钱花哪了，就谈不上省。

四桶口径（全课程统一，README 讲清边界）：
    system        常驻身份/规程/红线（每次调用全额付租）
    task_state    本轮指令与任务态（目录、计划、当前指令、加载的 skill）
    tool_results  工具带回的外部材料（搜索返回、信源全文、命令输出）
    history       过往轮次的产出（findings/summary/report 等 LLM 生成物、旧笔记）
    注：v4 是单串 prompt 调用（无独立 system 消息），RA 集成里 system 桶
    常为 0——长程单窗形态（L00 裸基线）里它才是常驻大头。

可注入 tokenizer（本课程的命根子，与课程十的可注入时钟同一地位）：
    真 tokenizer 慢、模型绑定、CI 不友好；「窗口够不够」的判断必须走可注入
    的计数器，测试才可复现。FakeTokenizer 用 len//4（与 cost_budget 的字符
    估算同口径）；真实校准路径是 API usage 回执（cost_budget.extract_usage
    已有），两者对账在 L09 可选真模型章。

水位三区（「最后 20% 不干大事」的量化依据）：
    safe    < 60%     放心干活
    caution 60%–85%   该压缩/外置了（L02 的触发区）
    danger  > 85%     只做收尾，不开新工作
    over    > 100%    越限（真实 API 会 400；enforce 模式模拟这一物理约束）

纯测量不拦截：主链路集成只记账（enable_context_ledger 默认关，零行为差异）；
enforce=True 仅供 eval/裸基线模拟物理约束用。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import settings
from .logging_config import get_logger

log = get_logger("context_ledger")

# 水位阈值（占 window_limit 的比例）
SAFE_MAX = 0.60
CAUTION_MAX = 0.85

# 四桶口径（顺序即报表顺序）
PARTS = ("system", "task_state", "tool_results", "history")


class Tokenizer(Protocol):
    """可注入计数器协议：count(text) -> token 数。"""

    def count(self, text: str) -> int: ...


class FakeTokenizer:
    """假 tokenizer：token ≈ len(text)//4，确定性、零依赖。

    诚实标注：字符近似对中文偏保守（绝对数字非真实 tokenizer），
    与 cost_budget 的估算口径一致——结构性结论（占比/水位/越限点）不受影响。
    """

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)


class ContextOverflowError(RuntimeError):
    """窗口越限（enforce 模式）——模拟真实 API 的 400 拒绝。

    关键设计：这是**异常**而不是静默截断——「装不下」必须显式失败，
    不能悄悄丢内容冒充装下了（L00 的 A3 基线正是反面教材）。
    """


def zone(total: int, limit: int) -> str:
    """水位分区：safe / caution / danger / over。"""
    if limit <= 0:
        return "safe"
    ratio = total / limit
    if ratio > 1.0:
        return "over"
    if ratio >= CAUTION_MAX:
        return "danger"
    if ratio >= SAFE_MAX:
        return "caution"
    return "safe"


@dataclass(frozen=True)
class CallRecord:
    """一次 LLM 调用的窗口账目（不可变：账本只追加不篡改）。"""
    call_no: int
    node: str
    parts: dict[str, int]      # 四桶各自的 token
    total: int
    limit: int
    zone: str

    @property
    def over_limit(self) -> bool:
        return self.total > self.limit


class WindowLedger:
    """窗口账本：逐调用记账 + 水位 + 汇总报表。

    enforce=False（默认）：纯测量——记录越限但不打断（主链路集成形态）。
    enforce=True：越限 raise ContextOverflowError（eval 模拟物理约束）。
    记录先于死亡：enforce 抛错前先落账——尸检要有数据。
    """

    def __init__(self, tokenizer: Tokenizer | None = None,
                 limit: int | None = None, enforce: bool = False):
        self.tokenizer = tokenizer or FakeTokenizer()
        self.limit = limit if limit is not None else settings.window_limit_tokens
        self.enforce = enforce
        self.records: list[CallRecord] = []

    def measure(self, node: str, *, system: str = "", task_state: str = "",
                tool_results: str = "", history: str = "") -> CallRecord:
        """调用前记一笔：四桶拆解 + 水位判断（enforce 时越限抛错）。"""
        texts = {"system": system, "task_state": task_state,
                 "tool_results": tool_results, "history": history}
        parts = {k: (self.tokenizer.count(v) if v else 0) for k, v in texts.items()}
        total = sum(parts.values())
        rec = CallRecord(len(self.records) + 1, node, parts, total,
                         self.limit, zone(total, self.limit))
        self.records.append(rec)
        if rec.over_limit:
            log.warning(f"窗口越限：{node} {total}/{self.limit} token")
            if self.enforce:
                raise ContextOverflowError(
                    f"窗口越限（{node}：{total}/{self.limit} token）")
        return rec

    def peak(self) -> int:
        return max((r.total for r in self.records), default=0)

    def summary(self) -> dict:
        """账本汇总：峰值/水位分布/四桶占比（治理顺序的依据）。"""
        by_part = {p: sum(r.parts[p] for r in self.records) for p in PARTS}
        grand = sum(by_part.values())
        zones: dict[str, int] = {}
        for r in self.records:
            zones[r.zone] = zones.get(r.zone, 0) + 1
        return {
            "calls": len(self.records),
            "peak": self.peak(),
            "peak_zone": zone(self.peak(), self.limit),
            "limit": self.limit,
            "by_part": by_part,
            "share": {p: (round(v / grand, 3) if grand else 0.0)
                      for p, v in by_part.items()},
            "zone_counts": zones,
            "over_calls": sum(1 for r in self.records if r.over_limit),
        }

    def report(self) -> str:
        """一段人类可读的账本报表（对齐 cost_budget.report 风格）。"""
        s = self.summary()
        if not s["calls"]:
            return "（无窗口记录）"
        lines = [f"窗口账本：{s['calls']} 次调用，峰值 {s['peak']}/{s['limit']}"
                 f"（{s['peak_zone']}），越限 {s['over_calls']} 次"]
        for p in PARTS:
            lines.append(f"  {p:<13} {s['by_part'][p]:>8} token  {s['share'][p]:>6.1%}")
        return "\n".join(lines)


# ── 模块级单例（对齐 cost_budget 的 tracker 模式）────────────────
# 一次运行共享一个账本；测试用 reset_ledger(tokenizer=..., limit=...) 注入。
_current_ledger: WindowLedger | None = None


def reset_ledger(tokenizer: Tokenizer | None = None,
                 limit: int | None = None, enforce: bool = False) -> WindowLedger:
    """开始一次新运行时重置账本（可注入 tokenizer/limit——测试的入口）。"""
    global _current_ledger
    _current_ledger = WindowLedger(tokenizer=tokenizer, limit=limit, enforce=enforce)
    return _current_ledger


def get_ledger() -> WindowLedger | None:
    return _current_ledger


def measure_call(node: str, *, system: str = "", task_state: str = "",
                 tool_results: str = "", history: str = "") -> CallRecord | None:
    """主链路的记账入口：开关关时零介入（返回 None，不创建任何对象）。

    纯测量不拦截——主链路永远不因记账而改变行为（enforce 只属于 eval）。
    """
    if not settings.enable_context_ledger:
        return None
    global _current_ledger
    if _current_ledger is None:
        _current_ledger = WindowLedger()
    return _current_ledger.measure(node, system=system, task_state=task_state,
                                   tool_results=tool_results, history=history)
