"""运行中改道与权限门：长途驾驶舱（Harness 课程 L07）。

为什么需要它（现状缺口）：
    任务越长，「发射时的指令」越可能过时——人看到中间产物想说
    「重点挪到 X」，v4 只能等它跑完或杀掉重跑（丢掉全部进度）。
    长任务不是发射后不管，驾驶舱要有三个部件：

改道通道（steering 队列，sqlite 风格对齐 inbox/jobs）：
    人随时投递指令；agent 在**安全点**（源与源之间/阶段边界）拉取并
    **协商合并**进计划——不是抢占是合并：指令改的是 plan.md（L06），
    recitation 现读机制让新计划立刻生效于后续每一步。
    留痕铁律：每条指令的提交/合并时刻入库可审计，plan.md 内附改道记录
    ——改道历史与压缩审计（L02）同宗：任何行为变更都显式可追溯。

停的两档：
    cancel（软停）  完成当前源，产出**诚实的半程报告**——半途产物也是
                    产物，显式声明「应用户指令于第 N 源停止，已研 N/30」
    kill（硬停）    进程级，靠 checkpoint+workspace 双恢复（L06，只引用）

权限门（tool gate）：
    危险工具调用过门——写出工作区之外 / 网络写操作 / 花费超阈，一律
    needs_approval（拦下并留痕）。审批流复用 agent-ops L05 interrupt 与
    课程十 inbox（只引用不重写）；本课交付的是**门本身**：把审批点从
    「发布环节」推广到「任意工具调用」，与 agency ladder 衔接（act 档也有门）。

判断与纪律的分工（第四次出现）：
    「指令怎么合并进计划」是模型的判断（生产=LLM 合并；演示=剧本代演）；
    安全点时机、队列留痕、越权必拦是代码的纪律。
默认关：enable_steering / enable_tool_gate 均 off，行为零差异。
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .config import settings
from .logging_config import get_logger

log = get_logger("steering")

_DB_PATH = "steering.db"

KIND_STEER = "steer"
KIND_CANCEL = "cancel"


def set_db_path_for_test(path: str) -> None:
    """测试注入独立 db（对齐 watcher/inbox 的隔离约定）。"""
    global _DB_PATH
    _DB_PATH = path


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS steering_queue ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " kind TEXT NOT NULL,"
        " text TEXT NOT NULL,"
        " submitted_at REAL NOT NULL,"
        " applied_at REAL,"
        " merge_note TEXT)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tool_gate_log ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " tool TEXT NOT NULL,"
        " target TEXT,"
        " verdict TEXT NOT NULL,"
        " reason TEXT,"
        " at REAL NOT NULL)")
    return conn


# ── 改道队列 ─────────────────────────────────────────────────
def submit_instruction(text: str, *, kind: str = KIND_STEER) -> int:
    """人随时投递（不打断进行中的源——安全点才被拉取）。"""
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO steering_queue(kind, text, submitted_at) VALUES(?,?,?)",
            (kind, text, time.time()))
        log.info(f"改道指令入队 #{cur.lastrowid}（{kind}）：{text[:60]}")
        return int(cur.lastrowid)


def pending_instructions() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, kind, text FROM steering_queue "
            "WHERE applied_at IS NULL ORDER BY id").fetchall()
    return [{"id": r[0], "kind": r[1], "text": r[2]} for r in rows]


def mark_applied(instruction_id: int, merge_note: str) -> None:
    """合并留痕：什么时候、以什么方式进了计划（改道审计）。"""
    with _conn() as c:
        c.execute("UPDATE steering_queue SET applied_at=?, merge_note=? WHERE id=?",
                  (time.time(), merge_note, instruction_id))


def history() -> list[dict]:
    """完整改道历史（含未应用的）——审计入口。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT id, kind, text, applied_at, merge_note "
            "FROM steering_queue ORDER BY id").fetchall()
    return [{"id": r[0], "kind": r[1], "text": r[2],
             "applied": r[3] is not None, "merge_note": r[4]} for r in rows]


def default_merge(plan: str, instruction: str, at_note: str) -> str:
    """机械合并：计划尾部追加改道记录（生产用 LLM 合并——判断交给模型）。

    留痕在计划内：recitation（L06）现读 plan.md，新指令即刻生效于后续每步。
    """
    return (f"{plan}\n\n## 改道记录（{at_note}）\n"
            f"- 用户指令：{instruction}\n- 后续步骤以本指令为准。")


def poll_safepoint(plan: str, at_note: str,
                   merge_fn=None) -> tuple[str, list[dict], bool]:
    """安全点拉取：合并 steer 指令、检测 cancel。

    返回 (新计划, 已应用指令, cancel_requested)。协商不是抢占——
    只在调用方到达安全点（源与源之间）时才发生。
    """
    merge = merge_fn or default_merge
    applied: list[dict] = []
    cancel = False
    new_plan = plan
    for ins in pending_instructions():
        if ins["kind"] == KIND_CANCEL:
            cancel = True
            mark_applied(ins["id"], f"软停请求于{at_note}受理")
            applied.append(ins)
            continue
        new_plan = merge(new_plan, ins["text"], at_note)
        mark_applied(ins["id"], f"于{at_note}合并进计划")
        applied.append(ins)
    if applied:
        log.info(f"安全点（{at_note}）应用 {len(applied)} 条指令"
                 f"{'，含软停' if cancel else ''}")
    return new_plan, applied, cancel


# ── 权限门 ───────────────────────────────────────────────────
@dataclass(frozen=True)
class ToolAction:
    """待过门的工具调用（机械可判的三要素）。"""
    tool: str            # 工具名
    target: str = ""     # 目标（路径/URL）
    cost_tokens: int = 0  # 预估花费
    method: str = ""     # 网络方法（GET/POST/…）


_WRITE_METHODS = ("POST", "PUT", "DELETE", "PATCH")


def gate_tool(action: ToolAction, *, workspace_root: str | Path | None = None) -> tuple[str, str]:
    """危险动作过门：返回 (verdict, reason)。

    verdict：allow / needs_approval。三条机械规则（越权 100% 拦截，测试锁死）：
        1. 写文件出工作区 → needs_approval（工作区是自留地，外面是别人家）
        2. 网络写操作（POST/PUT/DELETE/PATCH）→ needs_approval（副作用出网）
        3. 花费超阈（tool_gate_cost_threshold）→ needs_approval（钱包保险丝）
    审批流本身复用 agent-ops L05 interrupt + 课程十 inbox（只引用）。
    每次判定入库留痕——「拦过什么」与「放过什么」同样可审计。
    """
    verdict, reason = "allow", "常规调用"
    if action.tool in ("write_file", "delete_file"):
        root = Path(workspace_root) if workspace_root else Path(settings.workspace_dir)
        try:
            Path(action.target).resolve().relative_to(root.resolve())
        except ValueError:
            verdict, reason = "needs_approval", f"写出工作区之外（{action.target}）"
    if action.method.upper() in _WRITE_METHODS:
        verdict, reason = "needs_approval", f"网络写操作（{action.method} {action.target}）"
    if action.cost_tokens > settings.tool_gate_cost_threshold:
        verdict, reason = ("needs_approval",
                           f"花费超阈（{action.cost_tokens}>{settings.tool_gate_cost_threshold}）")
    with _conn() as c:
        c.execute("INSERT INTO tool_gate_log(tool, target, verdict, reason, at) "
                  "VALUES(?,?,?,?,?)",
                  (action.tool, action.target, verdict, reason, time.time()))
    if verdict != "allow":
        log.warning(f"权限门拦截：{action.tool}({action.target}) —— {reason}")
    return verdict, reason


def gate_log() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT tool, target, verdict, reason "
                         "FROM tool_gate_log ORDER BY id").fetchall()
    return [{"tool": r[0], "target": r[1], "verdict": r[2], "reason": r[3]}
            for r in rows]
