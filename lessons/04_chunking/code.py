"""
Lesson 04 — 文档处理：加载与切块 (Chunking)
============================================
本脚本让你"看见"不同切块策略的差异：
    ① 加载一份真实 Markdown 文档
    ② 用 chunk_size = 200 / 500 / 1000 分别切，对比结果
    ③ 演示 RecursiveCharacterTextSplitter（推荐切法）+ overlap 的作用

运行：python lessons/04_chunking/code.py
（本课不调用大模型 API，纯本地切分，不花钱）
"""
from __future__ import annotations

import os

from langchain_text_splitters import RecursiveCharacterTextSplitter

# 示例文档路径（第 1 课创建的员工手册）
DOC_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "sample_docs", "employee_handbook.md"
)


def load_document() -> str:
    """读取 Markdown 文档的纯文本。"""
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()


def show_stats(label: str, chunks: list[str]):
    """打印一批切块的统计信息。"""
    lengths = [len(c) for c in chunks]
    print(f"  块数：{len(chunks)}")
    print(f"  最短/最长/平均字符数：{min(lengths)} / {max(lengths)} / {sum(lengths)//len(lengths)}")


def section_compare_chunk_sizes(text: str):
    """第②部分：对比 chunk_size = 200 / 500 / 1000 的切块结果。"""
    print("\n" + "═" * 60)
    print("② 不同 chunk_size 的切块对比")
    print("═" * 60)

    for size in [200, 500, 1000]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=size,
            chunk_overlap=0,  # 先不加重叠，纯粹看 size 的影响
            separators=["\n\n", "\n", "。", "；", "，", " ", ""],
        )
        chunks = splitter.split_text(text)
        print(f"\n【chunk_size={size}】")
        show_stats(f"size={size}", chunks)
        # 打印前 3 块让你直观感受
        print("  前 3 块预览：")
        for i, c in enumerate(chunks[:3], 1):
            preview = c.replace("\n", " ")[:70]
            print(f"    [{i}] ({len(c)}字) {preview}...")

    print("\n👉 观察：")
    print("  - size=200：块很碎，很多半句话，语义不完整")
    print("  - size=1000：块太大，一块里混了好几个主题（请假+报销+远程）")
    print("  - size=500：相对均衡，每块基本是一个完整主题")


def section_recursive_with_overlap(text: str):
    """第③部分：推荐的切法——递归切分 + overlap。"""
    print("\n" + "═" * 60)
    print("③ 推荐切法：RecursiveCharacterTextSplitter + overlap")
    print("═" * 60)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=80,  # 重叠 80 字符，兜住边界信息
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )
    chunks = splitter.split_text(text)

    print(f"\n配置：chunk_size=500, chunk_overlap=80")
    show_stats("推荐切法", chunks)

    print("\n所有切块内容：")
    for i, c in enumerate(chunks, 1):
        print(f"\n  ── 块 {i} ({len(c)} 字) ──")
        # 缩进显示，便于阅读
        for line in c.strip().split("\n"):
            print(f"    {line}")

    print("\n👉 观察：每块基本是一个完整主题（工作时间/请假/报销/远程/福利）")
    print("  没有从句子中间劈断。这正是 chunk_overlap + 语义分隔符的效果。")


def section_explain_separators():
    """补充：解释 separators 优先级的作用。"""
    print("\n" + "═" * 60)
    print("④ 分隔符优先级（separators）解释")
    print("═" * 60)
    print("""
切分器按这个优先级尝试切分（前面的优先）：

    ["\\n\\n", "\\n", "。", "；", "，", " ", ""]

    \\n\\n（段落）> \\n（换行）> 。(句号) > ；(分号) > ，(逗号) > 空格 > 字符

工作原理：
  1. 先尝试用 \\n\\n（段落）切，如果切出来的块都 ≤ chunk_size，完成
  2. 如果某块还是太长，对【那一块】降级用 \\n 切
  3. 还太长？再降级用 。切……直到块够小

好处：尽量在"语义边界"（段落/句子）处切，避免劈断句子。
""")


def main():
    print("=" * 60)
    print("Lesson 04 — 文档处理：加载与切块 (Chunking)")
    print("=" * 60)

    # ① 加载文档
    print("\n① 加载文档")
    text = load_document()
    print(f"  文档：{os.path.basename(DOC_PATH)}")
    print(f"  总字符数：{len(text)}")

    # ② 对比 chunk_size
    section_compare_chunk_sizes(text)

    # ③ 推荐切法
    section_recursive_with_overlap(text)

    # ④ 分隔符解释
    section_explain_separators()

    print("\n" + "=" * 60)
    print("完成！切块的核心：在语义边界处切，每块是一个完整主题。")
    print("下一步（Lesson 05）会把这些块检索出来，拼成 prompt。")
    print("=" * 60)


if __name__ == "__main__":
    main()
