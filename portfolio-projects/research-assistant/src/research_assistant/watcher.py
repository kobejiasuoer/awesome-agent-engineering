"""信源与变化检测：世界变了什么（Ambient L02）。

现状缺口：
    会话式每次研究都当世界是全新的——L00 基线 Day2 世界没变仍全量重研。
    常驻 Agent 醒来后第一件事不该是研究，而是问「和上次比，变了什么」。

设计：
    - 信源适配器 = 任何返回条目列表的 callable（条目鸭子类型：
      有 item_id/title/content 属性即可——5 日时间线的 SourceItem 直接可用）
    - 快照表（sqlite）：每个条目存规范化内容哈希 + 首见/末见时间
    - scan_source()：fetch → 与快照 diff → ChangeSet（new/changed/gone）
    - 机械层五毛钱回答「有没有新东西」；「算不算实质变化」是 L04 语义判级的事

两条纪律（本课灵魂）：
    ① 「没有变化」是一等公民结果：ChangeSet 为空 → 本轮到此为止，不进研究图
    ② 「没能看到」≠「没有变化」：fetch 失败返回 ok=False 的 ChangeSet
      （不更新快照、绝不产出空变化集冒充「没变」）——agent-ops L03
      「诚实降级」（不让超时字符串混进材料）在常驻场景的直系延伸

与 ops-L10 语义缓存的亲缘与区别：
    都是「内容指纹去重」；那边对象是**问题**（同义问法命中缓存省一次回答），
    这边对象是**信源内容**（识别「没有新东西」省一轮研究）。
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .clock import Clock
from .logging_config import get_logger

log = get_logger("watcher")

_DB_PATH = "source_snapshots.db"


def _get_db_path() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent.parent / _DB_PATH


def _connect() -> sqlite3.Connection:
    path = _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            source_id       TEXT NOT NULL,
            item_id         TEXT NOT NULL,
            content_hash    TEXT NOT NULL,
            title           TEXT NOT NULL DEFAULT '',
            first_seen_at   REAL NOT NULL,
            last_seen_at    REAL NOT NULL,
            last_changed_at REAL NOT NULL,
            PRIMARY KEY (source_id, item_id)
        )
    """)
    conn.commit()
    return conn


# ── 规范化与指纹 ─────────────────────────────────────────────

def normalize(text: str) -> str:
    """规范化：压掉全部空白。

    L00 基线证明了全文 diff 对「顺序打乱/空白微调」大量误报（文本相似度
    49% vs 内容相似度 94%）。item 级 + 空白规范化后，这两类噪声归零。
    真正的措辞改写仍会被判「变更」——机械层诚实上报，「算不算实质变化」
    留给 L04 语义判级（分层：便宜的先跑，贵的兜底）。
    """
    return "".join(text.split())


def content_hash(item: Any) -> str:
    """条目内容指纹：规范化(title+content) 的 md5 前 16 位。"""
    raw = normalize(getattr(item, "title", "") + getattr(item, "content", ""))
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


# ── 变化集 ───────────────────────────────────────────────────

@dataclass
class ChangeSet:
    """一次扫描的结果。ok=False 表示「没能看到」（与空变化集严格区分）。"""
    source_id: str
    scanned_at: float
    ok: bool = True
    error: str = ""
    first_scan: bool = False                      # 建仓扫描（全部条目按 new 报）
    new_items: list[Any] = field(default_factory=list)
    changed_items: list[Any] = field(default_factory=list)
    gone_item_ids: list[str] = field(default_factory=list)

    def has_changes(self) -> bool:
        return bool(self.new_items or self.changed_items or self.gone_item_ids)

    def is_no_change(self) -> bool:
        """「确认没有变化」：只有 ok 的空变化集才配这么说。"""
        return self.ok and not self.has_changes()

    def summary_line(self) -> str:
        if not self.ok:
            return f"[{self.source_id}] ❌ 没能看到（{self.error}）——不等于没有变化"
        if self.first_scan:
            return f"[{self.source_id}] 📦 建仓：{len(self.new_items)} 条入快照"
        if self.is_no_change():
            return f"[{self.source_id}] ✅ 确认无变化"
        return (f"[{self.source_id}] 🔔 变化：新增{len(self.new_items)} "
                f"变更{len(self.changed_items)} 消失{len(self.gone_item_ids)}")


# ── 扫描核心 ─────────────────────────────────────────────────

def _load_snapshot(conn: sqlite3.Connection, source_id: str) -> dict[str, str]:
    rows = conn.execute(
        "SELECT item_id, content_hash FROM snapshots WHERE source_id = ?",
        (source_id,),
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def scan_source(
    source_id: str,
    fetch: Callable[[], Iterable[Any]],
    clock: Clock | None = None,
) -> ChangeSet:
    """扫描一个信源：fetch → 与快照 diff → 更新快照 → ChangeSet。

    故障语义：fetch 抛任何异常 → ok=False，**快照不动**——
    下次成功扫描仍与「最后一次看清世界的样子」对比，不会把故障期的
    空白误判成「全部消失又全部新增」。

    gone 语义：消失的条目从快照删除（只报一次；再出现算 new）。
    """
    now = (clock or Clock()).now()
    try:
        items = list(fetch())
    except Exception as e:  # 诚实 failed：绝不吞成空变化集
        log.warning(f"信源 {source_id} 扫描失败：{type(e).__name__}: {e}")
        return ChangeSet(source_id=source_id, scanned_at=now,
                         ok=False, error=f"{type(e).__name__}: {e}")

    conn = _connect()
    try:
        prev = _load_snapshot(conn, source_id)
        first_scan = not prev

        new_items, changed_items = [], []
        seen_ids = set()
        for it in items:
            iid = getattr(it, "item_id")
            seen_ids.add(iid)
            h = content_hash(it)
            if iid not in prev:
                new_items.append(it)
                conn.execute(
                    "INSERT OR REPLACE INTO snapshots (source_id, item_id, content_hash, "
                    "title, first_seen_at, last_seen_at, last_changed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (source_id, iid, h, getattr(it, "title", ""), now, now, now),
                )
            elif prev[iid] != h:
                changed_items.append(it)
                conn.execute(
                    "UPDATE snapshots SET content_hash = ?, title = ?, last_seen_at = ?, "
                    "last_changed_at = ? WHERE source_id = ? AND item_id = ?",
                    (h, getattr(it, "title", ""), now, now, source_id, iid),
                )
            else:
                conn.execute(
                    "UPDATE snapshots SET last_seen_at = ? WHERE source_id = ? AND item_id = ?",
                    (now, source_id, iid),
                )

        gone_ids = [iid for iid in prev if iid not in seen_ids]
        for iid in gone_ids:
            conn.execute("DELETE FROM snapshots WHERE source_id = ? AND item_id = ?",
                         (source_id, iid))
        conn.commit()
    finally:
        conn.close()

    cs = ChangeSet(source_id=source_id, scanned_at=now, ok=True,
                   first_scan=first_scan, new_items=new_items,
                   changed_items=changed_items, gone_item_ids=gone_ids)
    log.info(cs.summary_line())
    return cs


def snapshot_count(source_id: str) -> int:
    """快照里现存多少条目（诊断用）。"""
    conn = _connect()
    try:
        row = conn.execute("SELECT COUNT(*) FROM snapshots WHERE source_id = ?",
                           (source_id,)).fetchone()
        return int(row[0])
    finally:
        conn.close()


# ── 内置适配器 ───────────────────────────────────────────────

@dataclass(frozen=True)
class WatchItem:
    """通用条目（适配器产出用；与时间线 SourceItem 字段兼容）。"""
    item_id: str
    title: str
    content: str


def make_dir_fetch(dir_path: str | Path, patterns: tuple[str, ...] = ("*.md", "*.txt")):
    """本地目录适配器：每个文本文件一条目（离线可用，盯本地笔记/导出文件）。"""
    d = Path(dir_path)

    def fetch() -> list[WatchItem]:
        if not d.exists():
            raise FileNotFoundError(f"目录不存在：{d}")
        items = []
        for pat in patterns:
            for p in sorted(d.glob(pat)):
                items.append(WatchItem(
                    item_id=p.name, title=p.stem,
                    content=p.read_text(encoding="utf-8", errors="replace"),
                ))
        return items

    return fetch


def set_db_path_for_test(path: str):
    """测试用：覆盖快照库路径（隔离）。"""
    global _DB_PATH
    _DB_PATH = path
