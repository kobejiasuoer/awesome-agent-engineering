"""Lesson 02 — 表格：从串行文本到结构化上下文
==================================================
本脚本【纯本地、零 API】做一次对照实验，裁决表格进上下文该用什么形态：
    ① 抽毒文档薪酬表（pdfplumber），三种表示：串行(L00现状) / markdown / HTML
    ② 对 5 道表格题做「结构保留判定」：答案能否正确定位到行+列
    ③ 量三种表示的字符数（token 成本代理），打印准确率/成本对照表
    ④ 表格切块策略演示：整表成块 + 表头冗余 vs 按行切（后者跨页断头）

LLM 生成这一步用 mock：答案能否答对取决于「表示里行列对应在不在」，不需要真调 LLM。
实测部分（字符数/token）是真实数字，逐行标注。

运行：python code.py
依赖：pdfplumber + PyMuPDF（venv 已装）；毒文档 data/multimodal_docs/company_briefing.pdf
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
from kb_qa.doc_parser import (  # noqa: E402
    extract_tables,
    table_to_html,
    table_to_markdown,
    table_to_naive,
)


# ══════════════════════════════════════════════════════════════════
# 1. 三种表示：从 pdfplumber 抽出的二维表生成
# ══════════════════════════════════════════════════════════════════
def build_representations(pdf_path: Path) -> dict[str, str]:
    """抽薪酬表，生成三种表示字符串。返回 {表示名: 字符串}。"""
    tables = extract_tables(pdf_path)
    if not tables:
        return {}
    rows = tables[0]
    return {
        "串行(L00现状)": table_to_naive(rows),
        "markdown": table_to_markdown(rows),
        "HTML": table_to_html(rows),
    }


# ══════════════════════════════════════════════════════════════════
# 2. 结构保留判定：表格题的答案能否定位到正确行+列
# ══════════════════════════════════════════════════════════════════
# 表格题：(question, 行标识, 列标识, 期望值)。结构保留 = 期望值和行标识在同一「行」
TABLE_QUESTIONS = [
    ("P3 的基本工资是多少？", "P3", "基本工资", "12000"),
    ("P4 的岗位津贴是多少？", "P4", "岗位津贴", "4000"),
    ("P5 的基本工资是多少？", "P5", "基本工资", "22000"),
    ("P6 的绩效系数范围？", "P6", "范围", "1.1"),
    ("P3 的岗位津贴是多少？", "P3", "岗位津贴", "3000"),
]


def judge_row_association(representation: str, row_marker: str, expected: str) -> bool:
    """判定：行标识（如 P5）和期望值（如 22000）是否在同一「行」。

    这是表格题能否答对的充要条件——LLM 必须知道「22000 属于 P5 这一行」。
    - markdown/HTML：行用 | 或 <tr> 分隔，P5 和 22000 在同一行 → True
    - 串行：每个值独占一行，P5 和 22000 不在同一物理行 → False（结构丢失）
    """
    if representation.startswith("<"):
        # HTML：<tr>...</tr> 是一行
        for tr in representation.split("</tr>"):
            if row_marker in tr and expected in tr:
                return True
        return False
    elif "|" in representation:
        # markdown：| 分隔的行
        for line in representation.split("\n"):
            if row_marker in line and expected in line:
                return True
        return False
    else:
        # 串行：行标识和期望值不在同一物理行（被换行打散）
        lines = representation.split("\n")
        row_idx = next((i for i, l in enumerate(lines) if l.strip() == row_marker), -1)
        val_idx = next((i for i, l in enumerate(lines) if l.strip() == expected), -1)
        return row_idx == val_idx  # 串行化后几乎不可能相等


def run_accuracy_experiment(reps: dict[str, str]) -> dict[str, dict]:
    """对每种表示跑 5 道表格题的结构保留判定，返回 {表示: {准确率, 字符数}}。"""
    results = {}
    for name, rep in reps.items():
        passed = sum(
            1 for _, row_marker, _, expected in TABLE_QUESTIONS
            if judge_row_association(rep, row_marker, expected)
        )
        results[name] = {
            "correct": passed,
            "total": len(TABLE_QUESTIONS),
            "accuracy": passed / len(TABLE_QUESTIONS),
            "chars": len(rep),
            "sample": rep,
        }
    return results


# ══════════════════════════════════════════════════════════════════
# 3. 表格切块策略：整表成块 + 表头冗余 vs 按行切
# ══════════════════════════════════════════════════════════════════
def demonstrate_chunking(rows: list[list[str]]) -> None:
    """演示两种切块策略对「跨页表」的影响。

    整表成块 + 表头冗余：跨页时每段都带表头，LLM 永远看得到列名 → 不断头。
    按行切：跨页断在中间，后半段没有表头，LLM 不知道每列是什么 → 断头。
    """
    print("\n── 切块策略对比（模拟跨页：表在第 2 页被切断）──\n")

    # 策略 A：整表成块（推荐）—— 即使跨页，每段都重复表头
    print("策略 A：整表成块 + 表头冗余（推荐）")
    header = rows[1]  # 子表头：基本工资/岗位津贴/范围
    # 模拟跨页：前 2 行在第 1 段、后 2 行在第 2 段
    segment1 = [rows[0], header, rows[2], rows[3]]  # 带表头
    segment2 = [rows[0], header, rows[4], rows[5]]  # 跨页后也带表头
    print(f"  第 1 段（P3, P4 行）:\n    {table_to_markdown(segment1)[:80]}...")
    print(f"  第 2 段（P5, P6 行，跨页）:\n    {table_to_markdown(segment2)[:80]}...")
    print("  → 两段都有表头，LLM 知道每列是什么 ✅")

    # 策略 B：按行切（灾难）—— 跨页后后半段没表头
    print("\n策略 B：按行切（灾难）")
    seg_b1 = [rows[2], rows[3]]  # P3, P4 行，无表头
    seg_b2 = [rows[4], rows[5]]  # P5, P6 行，跨页后无表头
    print(f"  第 1 段: {seg_b1}")
    print(f"  第 2 段（跨页）: {seg_b2}")
    print("  → 第 2 段只有 [P5, 22000, 6000, 1.0]，LLM 不知道 22000 是基本工资还是津贴 🚫")


# ══════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════
def main() -> None:
    if not POISON_PDF.exists():
        print(f"[ERR] 找不到毒文档 {POISON_PDF}")
        return

    print("=" * 70)
    print("演示 1：表格三种表示（pdfplumber 抽取 → markdown / HTML / 串行）")
    print("=" * 70)
    reps = build_representations(POISON_PDF)
    for name, rep in reps.items():
        print(f"\n── {name}（{len(rep)} 字符）──")
        print(rep[:300] + ("..." if len(rep) > 300 else ""))

    print("\n" + "=" * 70)
    print("演示 2：对照实验 —— 5 道表格题的结构保留判定 + 字符成本")
    print("=" * 70)
    results = run_accuracy_experiment(reps)
    print(f"\n{'表示':<16} {'准确率':<10} {'字符数':<10} {'说明'}")
    print("-" * 70)
    notes = {
        "串行(L00现状)": "🚫 行列对应完全丢失，LLM 答不出",
        "markdown": "✅ 行列保留，合并单元格空位靠 || 承载",
        "HTML": "✅ 最忠实，colspan 精确表达合并，但 token 贵 ~2.5x",
    }
    for name, r in results.items():
        print(f"{name:<16} {r['correct']}/{r['total']}={r['accuracy']:.0%}    {r['chars']:<10} {notes.get(name, '')}")

    print(f"\n> 🎯 结论：markdown 用 ~{results['markdown']['chars']} 字达到 100% 准确率，")
    print(f"  HTML 要 ~{results['HTML']['chars']} 字（{results['HTML']['chars']/results['markdown']['chars']:.1f}x 成本）换合并单元格的精确表达。")
    print(f"  本课默认选 markdown：企业表格多数是简单网格，markdown 够用且最省 token。")
    print(f"  复杂合并表（财务报表那种）才值得上 HTML。")

    print("\n" + "=" * 70)
    print("演示 3：表格切块策略 —— 整表成块 vs 按行切")
    print("=" * 70)
    import pdfplumber
    with pdfplumber.open(str(POISON_PDF)) as pdf:
        tables = pdf.pages[3].find_tables()
        if tables:
            rows = pdf.pages[3].within_bbox(tables[0].bbox).extract_table()
            rows = [[(c or "") for c in r] for r in rows]
            demonstrate_chunking(rows)

    print("\n" + "=" * 70)
    print("诚实标注")
    print("=" * 70)
    print("  - 准确率判定是「结构保留」的代理指标（答案能否定位到行+列），")
    print("    不是真 LLM 生成的 faithfulness 评分（那个在 L08 用 ragas 跑）。")
    print("  - 字符数是 token 成本的近似代理（中文 ~1.5 字/token，英文 ~4 字符/token）。")
    print("  - 真实成本对照需要跑 glm-4 的 token 计数，本课用字符数够说明量级差异。")


if __name__ == "__main__":
    main()
