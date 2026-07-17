"""打扰决策：值得说吗、现在说吗（Ambient L04）。

现状缺口：
    会话式没有「开口」问题——人问了才答。常驻式每班都可能有产出，
    L00 基线 5 天推送 5 次全量报告（包括毫无新意的 Day2）——通知疲劳
    的结局是用户把通知关掉，系统白跑。**何时开口是常驻 Agent 的价值观核心。**

两层设计：
    ① 判级 classify_change：这次增量是 major / minor / none？
       - LLM judge（有内容理解力）+ 解析失败降级 minor（宁攒勿丢）
       - 无 LLM 时规则降级（关键词启发式，诚实标注 degraded）
    ② 决策 decide：判级 + 政策 + 打扰配额 → notify_now / add_to_digest / stay_silent
       - 配额（每日 N 次立即打扰）是「自主-控制」的阀门：
         配额尽了 major 也降 digest（记 quota_exhausted，日报可见）

与 agent-ops L07 告警的边界：
    那边是**系统健康**告警（步数超阈/预算烧穿——「我跑得不健康」）；
    本课是**内容价值**判断（世界的变化值不值得你抬头——「值得你看一眼」）。
    两者都进 L05 收件箱，但通道语义不同。

宁攒勿丢原则：
    判级失败/解析失败一律降级 minor（进 digest），绝不 stay_silent——
    宁可摘要里多一条平庸条目，不可静默丢一条可能重要的变化。
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .clock import Clock
from .config import settings
from .logging_config import get_logger

log = get_logger("proactivity")

_DB_PATH = "proactivity.db"

LEVELS = ("major", "minor", "none")
NOTIFY_NOW = "notify_now"
ADD_TO_DIGEST = "add_to_digest"
STAY_SILENT = "stay_silent"

# 规则降级的关键词（无 LLM / LLM 失败时的最后防线；诚实标注 degraded）
_MAJOR_KEYWORDS = ("更正", "撤回", "反转", "重磅", "矛盾", "✏️", "已不成立", "推翻")
_MINOR_KEYWORDS = ("🆕", "新增", "发布", "更新", "补丁")


def _get_db_path() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent.parent / _DB_PATH


def _connect() -> sqlite3.Connection:
    path = _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS interrupt_quota (
            day  TEXT PRIMARY KEY,
            used INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def day_key(now_ts: float) -> str:
    """配额的「一天」（本地日期）。"""
    return time.strftime("%Y-%m-%d", time.localtime(now_ts))


# ── 第①层：判级 ─────────────────────────────────────────────

@dataclass
class Judgement:
    """一次判级结果。degraded=True 表示走了降级路径（LLM 缺席/解析失败）。"""
    level: str
    reason: str
    degraded: bool = False


def _rule_classify(text: str) -> Judgement:
    """规则降级判级：关键词启发式（便宜、确定，但没有内容理解力）。"""
    if any(kw in text for kw in _MAJOR_KEYWORDS):
        return Judgement("major", "规则命中重大信号词（降级判级）", degraded=True)
    if any(kw in text for kw in _MINOR_KEYWORDS):
        return Judgement("minor", "规则命中一般更新词（降级判级）", degraded=True)
    return Judgement("none", "规则未命中任何信号词（降级判级）", degraded=True)


def classify_change(brief: str, llm: Any = None) -> Judgement:
    """判级：这次增量值不值得打扰人。

    llm 走「通知管家」prompt，输出两行（级别 + 理由）；
    解析失败降级 minor（宁攒勿丢：不误扰、也绝不静默丢）。
    llm=None 走规则降级（关键词）。
    """
    if not brief or not brief.strip():
        return Judgement("none", "空简报")
    if llm is None:
        return _rule_classify(brief)

    prompt = (
        "你是通知管家，替用户守着注意力。以下是研究助手的增量简报。\n"
        "判断打扰级别：\n"
        "  major = 重大进展/结论反转/直接影响决策，值得立即打扰\n"
        "  minor = 有信息量但不紧急，攒进每日摘要即可\n"
        "  none  = 无实质内容，不值得占用注意力\n"
        "第一行只输出级别单词（major/minor/none），第二行用一句话给理由。\n\n"
        f"{brief[:2000]}"
    )
    try:
        resp = llm.invoke(prompt)
        lines = [ln.strip() for ln in resp.content.strip().splitlines() if ln.strip()]
        level = lines[0].lower() if lines else ""
        reason = lines[1] if len(lines) > 1 else ""
        if level in LEVELS:
            return Judgement(level, reason or "（LLM 未给理由）")
        # 解析失败 → 宁攒勿丢
        log.warning(f"判级解析失败（got={level!r}），降级 minor")
        return Judgement("minor", f"判级解析失败（原始输出：{level[:40]}），宁攒勿丢", degraded=True)
    except Exception as e:
        log.warning(f"判级 LLM 调用失败，降级规则判级：{e}")
        j = _rule_classify(brief)
        return Judgement(j.level, f"LLM 失败降级规则：{j.reason}", degraded=True)


# ── 第②层：决策（政策 + 配额）───────────────────────────────

def quota_used(day: str) -> int:
    conn = _connect()
    try:
        row = conn.execute("SELECT used FROM interrupt_quota WHERE day = ?", (day,)).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def _consume_quota(day: str) -> int:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO interrupt_quota (day, used) VALUES (?, 1) "
            "ON CONFLICT(day) DO UPDATE SET used = used + 1", (day,))
        conn.commit()
        return quota_used(day)
    finally:
        conn.close()


def decide(judgement: Judgement, *, clock: Clock | None = None,
           policy: str | None = None, quota_limit: int | None = None) -> dict:
    """判级 → 打扰决策。

    政策（proactivity_policy）：
        threshold（默认）：major→立即通知（配额内）；minor→摘要；none→沉默
        all：非 none 全部立即通知（= 现状全推，基线对照，不查配额——
             专门用来演示通知疲劳）
        digest_only：非 none 全部进摘要（绝不打扰，适合「只想看日报」的用户）

    配额纪律：notify_now 消耗当日配额；配额尽了 major 也降 digest，
    并带 quota_exhausted=True（进日报——「今天漏打扰了几条 major」可审计）。
    """
    now = (clock or Clock()).now()
    day = day_key(now)
    policy = policy or settings.proactivity_policy
    limit = quota_limit if quota_limit is not None else settings.daily_interrupt_quota

    base = {"level": judgement.level, "reason": judgement.reason,
            "degraded": judgement.degraded, "policy": policy,
            "quota_limit": limit, "quota_exhausted": False}

    if judgement.level == "none":
        return {**base, "decision": STAY_SILENT, "quota_used": quota_used(day)}

    if policy == "all":
        return {**base, "decision": NOTIFY_NOW, "quota_used": quota_used(day)}

    if policy == "digest_only" or judgement.level == "minor":
        return {**base, "decision": ADD_TO_DIGEST, "quota_used": quota_used(day)}

    # threshold + major：配额内立即通知，配额尽降 digest（诚实记档）
    used = quota_used(day)
    if used >= limit:
        log.warning(f"打扰配额已尽（{used}/{limit}），major 降级进摘要")
        return {**base, "decision": ADD_TO_DIGEST,
                "quota_used": used, "quota_exhausted": True}
    used = _consume_quota(day)
    return {**base, "decision": NOTIFY_NOW, "quota_used": used}


def set_db_path_for_test(path: str):
    """测试用：覆盖配额库路径（隔离）。"""
    global _DB_PATH
    _DB_PATH = path
