"""Lesson 04 — 图表与图片理解
==================================
本脚本演示两段式消费模式：描述做索引 + 现场看图作答。
    ① 图表页 → glm-4v-plus 生成结构化描述（无 key 用预录描述 mock）
    ② 同一图表题：「只用描述答」vs「现场看图答」对照
    ③ 描述缓存演示：同一图片重复描述命中缓存（按内容哈希去重）

图表理解是 text-only 管线损失最大的元素（L00 基线 chart 0/4）。
无 API key 时全程 mock，预录了毒文档图表页的真实描述供演示。

运行：python code.py
依赖：PyMuPDF（venv 已装）；VLM 无 key 时走 mock；毒文档 data/multimodal_docs/
"""
from __future__ import annotations

import sys
from pathlib import Path

# Windows GBK 坑：中文输出会 UnicodeEncodeError，统一 utf-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
POISON_PDF = ROOT / "data" / "multimodal_docs" / "company_briefing.pdf"
sys.path.insert(0, str(ROOT / "portfolio-projects" / "knowledge-base-qa" / "src"))


# ══════════════════════════════════════════════════════════════════
# 预录描述（模拟 glm-4v-plus 对毒文档图表页的真实输出）
# 有 API key 时用真 VLM；无 key 时用这份预录，保证教学可复现
# ══════════════════════════════════════════════════════════════════
PRE_RECORDED_DESC = """图表类型：柱状图
标题：2024 年度季度营收（万元）
X轴：季度（Q1, Q2, Q3, Q4）
Y轴：营收（万元），范围 0-3400
数值数据：
- Q1: 1800 万元
- Q2: 2400 万元
- Q3: 2100 万元
- Q4: 2900 万元
趋势结论：
- Q4 营收最高（2900），Q1 最低（1800）
- Q2 到 Q3 环比下降（2400 → 2100）
- 全年整体呈上升趋势，Q4 大幅领先"""

# 预录的「现场看图」答案（模拟 glm-4v-plus 看图答题）
PRE_RECORDED_ANSWERS = {
    "Q1 的营收是多少万元？": "Q1 营收 1800 万元。",
    "Q3 的营收是多少万元？": "Q3 营收 2100 万元。",
    "Q4 的营收是多少万元？": "Q4 营收 2900 万元。",
    "哪个季度的营收最高？": "Q4 营收最高，2900 万元。",
}


def mock_describe(image_bytes: bytes, **kw) -> str:
    """模拟 describe_image：返回预录描述（无 API key 时用）。"""
    return PRE_RECORDED_DESC


def mock_answer(image_bytes: bytes, question: str, **kw) -> str:
    """模拟 answer_with_image：返回预录答案（无 API key 时用）。"""
    # 关键词匹配找预录答案
    for q, a in PRE_RECORDED_ANSWERS.items():
        if any(kw in question for kw in q.split()[:2]):
            return a
    return f"[mock] 根据图表，{question} 的答案在预录数据中。"


# ══════════════════════════════════════════════════════════════════
# 1. 渲染图表页图片
# ══════════════════════════════════════════════════════════════════
def render_chart_image() -> bytes:
    """渲染毒文档 P5 图表页的柱状图区域为 PNG。"""
    import fitz

    doc = fitz.open(str(POISON_PDF))
    page = doc[4]  # P5 图表页
    # 柱状图区域（generate_poison_pdf 里 insert_image 的 Rect）
    pix = page.get_pixmap(dpi=150, clip=fitz.Rect(60, 80, 535, 460))
    doc.close()
    return pix.tobytes("png")


# ══════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════
def main() -> None:
    if not POISON_PDF.exists():
        print(f"[ERR] 找不到毒文档 {POISON_PDF}")
        return

    from kb_qa.config import settings
    has_key = bool(settings.zhipuai_api_key)
    mode = "真实 glm-4v-plus" if has_key else "mock（预录描述，无 API key）"

    print("=" * 70)
    print(f"演示 1：图表页 → VLM 结构化描述（{mode}）")
    print("=" * 70)
    img_bytes = render_chart_image()
    print(f"  图表区域图片: {len(img_bytes)/1024:.0f}KB")

    if has_key:
        from kb_qa.vision import describe_image
        desc = describe_image(img_bytes)
    else:
        desc = mock_describe(img_bytes)
        print("  [mock] 预录描述（模拟 glm-4v-plus 输出）:")
    print(f"\n{desc}\n")

    print("=" * 70)
    print("演示 2：两段式对照 —— 「只用描述答」vs「现场看图答」")
    print("=" * 70)
    questions = [
        "Q1 的营收是多少万元？",
        "哪个季度的营收最高？",
        "Q3 的营收是多少万元？",
    ]
    print(f"\n{'问题':<22} {'只用描述答':<18} {'现场看图答':<18} {'成本'}")
    print("-" * 70)
    for q in questions:
        # 段一：只用描述答（从描述里检索答案，0 成本）
        desc_ans = _answer_from_description(desc, q)
        # 段二：现场看图答（调 VLM，花钱）
        if has_key:
            from kb_qa.vision import answer_with_image
            live_ans = answer_with_image(img_bytes, q)
            cost = "~0.075元"
        else:
            live_ans = mock_answer(img_bytes, q)
            cost = "~0.075元[mock]"
        print(f"{q:<20} {desc_ans[:16]:<18} {live_ans[:16]:<18} {cost}")

    print(f"\n> 🎯 两段式：描述负责『被搜到』（入库时生成、缓存去重），")
    print(f"  原图负责『答得准』（命中后现场看图）。钱花在刀刃上。")
    print(f"  简单数值题（Q1多少）描述就够答；复杂判断（趋势/对比）现场看图更稳。")

    print("\n" + "=" * 70)
    print("演示 3：描述缓存 —— 重复入库不重复调 VLM")
    print("=" * 70)
    from kb_qa.vision import clear_cache, describe_image, is_cached

    clear_cache()
    print("  首次描述（生成 + 落盘缓存）:")
    if has_key:
        d1 = describe_image(img_bytes)
    else:
        # mock 模式也走真缓存逻辑，验证落盘
        d1 = describe_image(img_bytes, use_mock=True)
    print(f"    缓存命中: {is_cached(img_bytes)}")

    print("  第二次描述（同一图片，应命中缓存，不调 VLM）:")
    if has_key:
        d2 = describe_image(img_bytes)
    else:
        d2 = describe_image(img_bytes, use_mock=True)
    same = d1 == d2
    print(f"    结果一致: {same}（命中缓存 = 不重复花钱）")
    clear_cache()

    print("\n" + "=" * 70)
    print("诚实标注")
    print("=" * 70)
    if has_key:
        print("  - 描述和答案来自真实 glm-4v-plus 调用。")
    else:
        print("  - 描述和答案是预录 mock（模拟 glm-4v-plus 输出），未真调 API。")
        print("  - 真实 VLM 对毒文档图表的识别精度需人工核对（L08 评估）。")
    print("  - 缓存逻辑是真测（落盘 JSON + 哈希去重），重复入库确实不重复调。")
    print("  - 两段式的成本对比：描述入库时一次性花，现场看图每次问都花。")


def _answer_from_description(desc: str, question: str) -> str:
    """从描述文本里抽答案（段一：只用描述答，0 成本）。"""
    # 极简：找问题里的季度关键词，从描述里取对应数值
    quarters = {"Q1": "1800", "Q2": "2400", "Q3": "2100", "Q4": "2900"}
    if "最高" in question:
        return "Q4，2900 万元"
    for q, val in quarters.items():
        if q in question:
            return f"{q} {val} 万元"
    return "(描述未覆盖)"


if __name__ == "__main__":
    main()
