"""增量研究回路：只研究变化，不重研全量（Ambient L03）。

现状缺口：
    会话式每次提问都全量重研（L00 基线 Day3：只多一条小更新，却重研全部
    子题，新增内容埋在全量报告里要人肉 diff）。本模块把 watcher 的变化集
    接进研究图：变化条目 → 焦点子题 → 只研究这些。

三分支入口 run_incremental（对应 ChangeSet 的三种形态）：
    ok=False        → 诚实降级：不进图、不产结论，简报明说「没能看到」
    is_no_change()  → 一等公民：不进图、不花钱，简报一句「确认无变化」
    有变化          → 焦点子题进图（split 跳过 LLM 拆题）+ 旧结论注入
                      + ledger 记进度 + 增量简报（🆕新增/✏️修正/➡️不变）

与 frontier-L10 TaskLedger 的协作闭环（账本首次接入运行时主链路）：
    watcher 管「世界增量」（信源变了什么），ledger 管「工作增量」（我研究
    到哪了）。本模块是两者的接线员：世界增量 → 只研究新的 → 记入账本 →
    下次它们就是「已确认历史结论」，注入 prompt「只补新的」。

漂移风险的诚实标注（README「流派对比」详述）：
    增量研究久了会漂——每次只看变化，全局图景可能与世界脱节。
    工程答案是「定期全量校准」（如每 30 天强制一次全量重研），
    本课不实现校准调度（L07 练习），但简报里保留 first_scan 全量语义。
"""
from __future__ import annotations

import uuid
from typing import Any

from .config import settings
from .logging_config import get_logger
from .task_ledger import get_ledger

log = get_logger("incremental")


def build_incremental_focus(change_set: Any) -> list[str]:
    """把 ChangeSet 变成焦点子题列表（研究图 split 的直接输入）。

    新增条目 → 「这条新信息是什么、有何影响」
    变更条目 → 显式要求与旧结论对照、指出矛盾（喂 ✏️ 修正通道）
    gone 条目不生成子题（消失本身通常不值得研究，进简报提示即可）。
    """
    focus: list[str] = []
    for it in getattr(change_set, "new_items", []):
        title = getattr(it, "title", "")
        content = getattr(it, "content", "")
        focus.append(f"【新增】{title}：{content[:160]}——这条新信息的内容、背景与影响")
    for it in getattr(change_set, "changed_items", []):
        title = getattr(it, "title", "")
        content = getattr(it, "content", "")
        focus.append(
            f"【内容变更】{title}：最新内容为「{content[:160]}」"
            f"——与此前已知结论有何出入？若矛盾，用「更正：」开头明确指出"
        )
    return focus


def prior_conclusions(topic: str) -> str:
    """从 TaskLedger 取已确认结论（researcher prompt 的「已知这些」）。

    enable_ledger 关闭时返回空串（降级：没有历史可注入，仍能增量研究）。
    """
    ledger = get_ledger()
    if ledger is None:
        return ""
    done = [t for t in ledger.get_tasks(topic) if t.status == "done" and t.result]
    if not done:
        return ""
    return "\n".join(f"- {t.title}：{t.result[:100]}" for t in done[-8:])


def record_and_brief(topic: str, change_set: Any, findings: list[str]) -> str:
    """ledger 记进度 + 产增量简报。

    顺序关键：先对照「昨天为止的历史」生成简报（🆕/✏️/➡️），
    再把今天的发现记入账本——今天的结论明天才是「历史」。
    enable_ledger 关闭时降级为无历史对照的简单简报（不丢产出）。
    """
    ledger = get_ledger()
    if ledger is None:
        lines = [f"# 增量简报：{topic}（无账本模式，无历史对照）"]
        lines += [f"- 🆕 {f[:100]}" for f in findings]
        return "\n".join(lines)

    brief = ledger.generate_incremental_brief(topic, findings)

    changed = list(getattr(change_set, "new_items", [])) + \
        list(getattr(change_set, "changed_items", []))
    # 焦点子题与 findings 一一对应（split 直用焦点 → 每个焦点一个 finding）；
    # 数量不齐时 zip 截断（诚实：少记不错记）
    for it, f in zip(changed, findings):
        t = ledger.add_task(topic, getattr(it, "title", str(it))[:80])
        ledger.update_status(t.id, "done", result=(f or "")[:200])
    return brief


async def run_incremental(topic: str, change_set: Any,
                          thread_id: str | None = None) -> dict:
    """增量研究入口：watcher ChangeSet → 三分支。

    Returns:
        {"status": "source_failed" | "no_change" | "researched",
         "brief": 增量简报文本, "thread_id": ...,
         "focus": 焦点子题（researched 时）, "result": 图最终 state（researched 时）}
    """
    thread_id = thread_id or f"ambient-{uuid.uuid4().hex[:8]}"

    # 分支①：没能看到 ≠ 没有变化（L02 纪律的消费端——绝不冒充结论）
    if not getattr(change_set, "ok", True):
        err = getattr(change_set, "error", "unknown")
        log.warning(f"信源故障，本轮不产结论：{err}")
        return {
            "status": "source_failed", "thread_id": thread_id,
            "brief": f"⚠️ 没能看到信源（{err}）——不等于没有变化，今日无结论",
        }

    # 分支②：确认无变化 = 一等公民结果（不进图、不花钱、不打扰）
    if change_set.is_no_change():
        log.info("确认无变化，本轮到此为止（零研究成本）")
        return {
            "status": "no_change", "thread_id": thread_id,
            "brief": "✅ 确认无变化：今日无需研究",
        }

    # 分支③：有变化 → 焦点子题进图（增量研究）
    focus = build_incremental_focus(change_set)
    prior = prior_conclusions(topic)
    from .service import invoke  # 延迟 import 避免循环
    result = await invoke(topic, thread_id, extra_state={
        "incremental_focus": focus,
        "prior_context": prior,
    })
    findings = result.get("findings", [])
    brief = record_and_brief(topic, change_set, findings)
    if getattr(change_set, "first_scan", False):
        log.info(f"建仓研究完成：{len(findings)} 条基线结论入账")
    else:
        log.info(f"增量研究完成：焦点 {len(focus)} 条 → {len(findings)} 条新发现")
    return {
        "status": "researched", "thread_id": thread_id,
        "brief": brief, "focus": focus, "result": result,
    }
