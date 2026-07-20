"""L07 · 运行中改道与权限门：长途驾驶舱
==================================================

本脚本做四件事：
    1. 改道通道微演示：投递 → 安全点协商合并 → plan.md 留痕 →
       recitation 即刻生效（L06 联动）。
    2. 长途改道线：第 10 源后投「优先 safety、跳过 marketing」——
       源序可见改变（safety 提前）、4 个营销源三态标注为「跳过≠失败」，
       在场率不受损（营销源零事实的语料设计在此兑现）。
    3. 软停线：cancel 指令于安全点受理——完成当前源即止，
       产出诚实半程声明（半途产物也是产物）。
    4. 权限门：写出工作区/网络写操作/花费超阈——三类危险动作 100% 拦下
       并留痕；放行同样留痕（拦过什么与放过什么都可审计）。

诚实标注：
    - 「指令→计划变更→源序调整」的合并为剧本代演（真实系统由 LLM 合并
      ——判断交给模型）；队列/安全点/留痕/三态/权限门是本课交付的纪律。

跑法（零外部依赖、零联网、零真实等待）：
    python code.py
"""
from __future__ import annotations

import logging
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
sys.path.insert(0, str(_PROJ))
sys.path.insert(0, str(_PROJ / "src"))

logging.disable(logging.WARNING)

from eval_agent.harness_runs import run_steered_longhaul  # noqa: E402
from research_assistant import steering  # noqa: E402
from research_assistant.steering import ToolAction, gate_tool  # noqa: E402


def hr(title: str) -> None:
    print(f"\n{'═' * 62}\n{title}\n{'═' * 62}")


def part1_channel(tmp: Path) -> None:
    hr("Part 1 · 改道通道：协商合并，不是抢占")
    steering.set_db_path_for_test(str(tmp / "demo.db"))
    plan = "目标：全量研究 30 源。"
    steering.submit_instruction("优先研究 safety 类信源")
    print("指令已入队（agent 正在研第 7 源——不打断）")
    print("……第 7 源完成，到达安全点：")
    new_plan, applied, cancel = steering.poll_safepoint(plan, "第 7 源完成后")
    print(f"  应用 {len(applied)} 条指令，计划变为：")
    for line in new_plan.splitlines():
        print(f"    {line}")
    print("→ 留痕两处：①队列表 applied_at + merge_note（审计）；")
    print("  ②计划内改道记录——L06 的 recitation 现读 plan.md，新计划即刻生效。")


def part2_reroute(tmp: Path) -> None:
    hr("Part 2 · 长途改道线：源序可见改变")
    steering.set_db_path_for_test(str(tmp / "s1.db"))
    r = run_steered_longhaul(workspace_base=tmp / "s1", run_id="s1", steer_after=10)
    print(f"第 10 源完成后投递：「优先 safety、跳过 marketing」")
    print(f"  安全点受理于：第 {r['steer_applied_at']} 源完成后（当前源不被打断）")
    print(f"  改道后源序（前 6）：{' → '.join(r['order_after_steer'])}（safety 提前）")
    print(f"  跳过：{r['skipped_by_instruction']}——三态标注「跳过≠失败」")
    print(f"  完成 {r['completed_sources']}/30，在场率 {r['presence']}（营销源零事实：跳过无损）")
    print(f"  矛盾可发现：{'✅' if r['contradiction_discoverable'] else '❌'}")
    print("→ 对照 v4：想改重点只能杀掉重跑——已研 10 源的劳动全部陪葬。")


def part3_cancel(tmp: Path) -> None:
    hr("Part 3 · 软停线：半途产物也是产物")
    steering.set_db_path_for_test(str(tmp / "s2.db"))
    r = run_steered_longhaul(workspace_base=tmp / "s2", run_id="s2",
                             steer_after=None, cancel_after=12)
    print(f"第 12 源完成后投递 cancel → 安全点受理，完成当前源即止")
    print(f"  半程声明：「{r['honest_stop_note']}」")
    print(f"  在场率 {r['presence']}——部分结果显式标注，不冒充完整")
    print("→ 停的两档：cancel 软停出诚实半程报告；kill 硬停靠 checkpoint+")
    print("  workspace 双恢复（L06/课程九，只引用）。")


def part4_gate(tmp: Path) -> None:
    hr("Part 4 · 权限门：越权 100% 拦下，放行同样留痕")
    steering.set_db_path_for_test(str(tmp / "gate.db"))
    ws_root = tmp / "s1"
    calls = [
        ToolAction("write_file", str(ws_root / "s1" / "draft.md")),
        ToolAction("write_file", "C:/Windows/system32/hosts"),
        ToolAction("http", "https://api.example.com/publish", method="POST"),
        ToolAction("web_search", "常规检索", cost_tokens=500),
        ToolAction("browse", "深度爬取全站", cost_tokens=99999),
    ]
    for a in calls:
        v, reason = gate_tool(a, workspace_root=ws_root)
        mark = "✅ 放行" if v == "allow" else "⛔ 需审批"
        print(f"  {mark}  {a.tool}({(a.target or '')[:40]}) —— {reason}")
    print("\n判定日志（放行与拦截都留痕）：")
    for row in steering.gate_log():
        print(f"  [{row['verdict']:>14}] {row['tool']} —— {row['reason']}")
    print("→ 审批流复用 agent-ops L05 interrupt + 课程十 inbox（只引用）；")
    print("  本课交付的是门：审批点从「发布环节」推广到「任意危险工具调用」。")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="steer_lesson_"))
    part1_channel(tmp)
    part2_reroute(tmp)
    part3_cancel(tmp)
    part4_gate(tmp)
    hr("两条主线的位置（L07）")
    print("窗口经济：改道保住的是已花掉的注意力——10 源的研究成果不因需求")
    print("         变化而作废；软停把「部分注意力投入」兑换成诚实的部分产出。")
    print("外置化：  驾驶舱的抓手全在窗口外——指令住 sqlite 队列、计划住")
    print("         plan.md、审计住判定日志；窗口只在安全点看一眼最新计划。")


if __name__ == "__main__":
    main()
