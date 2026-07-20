"""L06 · 文件即工作记忆：窗口只留指针
==================================================

本脚本做四件事：
    1. 工作区解剖：plan/sources/notes/draft 四件套 + 一行指针协议 + 目录树。
    2. 长途任务主秀：L05 隔离档之上加工作区——原文无损落盘（被压缩/截断
       丢的都能回来）、指针 vs 全文的体积对比（33 倍差）。
    3. recitation：后半程每步现读 plan.md 进窗口尾部——重读胜于记住；
       改了计划复述立刻变（文件是事实源，窗口是缓存）。
    4. 崩溃续跑（双恢复的工作区半边）：S18 后进程死亡 → 新进程 attach
       同一工作区 → fetch 总数仍 30（无工作区的重启=前功尽弃，48 次）。

诚实标注：
    - 双恢复的另一半（checkpoint 恢复图状态）是课程九资产，本课只引用
      不重演——本演示的「进程」是同进程内的两个对象，复刻的是「工作集
      从文件回来」这半边的语义（真实跨进程行为由文件系统保证，机制相同）。

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

from eval_agent.harness_runs import run_workspace_longhaul  # noqa: E402
from research_assistant.workspace import Workspace  # noqa: E402


def hr(title: str) -> None:
    print(f"\n{'═' * 62}\n{title}\n{'═' * 62}")


def part1_anatomy(base: Path) -> None:
    hr("Part 1 · 工作区解剖：四件套 + 指针协议")
    ws = Workspace("demo", base)
    ws.write_plan("目标：30 源全研、提取关键事实、指出跨源矛盾。")
    ws.save_source("S17", "《生态依赖图谱》全文……" * 400)
    ws.add_note("S17", "[S17] 结论：依赖图谱三层结构，核心维护者 40 人。")
    ws.write_draft("（草稿占位）")
    print(ws.tree())
    print("\n窗口里只住指针（State 不再扛全文）：")
    print(f"  {ws.pointer('sources/S17.txt')}")
    print("→ 要用时按需读回；回读也要过 L04 整形——外置不是免费回读。")
    print("→ 三存储各管一段：checkpoint=状态快照（机器读）、ledger=进度语义、")
    print("  workspace=认知外置（**人机共读写**——你现在就能用编辑器打开它改）。")


def part2_longhaul(base: Path) -> dict:
    hr("Part 2 · 长途主秀：隔离档 + 工作区")
    r = run_workspace_longhaul(workspace_base=base, run_id="hero")
    print(f"完成 {r['completed_sources']}/30，主窗峰值 {r['main_peak_tokens']:,}，"
          f"在场率 {r['presence']}，矛盾可发现 {'✅' if r['contradiction_discoverable'] else '❌'}")
    print(f"指针总量 {r['pointer_chars']:,} 字 vs 原文总量 {r['full_chars']:,} 字"
          f"（{r['full_chars'] // max(1, r['pointer_chars'])} 倍差）——")
    print("  「原文在不在手边」不再依赖窗口：压缩丢的、截断砍的，sources/ 里都在。")
    print("\n工作区收尾形态（前 8 行）：")
    for line in r["workspace_tree"]:
        print(f"  {line}")
    return r


def part3_recitation(base: Path) -> None:
    hr("Part 3 · recitation：重读胜于记住")
    ws = Workspace("recite-demo", base)
    ws.write_plan("目标 A：全量研究 30 源。")
    print(f"复述块（第一次）：{ws.recitation_block().splitlines()[1]}")
    ws.write_plan("目标 B：优先 safety 类，跳过 marketing 类（改道后计划）。")
    print(f"计划被改后现读：{ws.recitation_block().splitlines()[1]}")
    print("→ 每次都现读文件而不是引用窗口里的旧计划——文件是事实源，窗口是缓存；")
    print("  L07 的改道改的就是 plan.md，复述自动带上最新版。")
    print("  长途跑法里后半程（S16 起）每步复述一次：用一次小读换整程不迷航")
    print("  （对抗 lost-in-the-middle 的目标漂移——认知收益部分引证据，")
    print("   机械事实是：15 次复述、每次 ~50 token，总开销 <1% 计费）。")


def part4_crash(base: Path) -> None:
    hr("Part 4 · 崩溃续跑：双恢复的工作区半边")
    r = run_workspace_longhaul(workspace_base=base, run_id="crash", crash_at=18)
    print(f"剧本：第 18 源后进程死亡 → 新进程 Workspace.attach 同一 run_id 续跑")
    print(f"  「有笔记=已研完」：note_names() 就是进度事实源，跳过 S01–S18")
    print(f"  最终完成 {r['completed_sources']}/30，在场率 {r['presence']}")
    print(f"  fetch 总数：{r['total_fetches']}（前功不弃）")
    print(f"  对照·无工作区的重启：{r['refetch_waste_without_ws']} 次"
          f"（18 次白干 + 30 次重来——结构性推算）")
    print("→ checkpoint 管「图状态从哪继续」（课程九，只引用），")
    print("  workspace 管「工作集还在不在」——双恢复各管一段。")


def main() -> None:
    base = Path(tempfile.mkdtemp(prefix="ws_lesson_"))
    part1_anatomy(base)
    part2_longhaul(base)
    part3_recitation(base)
    part4_crash(base)
    hr("两条主线的位置（L06）")
    print("窗口经济：State 从「扛全文」变成「持指针」——2,763 字指针替 91,366 字")
    print("         原文站岗；窗口彻底回归「工作集缓存」的本分。")
    print("外置化：  虚拟内存图在本课闭环——RAM(窗口)/磁盘(文件)/swap(压缩)/")
    print("         进程(子代理) 全部就位；剩下的是驾驶舱（L07）与懒加载（L08）。")


if __name__ == "__main__":
    main()
