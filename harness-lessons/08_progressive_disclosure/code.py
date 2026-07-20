"""L08 · 渐进披露与 skills：指令的懒加载
==================================================

本脚本做四件事：
    1. 指令膨胀定律现场：4 个技能全文常驻 vs 三层架构的每调用账单。
    2. 三层组装解剖：常驻核心 / 索引层 / 按需层——同一任务只为命中的
       技能付全文租金（breakdown 三层计量）。
    3. 三任务对照：深度调研 / 快讯速览 / 无关任务——各命中各的，
       互不搭车；30 次调用的膨胀账（单体 vs 三层）。
    4. 同构收口：记忆索引（L03）与工作区指针（L06）进索引层——
       「索引常驻、正文按需」一套机制三种内容；反例：description
       写成抽象词=漏加载（索引质量决定召回的回旋镖）。

诚实标注：
    - 本课扩展 frontier-L03 的 skill_loader（复用 enable_skills 与 skills/
      目录，不新建模块）；writer 单点路径保持现状不动。
    - match_skills 是机械关键词匹配（可换 LLM 判断——判断交给模型）；
      三层结构与逐层计量是代码的纪律。

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

logging.disable(logging.INFO)

from research_assistant.context_ledger import FakeTokenizer  # noqa: E402
from research_assistant.skill_loader import (  # noqa: E402
    SkillLoader, build_layered_system, monolithic_system,
)

CORE = ("你是深度研究员。红线：不得编造未在信源中出现的数字；"
        "省略必须显式；矛盾必须显式指出。")

tk = FakeTokenizer()


def hr(title: str) -> None:
    print(f"\n{'═' * 62}\n{title}\n{'═' * 62}")


def part1_inflation(loader: SkillLoader) -> None:
    hr("Part 1 · 指令膨胀定律：能力越多，system 越肥")
    metas = loader.list_skills()
    bodies = sum(tk.count(loader.load_skill(m.name)) for m in metas)
    index = tk.count(loader.format_skill_descriptions())
    print(f"技能库：{len(metas)} 个（{', '.join(m.name for m in metas)}）")
    print(f"  全部正文合计：{bodies:,} token  vs  目录索引：{index} token"
          f"（{bodies // max(1, index)} 倍差）")
    print("单体注入=每次调用都扛全部正文；90% 场景用不到 90% 的指令，")
    print("但每次都付全额窗口租金——frontier-L03 已在 writer 单点做了渐进加载")
    print("的雏形，本课把它推广成全链路的三层架构。")


def part2_layers(loader: SkillLoader) -> None:
    hr("Part 2 · 三层组装解剖")
    text, bd = build_layered_system(CORE, query="做一次跨源深度调研", loader=loader)
    print("任务：「做一次跨源深度调研」")
    print(f"  常驻核心：{bd['core_tokens']} token（身份+红线，永远在、不可压）")
    print(f"  索引层：  {bd['index_tokens']} token（4 个技能各一行——「可能有用」挂在墙上）")
    print(f"  按需层：  {bd['ondemand_tokens']} token（只装命中的 {bd['matched_skills']}）")
    print(f"  合计 {tk.count(text):,} token；未命中的 quick-scan/comparison-table 正文一字未进。")


def part3_tasks(loader: SkillLoader) -> None:
    hr("Part 3 · 三任务对照 + 30 调用膨胀账")
    _, mono = monolithic_system(CORE, loader)
    print(f"| 任务 | 命中技能 | 三层账单 | 单体账单 |")
    print(f"|---|---|---|---|")
    layered_costs = []
    for q in ("做一次跨源深度调研", "扫一眼今天有什么新的快讯", "帮我订个会议室"):
        text, bd = build_layered_system(CORE, query=q, loader=loader)
        cost = tk.count(text)
        layered_costs.append(cost)
        hits = ",".join(bd["matched_skills"]) or "（无）"
        print(f"| {q[:14]} | {hits} | {cost:,} | {mono:,} |")
    print(f"\n30 次调用的膨胀账（以深度调研任务为例）：")
    print(f"  单体：{mono:,} × 31 调用 = {mono * 31:,} token")
    print(f"  三层：{layered_costs[0]:,} × 31 调用 = {layered_costs[0] * 31:,} token"
          f"（省 {(1 - layered_costs[0] / mono):.0%}）")
    print("  技能库越大差距越悬殊——索引层成本只随「技能数×一行」线性长。")


def part4_isomorphism(loader: SkillLoader) -> None:
    hr("Part 4 · 同构收口 + 漏加载反例")
    text, bd = build_layered_system(
        CORE, query="做一次跨源深度调研", loader=loader,
        memory_index="# 操作记忆索引\n- [report-style] 报告语言与长度偏好（用户纠正）",
        workspace_pointers="📁 [sources/S17.txt]（13,624 字）开头：《生态依赖图谱》…")
    print("整门课的窗口构成定稿图（三层指令架构）：")
    print("  ┌ 常驻核心   身份+红线（L02：system 不可压）")
    print("  ├ 索引层     skill 目录 + 记忆索引(L03) + 工作区指针(L06) ——便宜常驻")
    print("  └ 按需层     命中的 skill 正文 + 记忆正文 + 文件内容 ——用时换入")
    print(f"  本次组装：索引层 {bd['index_tokens']} token 里同时住着技能目录、")
    print("  记忆索引、文件指针——「索引常驻、正文按需」一套机制三种内容：")
    print("  记忆是**学到的**（agent 写），skill 是**配置的**（人写），文件是**产出的**。")

    bad_dir = Path(tempfile.mkdtemp(prefix="skills_bad_")) / "skills"
    (bad_dir / "style-rules").mkdir(parents=True)
    (bad_dir / "style-rules" / "SKILL.md").write_text(
        "---\nname: style-rules\ndescription: 输出规范\n---\n\n# 报告格式要求……",
        encoding="utf-8")
    ld_bad = SkillLoader(bad_dir)
    hit = ld_bad.match_skills("写一份研究报告")
    print(f"\n反例：description 写成抽象词「输出规范」→ 任务「写一份研究报告」"
          f"命中 {hit or '（漏！）'}")
    print("  索引质量决定召回——与 L03 记忆 triggers 同一根软肋：")
    print("  渐进披露把「全文常驻」的窗口成本换成了「索引写得好不好」的召回风险。")


def main() -> None:
    loader = SkillLoader()
    part1_inflation(loader)
    part2_layers(loader)
    part3_tasks(loader)
    part4_isomorphism(loader)
    hr("两条主线的位置（L08）")
    print("窗口经济：指令的「可能有用」与「此刻在场」分开计价收口——")
    print("         核心永在、索引便宜常驻、正文按需；膨胀账省约五成起。")
    print("外置化：  最后一类内容（指令正文）也搬出窗口——至此虚拟内存图")
    print("         八部件齐装；L09 全套合体跑收益矩阵。")


if __name__ == "__main__":
    main()
