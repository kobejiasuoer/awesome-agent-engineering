"""L05 · 收件箱与自主级别：不打断的交付面
==================================================

本脚本演示三件事：
    Part 1（收件箱五通道）：L04 的三种决策投递进收件箱 → digest 日结汇总。
    Part 2（隔夜审批）：夜里 23:00 后台运行触发发布审批、人不在场 →
        审批条目落箱、任务挂起在 checkpoint；早上 08:30 人一键批准 →
        复用 submit_approval 恢复执行（本演示 mock 恢复调用，机制真实）。
    Part 3（agency ladder）：同一份报告在 notify / propose / act 三个
        自主级别下的行为分岔——副作用的边界在哪一级被跨过。

跑法（零外部依赖、零联网、零等待）：
    python code.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_PROJ = _REPO / "portfolio-projects" / "research-assistant"
sys.path.insert(0, str(_PROJ / "src"))

import logging  # noqa: E402
logging.disable(logging.WARNING)

from research_assistant import config, inbox, publish  # noqa: E402
from research_assistant.clock import FakeClock  # noqa: E402
from research_assistant.inbox import (  # noqa: E402
    KIND_APPROVAL, accept_proposal, apply_agency, approve_entry,
    build_digest, deliver, file_approval_request, list_entries,
    pending_approvals, unread_count,
)


def _fresh_dbs(tag: str):
    tmp = tempfile.mkdtemp(prefix=f"ambient_l05_{tag}_")
    inbox.set_db_path_for_test(str(Path(tmp) / "inbox.db"))
    publish.set_db_path_for_test(str(Path(tmp) / "publish.db"))


def demo_channels():
    _fresh_dbs("ch")
    print("─" * 72)
    print("Part 1 · 收件箱五通道：L04 决策的投递面 + digest 日结")
    print("─" * 72)
    clock = FakeClock()

    # L04 的三种决策（浓缩自 Day2/Day3/Day4）
    deliver({"decision": "stay_silent", "level": "none", "reason": "无实质内容"},
            "盯梢主题", "确认无变化", clock=clock)
    deliver({"decision": "add_to_digest", "level": "minor", "reason": "例行补丁"},
            "盯梢主题", "🆕 框架Y 0.3.2 补丁", clock=clock)
    deliver({"decision": "notify_now", "level": "major", "reason": "结论反转"},
            "盯梢主题", "✏️ 框架X撤回AGUI支持", clock=clock)
    deliver({"decision": "add_to_digest", "level": "major", "reason": "配额尽的重大项",
             "quota_exhausted": True}, "盯梢主题", "另一条 major", clock=clock)

    print(f"  投递 4 个决策 → 收件箱未读：notify={unread_count('notify')} "
          f"digest={unread_count('digest')}（沉默不产生条目）")
    for e in reversed(list_entries()):
        print(f"    [{e['kind']:<7}] {e['title']}")
    print()
    print("  日结（build_digest 汇总未读摘要条目并标记已读）：")
    for line in build_digest(clock=clock).splitlines():
        print(f"    {line}")
    print(f"  再次日结：{build_digest(clock=clock)}   ← 不重复")
    print()


def demo_overnight_approval():
    _fresh_dbs("appr")
    print("─" * 72)
    print("Part 2 · 隔夜审批：interrupt 状态在 checkpoint 里等人")
    print("─" * 72)

    # mock submit_approval（真实版从 checkpoint 恢复图执行——agent-ops L05 资产）
    import research_assistant.service as service_mod
    async def fake_submit(thread_id, approved, comment=""):
        return {"publish_result": {"status": "published" if approved else "rejected"}}
    service_mod.submit_approval, _orig = fake_submit, service_mod.submit_approval

    print("  23:00  后台班次跑到 publish 节点 → interrupt（enable_hitl）")
    print("         人不在场：daemon 不阻塞等待，落一条审批条目，任务挂起")
    entry = file_approval_request("thread-night-42", "Agent 框架生态动态",
                                  "拟发布：Day4 重大反转的增量报告（摘要 200 字）")
    print(f"         → 收件箱 +approval：{entry['title']}")
    print(f"  （夜里什么都不发生——interrupt 状态持久在 checkpoint，不占进程）")
    print()
    print("  08:30  人打开收件箱：")
    for p in pending_approvals():
        print(f"         {p['title']}（thread={p['thread_id']}）")
    out = asyncio.run(approve_entry(entry["entry_id"], True))
    print(f"         一键批准 → submit_approval 恢复执行 → {out['result']['publish_result']['status']}")
    print(f"         条目落章：{inbox.get_entry(entry['entry_id'])['resolution']}")

    service_mod.submit_approval = _orig
    print()
    print("  🎯 复用不重写：interrupt/resume/跨进程恢复全是 agent-ops L05 资产。")
    print("     本课只加了「人不在场」的收发室——审批从『阻塞对话』变成『收件箱待办』。")
    print()


def demo_agency_ladder():
    print("─" * 72)
    print("Part 3 · agency ladder：同一份报告，三个自主级别的分岔")
    print("─" * 72)
    report = "【研究报告】框架X撤回AGUI支持，建议重评估选型……"

    for mode in ("notify", "propose", "act"):
        _fresh_dbs(mode)
        config.settings.__dict__["agency_level"] = mode
        config.settings.__dict__["publish_dry_run"] = False
        out = apply_agency("盯梢主题", report, f"t-{mode}")
        if mode == "notify":
            print(f"  notify : action={out['action']}（只报告，publish 碰都不碰）")
        elif mode == "propose":
            e = inbox.get_entry(out["entry_id"])
            print(f"  propose: action={out['action']} → 草稿条目落箱（resolved={e['resolved']}）")
            acc = accept_proposal(out["entry_id"])
            print(f"           人 accept → 才真正发布（published={acc['publish']['published']}）")
        else:
            print(f"  act    : action={out['action']}（先斩后奏，published={out['publish']['published']}）")
            replay = apply_agency("盯梢主题", report, f"t-{mode}")
            print(f"           同内容再跑一班 → idempotent_replay={replay['publish']['idempotent_replay']}"
                  f"（幂等键挡重放，agent-ops L04 资产）")
            trace = [e for e in list_entries(kind="notify") if "已代你发布" in e["title"]]
            print(f"           留痕条目 ×{len(trace)}（先斩后奏必须留痕）")
    config.settings.__dict__["agency_level"] = "notify"
    print()
    print("  🎯 阶梯的爬法：新动作先 notify 观察 → 判级/产出稳定后升 propose →")
    print("     只有低风险+幂等+可回滚的动作才配 act。降级永远一行配置。")
    print()


def main():
    print("=" * 72)
    print("  L05 · 收件箱与自主级别：不打断的交付面")
    print("=" * 72)
    print()
    print("L00 基线的第⑤环缺口：交付面是对话窗口——人不在场就没有交付。")
    print("本课给常驻产出一个异步交付面（收件箱五通道），并给「代办动作」")
    print("装上胆量分层（notify/propose/act）。")
    print()
    demo_channels()
    demo_overnight_approval()
    demo_agency_ladder()
    print("=" * 72)
    print("  本课小结")
    print("=" * 72)
    print("  ① 通道语义分明：notify/digest/proposal/approval/alert 各走各的")
    print("  ② 沉默不产生条目：stay_silent 连收件箱都不进（否则又是疲劳）")
    print("  ③ 隔夜审批：interrupt 在 checkpoint 里等人，审批变收件箱待办")
    print("  ④ agency ladder：副作用的边界在 propose→act 之间；act 必须幂等+留痕")


if __name__ == "__main__":
    main()
