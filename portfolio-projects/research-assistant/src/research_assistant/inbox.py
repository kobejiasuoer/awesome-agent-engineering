"""收件箱与自主级别：不打断的交付面 + 代办的胆量分层（Ambient L05）。

现状缺口：
    会话式的交付面是「对话窗口」——人在场才成立。常驻 Agent 的产出
    发生在人不在场时：立即通知投到哪？摘要攒在哪？后台跑到一半要审批，
    人睡着了怎么办？本模块给系统一个**异步交付面**：收件箱。

五类条目（通道语义不同，混在一起就是新的通知疲劳）：
    notify    立即通知（L04 判 major 且配额内）
    digest    摘要条目（L04 判 minor / 配额尽的 major——攒着，日结）
    proposal  行动草稿（agency=propose：Agent 拟好，等人确认才执行）
    approval  审批请求（后台 HITL interrupt 时人不在场——隔夜审批）
    alert     健康告警（L07：缺勤/预算/信源故障——系统的事，不是内容的事）

自主级别阶梯（agency ladder，「自主-控制」主线的总旋钮）：
    notify  只报告：产出只进收件箱，不碰任何副作用
    propose 拟稿等确认：Agent 把要做的动作写成草稿（proposal 条目），
            人 accept 才执行——LangChain ambient agents 的 review 姿势
    act     先斩后奏：直接执行（幂等键防重放）+ 留痕条目——最高自主，
            只该给低风险动作

隔夜审批（复用 agent-ops L05 资产，不重写）：
    后台运行触发 publish 的 interrupt → daemon（L06）发现 awaiting_approval
    → file_approval_request 落一条 approval 条目 → 人（第二天）approve_entry
    → 复用 service.submit_approval(thread_id) 从 checkpoint 恢复执行。
    interrupt/resume 机制零新增——本课只是给它一个「人不在场」的收发室。
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

from .clock import Clock
from .config import settings
from .logging_config import get_logger

log = get_logger("inbox")

_DB_PATH = "inbox.db"

KIND_NOTIFY = "notify"
KIND_DIGEST = "digest"
KIND_PROPOSAL = "proposal"
KIND_APPROVAL = "approval"
KIND_ALERT = "alert"
KINDS = (KIND_NOTIFY, KIND_DIGEST, KIND_PROPOSAL, KIND_APPROVAL, KIND_ALERT)


def _get_db_path() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent.parent / _DB_PATH


def _connect() -> sqlite3.Connection:
    path = _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inbox (
            entry_id   TEXT PRIMARY KEY,
            kind       TEXT NOT NULL,
            topic      TEXT NOT NULL DEFAULT '',
            title      TEXT NOT NULL,
            body       TEXT NOT NULL DEFAULT '',
            thread_id  TEXT NOT NULL DEFAULT '',
            level      TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            read       INTEGER NOT NULL DEFAULT 0,
            resolved   INTEGER NOT NULL DEFAULT 0,
            resolution TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inbox_kind ON inbox(kind, read)")
    conn.commit()
    return conn


_COLS = ("entry_id, kind, topic, title, body, thread_id, level, "
         "created_at, read, resolved, resolution")


def _row_to_dict(r) -> dict:
    return {
        "entry_id": r[0], "kind": r[1], "topic": r[2], "title": r[3],
        "body": r[4], "thread_id": r[5], "level": r[6], "created_at": r[7],
        "read": bool(r[8]), "resolved": bool(r[9]), "resolution": r[10],
    }


# ── 基础 CRUD ────────────────────────────────────────────────

def add_entry(kind: str, topic: str, title: str, body: str = "", *,
              thread_id: str = "", level: str = "",
              clock: Clock | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"未知条目类型：{kind}（可选：{KINDS}）")
    now = (clock or Clock()).now()
    eid = f"inbox-{uuid.uuid4().hex[:8]}"
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO inbox (entry_id, kind, topic, title, body, thread_id, "
            "level, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (eid, kind, topic, title, body, thread_id, level, now),
        )
        conn.commit()
    finally:
        conn.close()
    log.info(f"收件箱 +{kind}: {title[:50]}")
    return get_entry(eid)  # type: ignore[return-value]


def get_entry(entry_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(f"SELECT {_COLS} FROM inbox WHERE entry_id = ?",
                           (entry_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_entries(kind: str | None = None, unread_only: bool = False,
                 limit: int = 50) -> list[dict]:
    conn = _connect()
    try:
        sql, args = f"SELECT {_COLS} FROM inbox", []
        conds = []
        if kind:
            conds.append("kind = ?"); args.append(kind)
        if unread_only:
            conds.append("read = 0")
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        return [_row_to_dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def unread_count(kind: str | None = None) -> int:
    conn = _connect()
    try:
        if kind:
            row = conn.execute("SELECT COUNT(*) FROM inbox WHERE read = 0 AND kind = ?",
                               (kind,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM inbox WHERE read = 0").fetchone()
        return int(row[0])
    finally:
        conn.close()


def mark_read(entry_id: str):
    conn = _connect()
    try:
        conn.execute("UPDATE inbox SET read = 1 WHERE entry_id = ?", (entry_id,))
        conn.commit()
    finally:
        conn.close()


def resolve(entry_id: str, resolution: str):
    """处置 proposal/approval 条目（accepted/dismissed/approved/rejected）。"""
    conn = _connect()
    try:
        conn.execute("UPDATE inbox SET resolved = 1, resolution = ?, read = 1 "
                     "WHERE entry_id = ?", (resolution, entry_id))
        conn.commit()
    finally:
        conn.close()


# ── L04 决策的投递面 ─────────────────────────────────────────

def deliver(decision: dict, topic: str, brief: str, *,
            thread_id: str = "", clock: Clock | None = None) -> dict | None:
    """把 L04 decide() 的结果投递进收件箱。

    notify_now → notify 条目；add_to_digest → digest 条目；
    stay_silent → None（沉默 = 不产生任何条目，这是最常见的正确结局）。
    配额尽的 major 降级进 digest 时，标题带 ⚠ 前缀（日报可审计）。
    """
    d = decision.get("decision")
    level = decision.get("level", "")
    if d == "stay_silent" or d is None:
        return None
    title = f"[{topic}] {decision.get('reason', '')[:60]}"
    if d == "notify_now":
        return add_entry(KIND_NOTIFY, topic, title, brief,
                         thread_id=thread_id, level=level, clock=clock)
    if decision.get("quota_exhausted"):
        title = f"⚠ 配额尽降级 {title}"
    return add_entry(KIND_DIGEST, topic, title, brief,
                     thread_id=thread_id, level=level, clock=clock)


def build_digest(*, clock: Clock | None = None, mark: bool = True) -> str:
    """把未读 digest 条目汇总成一封摘要（日结；L07 的日报会引用它）。

    mark=True 时把已汇总条目标记已读（下次日结不重复）。
    """
    entries = list_entries(kind=KIND_DIGEST, unread_only=True, limit=100)
    if not entries:
        return "（今日摘要：无条目）"
    now = (clock or Clock()).now()
    lines = [f"📥 每日摘要（{time.strftime('%Y-%m-%d', time.localtime(now))}，"
             f"{len(entries)} 条）"]
    for e in reversed(entries):     # 时间正序阅读
        lines.append(f"  · [{e['level'] or '-'}] {e['title']}")
    if mark:
        for e in entries:
            mark_read(e["entry_id"])
    return "\n".join(lines)


# ── 隔夜审批（复用 agent-ops L05 HITL 资产）──────────────────

def file_approval_request(thread_id: str, topic: str, summary: str, *,
                          clock: Clock | None = None) -> dict:
    """后台运行触发 interrupt、人不在场 → 落一条审批条目（任务保持挂起）。

    checkpoint 里存着中断状态，审批可以隔夜——这正是 agent-ops L05
    「跨进程恢复」能力在常驻场景的用武之地。
    """
    return add_entry(KIND_APPROVAL, topic,
                     f"待审批：{topic} 的发布请求", summary,
                     thread_id=thread_id, clock=clock)


def pending_approvals() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT {_COLS} FROM inbox WHERE kind = ? AND resolved = 0 "
            "ORDER BY created_at", (KIND_APPROVAL,)).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


async def approve_entry(entry_id: str, approved: bool, comment: str = "") -> dict:
    """人回来了：处置审批条目 → 复用 submit_approval 从 checkpoint 恢复执行。"""
    entry = get_entry(entry_id)
    if entry is None or entry["kind"] != KIND_APPROVAL:
        raise KeyError(f"审批条目不存在：{entry_id}")
    if entry["resolved"]:
        return {"status": "already_resolved", "resolution": entry["resolution"]}
    from .service import submit_approval  # 延迟 import 避免循环
    result = await submit_approval(entry["thread_id"], approved, comment)
    resolve(entry_id, "approved" if approved else "rejected")
    log.info(f"隔夜审批完成：{entry_id} → {'批准' if approved else '否决'}")
    return {"status": "resumed", "approved": approved, "result": result}


# ── 自主级别阶梯（agency ladder）─────────────────────────────

def _pub_status(pub: dict) -> str:
    """publish_report 结果的一词概括（留痕/日志用）。"""
    if pub.get("idempotent_replay"):
        return "duplicate（幂等重放，未重复执行）"
    if pub.get("dry_run"):
        return "dry_run（演习，未真执行）"
    return "published" if pub.get("published") else "unknown"


def apply_agency(topic: str, report: str, thread_id: str, *,
                 clock: Clock | None = None) -> dict:
    """产出之后「要不要代办动作」按自主级别分层（动作 = publish 发布）。

    notify  只报告：不碰副作用（通知/摘要的投递由 deliver 负责）
    propose 拟稿等确认：proposal 条目落箱，人 accept_proposal 才执行
    act     先斩后奏：直接 publish（幂等键防重放）+ notify 留痕
    """
    mode = settings.agency_level
    if mode == "act":
        from .publish import publish_report
        pub = publish_report(thread_id, report)
        add_entry(KIND_NOTIFY, topic, f"已代你发布（act 模式）：{topic}",
                  f"发布结果：{_pub_status(pub)}（幂等键 {pub.get('key', '')[:12]}…）",
                  thread_id=thread_id, clock=clock)
        return {"mode": "act", "action": "published", "publish": pub}
    if mode == "propose":
        entry = add_entry(KIND_PROPOSAL, topic, f"发布草稿待确认：{topic}",
                          report, thread_id=thread_id, clock=clock)
        return {"mode": "propose", "action": "drafted", "entry_id": entry["entry_id"]}
    return {"mode": "notify", "action": "none"}


def accept_proposal(entry_id: str) -> dict:
    """人确认草稿 → 执行发布（幂等）→ 条目落章。"""
    entry = get_entry(entry_id)
    if entry is None or entry["kind"] != KIND_PROPOSAL:
        raise KeyError(f"草稿条目不存在：{entry_id}")
    if entry["resolved"]:
        return {"status": "already_resolved", "resolution": entry["resolution"]}
    from .publish import publish_report
    pub = publish_report(entry["thread_id"], entry["body"])
    resolve(entry_id, "accepted")
    return {"status": "accepted", "publish": pub}


def set_db_path_for_test(path: str):
    """测试用：覆盖收件箱路径（隔离）。"""
    global _DB_PATH
    _DB_PATH = path
