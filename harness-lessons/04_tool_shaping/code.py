"""L04 · 工具返回值工程：控源胜于止损
==================================================

本脚本做四件事：
    1. 回看账本证据（工具结果占大头）——宣布教学反转：你在 L02 学的压缩
       其实是最后手段，先控源再止损。
    2. 三板斧过超长文档 S17（≈3,400 token）：截断（显式标记）、分页（无缝
       翻页）、引用（无损外置+指针）——三种整形的窗口占用对比表。
    3. 谎报案例：同一篇「结论在后半段反转」的文档，无标记截断 vs 显式标记
       ——静默掐尾让「争议结论」以「最终结论」的面目进窗口。
    4. 错误也是返回值：40 行堆栈 vs 一行可行动错误的 token 对比。

诚实标注：
    - 「模型看到标记后会去翻页」是真模型行为，FakeLLM 演不出——本演示
      展示的是**窗口文本的差异**（半篇冒充全篇 vs 显式知情），行为差异
      属于认知收益，引证据讲、L09 真模型章抽查。

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

from eval_agent.long_haul import OVERSIZED_DOC_IDS, LongHaulSource  # noqa: E402
from research_assistant import tool_shaping as ts  # noqa: E402
from research_assistant.context_ledger import FakeTokenizer  # noqa: E402


def hr(title: str) -> None:
    print(f"\n{'═' * 62}\n{title}\n{'═' * 62}")


tk = FakeTokenizer()


def part1_inversion() -> None:
    hr("Part 1 · 教学反转：压缩是最后手段")
    print("账本证据（L00/L01）：工具结果占越限窗口 95%、占 RA 集成窗口 75%。")
    print("L02 教了怎么压——但压缩是有损的、要花摘要钱、还会递归失真。")
    print("🎯 治理顺序应该是：**先控源（本课），再止损（压缩）**：")
    print("   一条 3,400 token 的检索结果，进窗口前整形成 600，")
    print("   比进来之后再花一次 LLM 调用把它压掉，便宜且无损（原文还在源头）。")


def part2_three_axes() -> None:
    hr("Part 2 · 三板斧过超长文档")
    src = LongHaulSource()
    dump = Path(tempfile.mkdtemp(prefix="shaping_demo_"))

    print("| 文档 | 全文直给 | 截断(600) | 分页(400/页) | 引用(指针) |")
    print("|---|---|---|---|---|")
    for doc_id in OVERSIZED_DOC_IDS:
        text = src.fetch(doc_id)
        truncated = ts.shape_result(text, max_tokens=600)
        page = ts.paginate(text, page_tokens=400)
        ref = ts.reference(text, doc_id, dump)
        print(f"| {doc_id} | {tk.count(text):,} tok | {tk.count(truncated):,} tok "
              f"| {tk.count(page['content']):,} tok/页 | {tk.count(ref['pointer']):,} tok |")

    text = src.fetch("S17")
    print("\n截断标记长这样（显式三要素：略了多少/原文多长/怎么拿全文）：")
    print("  " + ts.shape_result(text, max_tokens=600).rsplit("…", 1)[-1].strip())
    p1 = ts.paginate(text, page_tokens=400)
    p2 = ts.paginate(text, offset=p1["next_offset"], page_tokens=400)
    print("\n分页头尾标记（翻页权在 agent 手里）：")
    print("  " + p1["content"].splitlines()[0])
    print("  " + p1["content"].splitlines()[-1])
    print("  " + p2["content"].splitlines()[0] + "  ← 用 next_offset 无缝续读")
    print("\n引用指针（全文无损落盘，窗口只进这一行）：")
    print("  " + ref["pointer"][:100] + "…")


def part3_liar_case() -> None:
    hr("Part 3 · 谎报案例：静默掐尾比溢出更危险")
    doc = ("《方案 A 可行性调研》初步结论：方案 A 在小规模验证中表现良好，"
           "推荐进入下一阶段。" + "（中间是 800 字的验证细节。）" * 60
           + "但随后的大规模复测推翻了初步结论：方案 A 在并发超过 1k 时"
             "出现级联失败，结论修正为：不推荐采用。")
    silent = doc[:200]                                # 无标记硬截断（A3 的做法）
    marked = ts.shape_result(doc, max_tokens=50)      # 显式省略标记

    print("原文结构：前 1/4 说「推荐」，结尾反转成「不推荐」。\n")
    print(f"【无标记截断】窗口只见（{len(silent)} 字）：")
    print(f"  「…{silent[30:90]}…」")
    print("  → 没有任何迹象表明后面还有内容——「推荐采用」以最终结论的")
    print("    面目进了窗口。模型引用它不是幻觉，是被喂了半篇冒充的全篇。\n")
    print(f"【显式标记截断】窗口见到（同样预算）：")
    print(f"  「…{marked[30:90]}…」")
    print(f"  尾部标记：{marked.rsplit('…', 1)[-1].strip()}")
    print("  → 模型**知道**这是节选、知道还有多少、知道怎么拿——")
    print("    翻页第二页就会看到反转（把「要不要看」变成它的决策）。")
    p_last = ts.paginate(doc, offset=len(doc) - 400, page_tokens=100)
    print(f"\n  （翻到末页即见：「…{p_last['content'][-60:-20]}…」）")


def part4_errors() -> None:
    hr("Part 4 · 错误也是返回值")
    fake_traceback = ("Traceback (most recent call last):\n"
                      + '  File "tools.py", line 88, in web_search\n'
                      + "    resp = await client.get(url, timeout=15)\n" * 12
                      + "httpx.ConnectTimeout: timed out")
    short = ts.shape_error("检索超时", "DuckDuckGo 15 秒无响应", "缩小关键词重试一次，仍失败则跳过该子题")
    print(f"40 行堆栈：{tk.count(fake_traceback)} token——对 agent 是纯租金，")
    print("           它不需要知道第 88 行，需要知道下一步怎么办。")
    print(f"可行动错误：{tk.count(short)} token —— 「{short}」")
    print("（呼应 agent-ops L03 结构化降级：错误信息是给调用方的接口，不是给人的日志。）")


def main() -> None:
    part1_inversion()
    part2_three_axes()
    part3_liar_case()
    part4_errors()
    hr("两条主线的位置（L04）")
    print("窗口经济：整形是「砍租金」——账本指认的最大租客（工具结果）在进门")
    print("         前就瘦身；预算含标记，省略的每一字都明码标价。")
    print("外置化：  引用板斧是外置化的先声——全文无损落盘、窗口只留指针；")
    print("         L06 把落盘位置正规化成工作区，指针协议全面接管。")


if __name__ == "__main__":
    main()
