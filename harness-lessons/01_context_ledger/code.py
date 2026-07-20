"""L01 · 上下文账本：先量出来才管得住
==================================================

本脚本做四件事：
    1. 演示「token 数」为什么必须是依赖注入（与课程十的可注入时钟同构）。
    2. 水位三区的算术：safe / caution / danger / over 的边界行为。
    3. 给长途任务的长程裸奔前 6 源逐调用记账——看着水位从 safe 爬进 caution。
    4. 打开 enable_context_ledger，跑 RA 主链路五节点（FakeLLM + mock 搜索），
       看账本给出的四桶占比——「工具结果是最大消耗方」从此有账可查；
       再关掉开关重跑，验证零介入（一条记录都不产生）。

诚实标注：
    - FakeTokenizer 为 len//4 字符近似（与 cost_budget 估算同口径），
      对中文偏保守；占比/水位/越限点等结构性结论不受影响。
    - FakeLLM 的回复是预设短语——本课量的是「进 prompt 的东西」，
      与回复质量无关，这正是账本能在 mock 下成立的原因。

跑法（零外部依赖、零联网、零真实等待）：
    python code.py
"""
from __future__ import annotations

import asyncio
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

from eval_agent.long_haul import (  # noqa: E402
    DOC_IDS, SYSTEM_PROMPT, LongHaulSource,
)
from research_assistant import context_ledger as cl  # noqa: E402
from research_assistant.config import settings  # noqa: E402


def hr(title: str) -> None:
    print(f"\n{'═' * 62}\n{title}\n{'═' * 62}")


# ════════════════════════════════════════════════════════════
# Part 1 · 为什么 token 数必须可注入
# ════════════════════════════════════════════════════════════
def part1_injectable() -> None:
    hr("Part 1 · 可注入 tokenizer：本课程的命根子")
    tk = cl.FakeTokenizer()
    text = "同一段文本" * 100
    print(f"count(500字) 三次调用：{tk.count(text)}, {tk.count(text)}, {tk.count(text)}"
          f"  ← 确定性（真 tokenizer 慢且模型绑定，CI 里没法当尺子）")
    print("课程十把 time.time() 换成 clock.now()，5 天测试秒级跑完；")
    print("本课把「窗口够不够」换成 tokenizer.count() + 注入 limit——同一个道理：")
    print("🎯 判断依据必须是可替换的依赖，行为才可测试、结论才可复现。")


# ════════════════════════════════════════════════════════════
# Part 2 · 水位三区
# ════════════════════════════════════════════════════════════
def part2_zones() -> None:
    hr("Part 2 · 水位三区：「最后 20% 不干大事」的量化版")
    limit = 8000
    for total in (3000, 4800, 6799, 6800, 8000, 8001):
        z = cl.zone(total, limit)
        mark = {"safe": "✅ 放心干活", "caution": "⚠️ 该压缩/外置了（L02 触发区）",
                "danger": "🚨 只做收尾，不开新工作", "over": "💀 越限（真实 API 会 400）"}[z]
        print(f"  {total:>5}/{limit}  {total / limit:>5.0%}  {z:<8} {mark}")


# ════════════════════════════════════════════════════════════
# Part 3 · 给长程裸奔记账：看着水位爬升
# ════════════════════════════════════════════════════════════
def part3_longhaul_ledger() -> None:
    hr("Part 3 · 长途任务前 6 源逐调用记账（长程单窗形态）")
    src = LongHaulSource()
    led = cl.WindowLedger(tokenizer=cl.FakeTokenizer(), limit=8000)
    catalog = src.catalog_text()
    tools: list[str] = []
    notes: list[str] = []
    print("| 调用 | 源 | system | task_state | tool_results | history | 总计 | 水位 |")
    print("|---|---|---|---|---|---|---|---|")
    for doc_id in DOC_IDS[:6]:
        text = src.fetch(doc_id)
        rec = led.measure("study", system=SYSTEM_PROMPT,
                          task_state=catalog + "请研读下一篇文档并记录要点。",
                          tool_results="".join(tools) + text,
                          history="".join(notes))
        p = rec.parts
        print(f"| #{rec.call_no} | {doc_id} | {p['system']} | {p['task_state']} "
              f"| {p['tool_results']:,} | {p['history']} | {rec.total:,} | {rec.zone} |")
        tools.append(text)
        notes.append(f"已研读 {doc_id}，要点已记。")
    s = led.summary()
    print(f"\n峰值 {s['peak']:,}/{s['limit']:,}（{s['peak_zone']}），"
          f"水位分布 {s['zone_counts']}——第 5 源就进了 caution：")
    print("裸奔不是死在第 11 源那一刻，是从第 5 源就开始病了（L02 的触发区就在这里）。")


# ════════════════════════════════════════════════════════════
# Part 4 · RA 主链路集成：开关开 vs 关
# ════════════════════════════════════════════════════════════
class FakeLLM:
    """预设回复的假 LLM（对齐 tests/conftest.py 风格）。"""

    def __init__(self, responses: dict[str, str], default: str = "mock 回复"):
        self.responses = responses
        self.default = default

    def invoke(self, prompt, **kwargs):
        class _Msg:
            def __init__(self, content):
                self.content = content
        text = prompt if isinstance(prompt, str) else str(prompt)
        for key, resp in self.responses.items():
            if key in text:
                return _Msg(resp)
        return _Msg(self.default)


async def run_main_chain() -> None:
    """跑 RA 主链路五调用：split → researcher → summarize → writer → reviewer。"""
    from research_assistant import nodes

    long_search = ("[检索结果] 关于该子题的资料正文。" * 120)   # 模拟一次肥搜索返回

    async def fake_search(q):
        return long_search

    orig = nodes.web_search
    nodes.web_search = fake_search
    try:
        llm = FakeLLM({"研究规划师": "子题A\n子题B", "研究员": "mock 发现",
                       "综合分析师": "mock 摘要" * 30, "撰写者": "mock 报告" * 60,
                       "审稿人": "合格"})
        nodes.make_split(llm)({"topic": "Agent 生态调研"})
        r = nodes.make_researcher(llm)
        await r({"subtopic": "子题A"})
        await r({"subtopic": "子题B"})
        nodes.make_summarize(llm)({"findings": ["【子题A】mock 发现" * 20,
                                                "【子题B】mock 发现" * 20]})
        nodes.make_writer(llm)({"research_summary": "mock 摘要" * 30,
                                "feedback": "", "truncated": False})
        nodes.make_reviewer(llm)({"report": "mock 报告" * 60, "rewrite_count": 0,
                                  "re_research_count": 0, "findings": []})
    finally:
        nodes.web_search = orig


def part4_integration() -> None:
    hr("Part 4 · RA 主链路：enable_context_ledger 开 vs 关")
    # 开：五节点六调用全入账
    settings.__dict__["enable_context_ledger"] = True
    cl.reset_ledger()
    asyncio.run(run_main_chain())
    led = cl.get_ledger()
    print("开关开——账本报表：")
    print(led.report())
    share = led.summary()["share"]
    print(f"\n→ tool_results 占 {share['tool_results']:.0%}：治理顺序有了依据——")
    print("  先控源（L04 整形）再止损（L02 压缩）；能外置的外置（L05/L06）。")
    print("  （四桶口径：检索材料→tool_results；findings/summary/report 等")
    print("   LLM 产物→history；指令与 skill→task_state；v4 单串调用无独立 system。）")

    # 关：零介入
    settings.__dict__["enable_context_ledger"] = False
    cl._current_ledger = None
    asyncio.run(run_main_chain())
    print(f"\n开关关——重跑同样链路后账本：{cl.get_ledger()}（None = 一条记录都没有，零介入）")


def main() -> None:
    import logging
    logging.disable(logging.INFO)   # 演示脚本静默节点日志（对齐 run_ambient_eval 先例）
    part1_injectable()
    part2_zones()
    part3_longhaul_ledger()
    part4_integration()
    hr("两条主线的位置（L01）")
    print("窗口经济：账本是空间预算的记账器——量租金是砍租金的前提；")
    print("         水位三区把「什么时候该动手」变成了可测的阈值（L02 在 caution 区触发）。")
    print("外置化：  账本本身不外置任何东西，但它指认了该外置谁——")
    print("         四桶占比就是外置优先级表（tool_results 大头 → L04/L06 先动它）。")


if __name__ == "__main__":
    main()
