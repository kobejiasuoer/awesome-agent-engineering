"""L00 · 全景与基线：会话式的天花板
==================================================

本脚本做两件事：
    1. 用「现状 v3 的简化轨迹模型」模拟**人肉盯梢**：同一主题连问 5 个模拟日，
       每天全量重研——诚实记录会话式范式在盯梢任务上的裸奔结局
       （存档 baseline_ambient.json，之后每课对照）。
    2. 附加一条「人忘了问」支线：Day4（重大进展日）没人发起研究会怎样。

为什么用「轨迹模型」而不是直接跑真实 research-assistant：
    - 真实图依赖 ChatZhipuAI（要 API key），无法满足「全离线可复现」硬约束。
    - 要演示的是**范式级结论**——会话式系统没有触发器/变化检测/增量路径/
      打扰判断，这与用真实 LLM 还是 mock 无关。
    - 简化模型忠实复刻现状行为：每次提问都全量跑
      split → researcher×N → summarize → writer，
      以及现状 web_search 的兜底缺口（失败字符串混进材料）。

诚实标注：
    - mock 下的 token 为字符数/4 估算（非真实 usage_metadata）。
    - 信源为脚本化 5 日时间线（eval_agent/ambient_timeline.py），内容教学虚构。
    - 报告相似度用 difflib 序列相似度（真实系统用语义相似度更准，结论方向一致）。

跑法（零外部依赖、零联网、零真实等待——5 天几秒跑完）：
    python code.py
"""
from __future__ import annotations

import asyncio
import difflib
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

# Windows 控制台默认 GBK，统一 utf-8（课程硬约束）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 让脚本在仓库根 / 课程目录 / 项目目录都能跑
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_PROJ = _REPO / "portfolio-projects" / "research-assistant"
sys.path.insert(0, str(_PROJ))
sys.path.insert(0, str(_PROJ / "src"))

from eval_agent.ambient_timeline import (  # noqa: E402
    TOPIC, TIMELINE_DAYS, DAY_EXPECTATIONS,
    AmbientTimeline, SourceUnavailableError,
)
from research_assistant.clock import FakeClock  # noqa: E402

# 现状配置（搬 config.py 默认值：证明「会话式跑一次」本身是健康的）
NUM_SUBTOPICS = 3


def estimate_tokens(text: str) -> int:
    """诚实估算：token ≈ 字符数/4。"""
    return max(1, len(text) // 4)


# ════════════════════════════════════════════════════════════
# Part 1 · 现状 v3 的简化轨迹模型（会话式：每问一次，全量跑一遍）
# ════════════════════════════════════════════════════════════

@dataclass
class DayResult:
    """一个模拟日的人肉盯梢结局档案。"""
    day: int
    asked: bool                    # 这天人有没有来问（会话式：不问=什么都不发生）
    tokens: int                    # 当日消耗（全量重研）
    report_chars: int
    similarity_vs_prev: float      # 与前一日报告的文本相似度（顺序敏感）
    content_similarity_vs_prev: float  # 顺序无关的内容相似度（行排序后对比）
    new_facts_highlighted: bool    # 报告是否主动标出「今天新增了什么」（现状：否）
    contradiction_marked: bool     # Day4 矛盾是否有 ✏️ 修正标注（现状：否）
    failure_string_in_report: bool  # 信源故障字符串是否混进报告（Day5 现状：是）
    interrupted_user: bool         # 是否向用户推送了全量产出（现状：问了就推全量）
    expectation: str               # 常驻式应有的正确行为（对照）
    notes: str                     # 诚实备注


async def run_full_research(timeline: AmbientTimeline, day: int) -> tuple[str, int]:
    """复刻现状 v3 的一次全量研究（会话式，简化轨迹模型）。

    关键复刻点：
        - 每次提问全量跑 split→researcher×N→summarize→writer（没有增量概念）
        - researcher 的搜索兜底 = 现状 tools.py 行为：失败返回字符串混进材料
    Returns:
        (report, tokens)
    """
    tokens = 0

    # split：主题拆 N 个子题
    subtopics = [f"{TOPIC}·子题{i+1}" for i in range(NUM_SUBTOPICS)]
    tokens += estimate_tokens(TOPIC) + estimate_tokens("\n".join(subtopics))

    # researcher×N（并行）：每个子题搜一次当日信源
    async def one_researcher(sub: str) -> str:
        try:
            result = timeline.as_search_text(sub, day)
        except SourceUnavailableError as e:
            # ⚠️ 复刻现状 web_search 兜底：失败字符串直接当材料返回（不诚实降级）
            result = f"搜索 '{sub}' 失败（{type(e).__name__}: {e}）。可换关键词重试。"
        return result

    findings = await asyncio.gather(*[one_researcher(s) for s in subtopics])
    for f in findings:
        tokens += estimate_tokens(f)

    # summarize + writer：全量材料 → 全量报告（现状没有「只写增量」的模式）
    material = "\n".join(findings)
    summary = material[:400]
    tokens += estimate_tokens(material) + estimate_tokens(summary)
    report = f"【{TOPIC} 研究报告】\n{material}\n【小结】{summary[:120]}"
    tokens += estimate_tokens(report)
    return report, tokens


# ════════════════════════════════════════════════════════════
# Part 2 · 人肉盯梢 5 日基线（会话式范式的裸奔）
# ════════════════════════════════════════════════════════════

def _sorted_lines(text: str) -> str:
    """行排序（顺序无关的内容视图）：条目顺序打乱不影响对比。"""
    return "\n".join(sorted(ln.strip() for ln in text.splitlines() if ln.strip()))


async def run_baseline(skip_day: int | None = None) -> list[DayResult]:
    """模拟人肉盯梢：每个模拟日人来问一次（skip_day 那天忘了问）。"""
    clock = FakeClock()
    timeline = AmbientTimeline(clock=clock, start_ts=clock.now())
    results: list[DayResult] = []
    prev_report = ""

    for day in range(1, TIMELINE_DAYS + 1):
        if day == skip_day:
            # 会话式的死穴：人不问，什么都不发生（没有触发器）
            results.append(DayResult(
                day=day, asked=False, tokens=0, report_chars=0,
                similarity_vs_prev=0.0, content_similarity_vs_prev=0.0,
                new_facts_highlighted=False,
                contradiction_marked=False, failure_string_in_report=False,
                interrupted_user=False,
                expectation=DAY_EXPECTATIONS[day],
                notes="人忘了问 → 系统全盲：这天世界发生了什么，永远没人知道",
            ))
            clock.advance_days(1)
            continue

        report, tokens = await run_full_research(timeline, day)
        sim = difflib.SequenceMatcher(None, prev_report, report).ratio() if prev_report else 0.0
        csim = (difflib.SequenceMatcher(None, _sorted_lines(prev_report),
                                        _sorted_lines(report)).ratio()
                if prev_report else 0.0)
        polluted = ("失败（" in report) or ("超时" in report)

        results.append(DayResult(
            day=day, asked=True, tokens=tokens, report_chars=len(report),
            similarity_vs_prev=round(sim, 3),
            content_similarity_vs_prev=round(csim, 3),
            new_facts_highlighted=False,   # 现状：全量报告，不标增量
            contradiction_marked=False,    # 现状：无 ✏️ 修正通道（矛盾埋在正文里）
            failure_string_in_report=polluted,
            interrupted_user=True,         # 现状：问了就推全量报告（不判断值不值得）
            expectation=DAY_EXPECTATIONS[day],
            notes=_day_note(day, sim, csim, polluted),
        ))
        prev_report = report
        clock.advance_days(1)

    return results


def _day_note(day: int, sim: float, csim: float, polluted: bool) -> str:
    if day == 1:
        return "建仓日：全量研究合理（这是会话式唯一不吃亏的一天）"
    if day == 2:
        return (f"世界没变（内容相似度 {csim:.0%}），仍全量重研+全量推送；"
                f"且条目顺序一打乱，文本相似度掉到 {sim:.0%}——肉眼/文本 diff 既费人又不可靠")
    if day == 3:
        return "只多了一条小更新，却重研全部子题；新增内容埋在全量报告里要人肉 diff"
    if day == 4:
        return "重大反转出现，但报告无 ✏️ 修正标注——旧结论被静默覆盖，矛盾要读者自己发现"
    if day == 5 and polluted:
        return "信源故障字符串混进报告被当成当日结论——「没能看到」被写成了「今天的情况」"
    return ""


# ════════════════════════════════════════════════════════════
# Part 3 · 打印 + 存档
# ════════════════════════════════════════════════════════════

def print_report(results: list[DayResult], skipped: list[DayResult]):
    print()
    print("=" * 76)
    print("  Ambient L00 · 人肉盯梢裸基线 —— 会话式范式在盯梢任务上的结局")
    print("=" * 76)
    print(f"{'日':<4} {'问了?':<5} {'token(估)':>10} {'文本相似':>8} {'内容相似':>8} "
          f"{'标增量':>6} {'标修正':>6} {'污染':>5} {'打扰':>5}")
    print("-" * 76)
    for r in results:
        print(f"Day{r.day:<2} {'是' if r.asked else '否':<5} {r.tokens:>10} "
              f"{r.similarity_vs_prev:>7.0%} {r.content_similarity_vs_prev:>7.0%} "
              f"{'—' if not r.asked else ('是' if r.new_facts_highlighted else '否'):>6} "
              f"{'—' if not r.asked else ('是' if r.contradiction_marked else '否'):>6} "
              f"{'是' if r.failure_string_in_report else '否':>5} "
              f"{'是' if r.interrupted_user else '否':>5}")
    print("-" * 76)
    total = sum(r.tokens for r in results)
    print(f"5 日总消耗：{total} token（估）——其中 Day2 的 {results[1].tokens} 是纯重复劳动")
    print()
    print("逐日诊断（现状结局 vs 常驻式应有行为）：")
    print("-" * 76)
    for r in results:
        print(f"  Day{r.day} 现状：{r.notes}")
        print(f"       应为：{r.expectation}")
        print()
    print("「人忘了问」支线（跳过 Day4 重大进展日）：")
    for r in skipped:
        if not r.asked:
            print(f"  Day{r.day}：{r.notes}")


def save_baseline(results: list[DayResult], skipped: list[DayResult]) -> Path:
    """存档 baseline_ambient.json（后续每课对照）。"""
    total = sum(r.tokens for r in results)
    payload = {
        "course": "ambient-agent-lessons",
        "lesson": "L00",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "topic": TOPIC,
        "honesty_note": "mock 模式：token 为字符/4 估算，报告相似度为 difflib 序列相似度；"
                        "范式级结论（无触发/无增量/无打扰判断/故障污染/不问全盲）与真实 API 一致",
        "paradigm_gaps": {
            "no_trigger": "一切开始于人发消息；人忘了问 = 全盲（见 skipped_day_probe）",
            "no_change_detection": "Day2 世界没变仍全量重研（相似度见 daily[1]）",
            "no_incremental_path": "Day3 只有一条新内容却重研全部子题",
            "no_interrupt_judgement": "每天推全量报告：Day2 不值得也推，无 digest/沉默选项",
            "dishonest_on_source_failure": "Day5 失败字符串混进报告冒充当日结论",
            "no_correction_marking": "Day4 矛盾无 ✏️ 标注，旧结论被静默覆盖",
        },
        "totals": {"tokens_5days": total,
                   "interrupts": sum(1 for r in results if r.interrupted_user),
                   "wasted_tokens_day2": results[1].tokens},
        "daily": [asdict(r) for r in results],
        "skipped_day_probe": [asdict(r) for r in skipped],
    }
    path = _HERE / "baseline_ambient.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n📦 基线档案已存：{path}")
    return path


async def main():
    print("=" * 76)
    print("  L00 · 范式倒置全景 + 人肉盯梢裸基线")
    print("=" * 76)
    print()
    print(f"盯梢任务：持续追踪「{TOPIC}」，信源为脚本化 5 日时间线：")
    for d, exp in DAY_EXPECTATIONS.items():
        print(f"  Day{d}: {exp}")
    print()
    print("现状 v3 是会话式（pull）：只能人肉每天来问一次，每问全量重研。")
    print("下面用可注入时钟快进 5 天（零真实等待），记录裸奔结局……")

    results = await run_baseline()
    skipped = await run_baseline(skip_day=4)  # 「人忘了问」支线：偏偏忘在重大进展日
    print_report(results, skipped)
    save_baseline(results, skipped)

    print()
    print("=" * 76)
    print("  基线结论：会话式的五个环节全靠人，盯梢任务上全线失守")
    print("=" * 76)
    print("  ① 发起靠人  → 忘了问 = 全盲（Day4 支线）")
    print("  ② 研究对象靠人 → 世界没变也全量重研（Day2 纯浪费）")
    print("  ③ 增量靠人 diff → 新东西埋在全量报告里（Day3）")
    print("  ④ 开口不判断  → 每天全量轰炸，无 digest/沉默（Day2 也打扰）")
    print("  ⑤ 故障不诚实  → 「没能看到」被写成「没有变化」（Day5 污染）")
    print()
    print("  之后每课修一环：L01 触发 → L02/L03 增量 → L04/L05 开口 → L06/L07 常驻运营")


if __name__ == "__main__":
    asyncio.run(main())
