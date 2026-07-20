"""文件即工作记忆：窗口只留指针（Harness 课程 L06）。

虚拟内存观的收口：
    L04 把工具全文引用落盘、L05 把过程关进子窗口——本模块把**工作集**
    正规化成运行工作区：
        workspace/<run_id>/
          plan.md        计划快照（目标与源清单；recitation 的原料）
          sources/       信源原文（无损落盘——压缩/截断丢的都能回来）
          notes/         每源结论笔记（断点续跑的进度事实源）
          draft.md       报告草稿
    窗口=RAM、文件=磁盘：State/窗口里只留**指针**（路径+一行摘要），
    内容按需读回（读回也要过 L04 整形——外置不是免费回读）。

与两个既有存储的边界（1.2 表落地，互补不替代）：
    checkpoint（agent-ops L06）  崩溃恢复的**状态快照**（机器读，恢复用）
    task_ledger                  任务进度**语义**（结构化 TODO 树）
    workspace（本模块）          **认知外置**（自由文本，人机共读写）
    双恢复：checkpoint 恢复图状态，workspace 恢复工作集——各管一段。

重读胜于记住（recitation，Manus 思想）：
    长任务后半程把 plan.md **重新读进**窗口尾部——对抗目标漂移。
    每次都现读文件而不是引用窗口里的旧计划：文件是事实源，窗口是缓存。

人机共域：工作区文件人可以直接看、直接改——文件是最好的人机接口
（与课程十 inbox 的精神一脉：异步协作面）。

运行时集成：长程模式消费（eval 本课接入，v5/L09 接管）；
enable_workspace 默认关，主链路行为零差异。
"""
from __future__ import annotations

from pathlib import Path

from .config import settings
from .logging_config import get_logger

log = get_logger("workspace")

_SOURCES = "sources"
_NOTES = "notes"
_PLAN = "plan.md"
_DRAFT = "draft.md"


class Workspace:
    """一次长程运行的文件工作区（建区/读写/指针/复述/挂载恢复）。"""

    def __init__(self, run_id: str, base_dir: str | Path | None = None):
        self.run_id = run_id
        base = Path(base_dir) if base_dir is not None else Path(settings.workspace_dir)
        self.root = base / run_id
        (self.root / _SOURCES).mkdir(parents=True, exist_ok=True)
        (self.root / _NOTES).mkdir(parents=True, exist_ok=True)

    # ── 挂载（双恢复的工作区半边）─────────────────────────────
    @classmethod
    def attach(cls, run_id: str, base_dir: str | Path | None = None) -> "Workspace":
        """挂载既有工作区：崩溃重启后，工作集从文件回来（checkpoint 管图状态）。"""
        return cls(run_id, base_dir)

    # ── 写（产物落区）─────────────────────────────────────────
    def write_plan(self, text: str) -> str:
        """计划快照（覆盖式演进——最新计划是唯一事实源，历史靠 git/审计）。"""
        (self.root / _PLAN).write_text(text, encoding="utf-8")
        return self.pointer(_PLAN)

    def save_source(self, doc_id: str, text: str) -> str:
        """信源原文无损落盘——被压缩/截断丢掉的，都能从这里回来。"""
        (self.root / _SOURCES / f"{doc_id}.txt").write_text(text, encoding="utf-8")
        return self.pointer(f"{_SOURCES}/{doc_id}.txt")

    def add_note(self, name: str, text: str) -> str:
        (self.root / _NOTES / f"{name}.md").write_text(text, encoding="utf-8")
        return self.pointer(f"{_NOTES}/{name}.md")

    def write_draft(self, text: str) -> str:
        (self.root / _DRAFT).write_text(text, encoding="utf-8")
        return self.pointer(_DRAFT)

    # ── 读（按需换入）─────────────────────────────────────────
    def read(self, rel_path: str) -> str:
        """按需读回（调用方自己过 L04 整形——外置不是免费回读）。"""
        p = self.root / rel_path
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def read_plan(self) -> str:
        return self.read(_PLAN)

    def has_source(self, doc_id: str) -> bool:
        return (self.root / _SOURCES / f"{doc_id}.txt").exists()

    def note_names(self) -> list[str]:
        """已有笔记名（断点续跑的进度事实源：有笔记=该源已研完）。"""
        return sorted(p.stem for p in (self.root / _NOTES).glob("*.md"))

    # ── 指针协议（State/窗口里的形态）─────────────────────────
    def pointer(self, rel_path: str, head_chars: int = 60) -> str:
        """一行指针：路径 + 体积 + 开头——窗口里只住这一行。"""
        p = self.root / rel_path
        if not p.exists():
            return f"📁 [{rel_path}]（不存在）"
        text = p.read_text(encoding="utf-8")
        return f"📁 [{rel_path}]（{len(text):,} 字）开头：{text[:head_chars]}…"

    def tree(self) -> str:
        """目录树（人机共读的入口）。"""
        lines = [f"workspace/{self.run_id}/"]
        for p in sorted(self.root.rglob("*")):
            rel = p.relative_to(self.root)
            depth = len(rel.parts) - 1
            size = f"（{len(p.read_text(encoding='utf-8')):,} 字）" if p.is_file() else "/"
            lines.append(f"{'  ' * (depth + 1)}{rel.parts[-1]}{size}")
        return "\n".join(lines)

    # ── 复述（对抗目标漂移）───────────────────────────────────
    def recitation_block(self) -> str:
        """从 plan.md 现读目标进窗口尾部——重读胜于记住。

        每次都读文件（不是引用窗口里的旧计划）：文件是事实源，窗口是缓存；
        计划被改道（L07）改过之后，复述自动带上最新版。
        """
        plan = self.read_plan()
        if not plan:
            return ""
        return f"🧭 目标复述（现读自 plan.md，对抗漂移）：\n{plan}"
