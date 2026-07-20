"""跨会话记忆文件：Agent 的操作记忆（Harness 课程 L03）。

三种记忆分清（1.2 边界表的落地，谁都不取代谁）：
    任务经验  memory.py（frontier）   研究结论与教训，向量召回，量大
    任务进度  task_ledger.py          TODO 树与增量简报，结构化语义
    操作记忆  本模块                  「用户要求报告 ≤500 字」——既不是研究
                                      结论也不是进度，此前无处安放，每次会话
                                      从零开始。量小、价值密度高、人可直读直改。

形态（活参考：Claude Code 对它的用户就是这套机制）：
    单事实单文件（frontmatter: name/description/type/triggers + 正文）
    + MEMORY.md 索引（每条记忆一行）。
    **索引常驻、正文按需**——一条记忆的常驻成本只有一行描述；trigger 命中
    才读正文注入（渐进披露第一次出现，L08 的 skill 加载与此同构：
    记忆是「学到的」，skill 是「配置的」，机制同一套）。

写入纪律（比怎么记更难的是何时记——判断交给模型、纪律交给代码）：
    「这是不是值得记的操作事实」是模型的判断（真实系统里 LLM 提名候选）；
    gate_memory 是代码的纪律：
        - scope=session（只对本轮有意义的临时参数）→ 拒收
        - 仓库/代码已记录的 → 拒收（不重复存储事实源）
        - 空名/空正文 → 拒收
        - 记错了 → delete_memory（记忆可反悔，删除同步索引）

召回纪律（防记忆污染）：
    记忆是**背景不是指令**——注入块自带「可能过时，与当前对话冲突时以当前
    对话为准」提示；旧记忆过时要验证，不盲从。

运行时集成：writer 在 enable_memory_files 下按需召回（trigger 命中才注入）。
「索引常驻 system」的完整形态属于长程单窗模式（v5/L09）——v4 map-reduce
没有常驻 system 段，诚实起见不做注入戏。默认关：行为零差异。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import settings
from .logging_config import get_logger

log = get_logger("memory_files")

INDEX_NAME = "MEMORY.md"

# 记忆类型（操作记忆的三个来源）
MTYPE_PREFERENCE = "preference"        # 用户偏好（怎么给他干活）
MTYPE_CONSTRAINT = "constraint"        # 长期约束（红线/规则）
MTYPE_PROJECT = "project_state"        # 跨会话项目状态
_VALID_TYPES = (MTYPE_PREFERENCE, MTYPE_CONSTRAINT, MTYPE_PROJECT)


@dataclass(frozen=True)
class MemoryCandidate:
    """一条待写入的记忆候选（真实系统里由 LLM 提名——判断交给模型）。

    scope：durable=跨会话事实 / session=只对本轮有意义（gate 必拒）。
    triggers：逗号分隔的触发词——召回时 query 命中任一触发词才读正文。
    """
    name: str
    description: str
    body: str
    mtype: str = MTYPE_PREFERENCE
    scope: str = "durable"
    triggers: str = ""
    already_recorded: bool = False     # 仓库/代码已记录（提名方如实标注）


def _base_dir(base_dir: str | Path | None = None) -> Path:
    return Path(base_dir) if base_dir is not None else Path(settings.memory_files_dir)


# ── 写入纪律（gate：纪律交给代码）────────────────────────────
def gate_memory(c: MemoryCandidate) -> tuple[bool, str]:
    """写入纪律：什么不值得记，代码说了算。"""
    if not c.name.strip() or not c.body.strip():
        return False, "拒收：空名或空正文"
    if c.scope == "session":
        return False, "拒收：只对本轮有意义的临时参数（session scope）"
    if c.already_recorded:
        return False, "拒收：仓库/代码已记录，不重复存储事实源"
    if c.mtype not in _VALID_TYPES:
        return False, f"拒收：未知类型 {c.mtype}"
    return True, "通过"


# ── 落盘与索引 ───────────────────────────────────────────────
def _memory_path(name: str, base: Path) -> Path:
    return base / f"{name}.md"


def _render_file(c: MemoryCandidate) -> str:
    return (f"---\nname: {c.name}\ndescription: {c.description}\n"
            f"type: {c.mtype}\ntriggers: {c.triggers}\n---\n\n{c.body.strip()}\n")


def _rebuild_index(base: Path) -> None:
    """索引从文件重建（单一事实源是文件；索引只是视图，按名排序确定性）。"""
    entries = []
    for p in sorted(base.glob("*.md")):
        if p.name == INDEX_NAME:
            continue
        meta = _parse_frontmatter(p.read_text(encoding="utf-8"))
        entries.append(f"- [{meta.get('name', p.stem)}] {meta.get('description', '')}")
    text = "# 操作记忆索引（正文按需读取）\n\n" + "\n".join(entries) + "\n"
    (base / INDEX_NAME).write_text(text, encoding="utf-8")


def _parse_frontmatter(text: str) -> dict:
    meta: dict[str, str] = {}
    if text.startswith("---"):
        for line in text.split("---", 2)[1].strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return meta


def write_memory(c: MemoryCandidate,
                 base_dir: str | Path | None = None) -> tuple[Path | None, str]:
    """过 gate 才落盘；同名=更新而非新增（用户改主意是常态）；索引同步重建。"""
    ok, reason = gate_memory(c)
    if not ok:
        log.info(f"记忆候选被拒：{c.name} —— {reason}")
        return None, reason
    base = _base_dir(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    path = _memory_path(c.name, base)
    updated = path.exists()
    path.write_text(_render_file(c), encoding="utf-8")
    _rebuild_index(base)
    log.info(f"记忆{'更新' if updated else '写入'}：{c.name}")
    return path, ("更新" if updated else "写入")


def delete_memory(name: str, base_dir: str | Path | None = None) -> bool:
    """记错了删（记忆可反悔）；索引同步重建。"""
    base = _base_dir(base_dir)
    path = _memory_path(name, base)
    if not path.exists():
        return False
    path.unlink()
    _rebuild_index(base)
    return True


# ── 召回（索引常驻、正文按需）────────────────────────────────
def load_index(base_dir: str | Path | None = None) -> str:
    """索引全文（常驻成本：每条记忆一行）。"""
    p = _base_dir(base_dir) / INDEX_NAME
    return p.read_text(encoding="utf-8") if p.exists() else ""


def list_memories(base_dir: str | Path | None = None) -> list[dict]:
    base = _base_dir(base_dir)
    out = []
    if base.exists():
        for p in sorted(base.glob("*.md")):
            if p.name == INDEX_NAME:
                continue
            out.append(_parse_frontmatter(p.read_text(encoding="utf-8")))
    return out


def read_memory(name: str, base_dir: str | Path | None = None) -> str:
    """按需读正文（frontmatter 之后的部分）。"""
    p = _memory_path(name, _base_dir(base_dir))
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip() if text.startswith("---") else text.strip()


def match_memories(query: str, base_dir: str | Path | None = None) -> list[str]:
    """trigger 命中的记忆名（机械层匹配；「要不要读」的判断也可交模型，L08 同构）。"""
    hits = []
    for meta in list_memories(base_dir):
        triggers = [t.strip() for t in meta.get("triggers", "").split(",") if t.strip()]
        if any(t in query for t in triggers):
            hits.append(meta["name"])
    return hits


def recall_block(query: str, base_dir: str | Path | None = None) -> str:
    """命中记忆的注入块（召回纪律内置：背景不是指令，过时以当前对话为准）。"""
    names = match_memories(query, base_dir)
    if not names:
        return ""
    lines = [f"- [{n}] {read_memory(n, base_dir)}" for n in names]
    return ("📌 跨会话操作记忆（背景参考；可能过时，与当前对话冲突时以当前对话为准）：\n"
            + "\n".join(lines))
