"""L02 · 压缩：有损但有纪律
==================================================

本脚本做四件事：
    1. 微观演示三步纪律：登记 → 摘要 → 验证——用一个「恶意摘要器」
       （什么都不保留）证明登记项是机械保证的，不依赖摘要器的善意。
    2. 长途任务主秀：登记压缩 vs L00 三条裸基线 vs 「不登记」对照组——
       裸奔死于 S11、硬截断 8/20，登记压缩 30 源完赛且 20/20 在场。
    3. 分层可压性：结论层是资产不是缓存，无论多超标都不丢。
    4. 打印完整审计报表——「压缩过」是一等公民信息，无痕压缩=篡史。

诚实标注：
    - 摘要器为确定性假实现（head_summarizer 留前 80 字）——mock 测的是
      机械纪律（登记存活/审计完整），摘要语义保真 FakeLLM 测不了
      （L09 可选真模型章抽查）。
    - 「研读时登记哪些事实」真实系统里是 LLM 判断（判断交给模型），
      本演示用剧本代演（研读某源即登记该源 KEY_FACTS）——登记漏了的
      事实同样会丢，判定质量是另一个战场（见练习 3）。

跑法（零外部依赖、零联网、零真实等待）：
    python code.py
"""
from __future__ import annotations

import logging
import sys
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

logging.disable(logging.INFO)

from eval_agent.harness_runs import run_compacted_longhaul  # noqa: E402
from eval_agent.long_haul import run_naive_longhaul  # noqa: E402
from research_assistant.compactor import (  # noqa: E402
    Compactor, PinnedFact, WindowItem,
)
from research_assistant.context_ledger import FakeTokenizer  # noqa: E402


def hr(title: str) -> None:
    print(f"\n{'═' * 62}\n{title}\n{'═' * 62}")


# ════════════════════════════════════════════════════════════
# Part 1 · 三步纪律：恶意摘要器也丢不掉登记项
# ════════════════════════════════════════════════════════════
def part1_discipline() -> None:
    hr("Part 1 · 登记-摘要-验证：机械保证 vs 摘要器的善意")

    def evil_summarizer(texts):
        return "（摘要）本档案员什么都没保留。"    # 恶意：全丢

    c = Compactor(tokenizer=FakeTokenizer(), limit=1000, threshold_pct=0.6,
                  target_pct=0.3, summarizer=evil_summarizer)
    c.register(PinnedFact("F05", "Argus 上下文页缓存命中时端到端延迟下降 41%"))
    items = [WindowItem("S05", "tool_result",
                        "（超长解析正文……）延迟下降 41% 出现在第 7 节……" + "水" * 3000)]
    new_items, rec = c.compact(items)
    window = "".join(i.text for i in new_items)
    print(f"摘要器：恶意（什么都不保留）")
    print(f"压缩：{rec.before_tokens:,} → {rec.after_tokens:,} token，"
          f"丢弃 {list(rec.dropped_items)}")
    print(f"登记项「延迟下降 41%」压缩后在场：{'✅' if '延迟下降 41%' in window else '❌'}"
          f"（验证 {'✅' if rec.pinned_verified else '❌'}）")
    print("→ 关键事实的存活不依赖摘要器的善意：pinned 块永不进摘要器、永不可压。")
    print("  判断（哪些值得登记/摘要怎么写）交给模型，纪律（登记必活/留审计）交给代码。")


# ════════════════════════════════════════════════════════════
# Part 2 · 长途任务主秀：五行对照
# ════════════════════════════════════════════════════════════
def part2_longhaul() -> dict:
    hr("Part 2 · 长途任务：登记压缩 vs 裸基线")
    enforce = run_naive_longhaul("enforce")
    trunc = run_naive_longhaul("hard_truncate")
    pinned = run_compacted_longhaul(register_pins=True)
    nopin = run_compacted_longhaul(register_pins=False)

    print("\n| 配置 | 完成 | 峰值窗口 | 在场率 | 矛盾 | 计费token | 结局 |")
    print("|---|---|---|---|---|---|---|")
    print(f"| 长程裸奔（L00 A2） | {enforce['completed_sources']}/30 | — | 0/20 | ❌ "
          f"| {enforce['tokens_billed']:,} | 死于 S{enforce['died_at']:02d} |")
    print(f"| 硬截断（L00 A3） | 30/30 | {trunc['peak_window_tokens']:,} | 8/20 | ❌ "
          f"| {trunc['tokens_billed']:,} | 活着但失忆 |")
    print(f"| 压缩·不登记（对照） | 30/30 | {nopin['peak_window_tokens']:,} "
          f"| {nopin['presence']} | {'✅' if nopin['contradiction_discoverable'] else '❌'} "
          f"| {nopin['tokens_billed']:,} | 无契约=运气 |")
    print(f"| **压缩·登记（本课）** | **30/30** | **{pinned['peak_window_tokens']:,}** "
          f"| **{pinned['presence']}** | {'✅' if pinned['contradiction_discoverable'] else '❌'} "
          f"| {pinned['tokens_billed']:,} | **完赛且记得** |")

    print(f"\n解读：")
    print(f"  ①同样的 8k 窗口：裸奔死于 S11，压缩跑完 30 源（{pinned['compactions']} 次压缩）。")
    print(f"  ②同样是压缩：不登记 → 在场率 {nopin['presence']}（关键事实随原文蒸发，")
    print(f"    矛盾对断裂）；登记 → 20/20 + 矛盾可发现（F06/F16 都躺在 pinned 块里）。")
    print(f"  ③「硬截断 8/20」vs「登记压缩 20/20」：两者都在丢信息——差别不是丢不丢，")
    print(f"    是**丢什么由谁决定**：截断按位置盲丢，登记按价值契约保留。")
    return pinned


# ════════════════════════════════════════════════════════════
# Part 3 · 分层可压性：结论是资产不是缓存
# ════════════════════════════════════════════════════════════
def part3_layers() -> None:
    hr("Part 3 · 分层可压性：谁先被压")
    c = Compactor(tokenizer=FakeTokenizer(), limit=400, threshold_pct=0.5,
                  target_pct=0.25)
    items = [
        WindowItem("S01", "tool_result", "原" * 400),
        WindowItem("note-1", "note", "笔" * 400),
        WindowItem("concl-1", "conclusion", "跨源结论：Nimbus 检查点承诺存在反转。" * 10),
    ]
    new_items, rec = c.compact(items)
    print(f"丢弃顺序：{list(rec.dropped_items)}（tool_result 先于 note）")
    print(f"conclusion 仍在：{'✅' if any(i.kind == 'conclusion' for i in new_items) else '❌'}"
          f"（宁可压不到目标，也不丢结论层）")
    print("层级依据：工具原文已被提炼过（可再生），笔记是过程（可再生），")
    print("结论是研究的资产（不可再生）——可再生度决定可压性。")


def main() -> None:
    part1_discipline()
    pinned = part2_longhaul()
    part3_layers()
    hr("Part 4 · 审计报表：「压缩过」是一等公民信息")
    print(pinned["audit_report"])
    print("\n→ 每行审计都可追溯：丢了哪些 item（id 在案）、摘要多长、登记验证结果。")
    print("  递归漂移的解药也在这里：摘要的摘要会累积失真，但 dropped_items 记着")
    print("  原文身份——配合 L06 工作区（原文落盘），可定期做「全量校准」。")
    hr("两条主线的位置（L02）")
    print("窗口经济：压缩是「收房」——水位到 60% 就动手，把租金最高的工具原文")
    print("         换成摘要+登记块；太早浪费摘要成本，太晚连自救动作都放不下。")
    print("外置化：  压缩是有损的窗口内自救；L04/L06 会证明——能外置的别压缩，")
    print("         原文落盘后，压缩只需要处理真正回不去的对话过程。")


if __name__ == "__main__":
    main()
