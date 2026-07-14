# Lesson 02 练习

> 改 `code.py` 和 `src/kb_qa/doc_parser.py` 里的代码，运行 `python code.py` 观察变化。本课依赖 pdfplumber（venv 已装），毒文档在 `data/multimodal_docs/`。

---

## 练习 1：构造一个「套娃合并表」，看 markdown 和 HTML 的分歧

现在的薪酬表只有一层合并（「薪酬」跨 2 列）。构造更毒的——两层合并，看 markdown 什么时候不够用。

在 `generate_poison_pdf.py` 的 `make_table_page` 里，把表头再加一层：让「薪酬」和「绩效」再被一个更大的「待遇」表头合并：

```python
# 表头改成两层合并：
# 第 0 行：| 待遇（跨4列）                |
# 第 1 行：| 职级 | 薪酬（跨2列） | 绩效（跨1列）|
# 第 2 行：|      | 基本  | 津贴  | 范围       |
```

重新生成 PDF，跑 `code.py`，看 markdown 和 HTML 的输出差异。

**思考**：markdown 还能正确表达两层合并吗？——**不能**。markdown 的 `||` 空位只能表达「这一格属于左边的合并」，但表达不了「这一格既属于左边的合并、整个上面又被一个大表头盖住」的嵌套关系。HTML 的 `colspan` + `rowspan` 能。**这就是 HTML 存在的价值——复杂合并场景 markdown 力不从心。** 你的真实文档如果都是简单表，markdown 够用；如果有财务报表那种套娃，切 HTML。

---

## 练习 2：调 `table_format` 开关，切换 markdown / HTML

`config.py` 里有 `table_format` 字段（L01 加的，默认 `markdown`）。切换它看 table 元素 content 变化：

```python
# 临时改配置（不改 .env，直接 monkeypatch 思路）
from kb_qa.config import settings
settings.table_format = "html"   # 切到 HTML
# 再跑 parse_pdf
```

验证：跑 `parse_pdf(毒文档)`，看 table 元素的 content 是不是变成了带 `<table><tr><td colspan="2">` 的 HTML。

**思考**：为什么把这个做成配置项而不是写死 markdown？——因为不同文档集的表格复杂度不同。**配置化的本质是「把选型决策延迟到部署时」**：开发时两种都实现，部署时按你的数据特点选。这和 ops-L12 的「成本-质量方法论」一脉相承：没有 universally 最优的表示，只有适合你数据的表示。

---

## 练习 3（设计实验）：量「无边框表」对 pdfplumber 的影响

这是本课的**设计实验验证**题——自己造一个无边框表，量化 pdfplumber 的局限。

L01 的表格检测靠「线段数 ≥ 6」，但有些表格没有框线（靠对齐分列）。在 `generate_poison_pdf.py` 里造一个无边框表——把 `make_table_page` 里的画线代码注释掉：

```python
# 注释掉所有 draw_line（表格不画框线，纯靠文字对齐）
# for ry in [95, 125, 150, 178, 206, 234, 262]:
#     page.draw_line(...)   ← 注释掉
# for x in xs:
#     page.draw_line(...)   ← 注释掉
```

重新生成，跑 L01 的 `code.py`（演示 1），看 P4 还被判为 table 吗？再跑 L02 的 `code.py`，看 pdfplumber 还能抽到表吗？

**思考**：
1. L01 的线段阈值（≥6）判不出无边框表——P4 会退化成 text。这是启发式的固有局限。
2. pdfplumber 的 `find_tables()` 还能抽到吗？——**有时能**（它也看文本对齐），但列多时容易错位。
3. 记录两个数字：无边框表被 L01 认出的概率、被 pdfplumber 正确抽取的概率。**这两个数字就是你文档集是否需要更高级版面模型的依据。** 如果你的表格很多是无边框的，值得考虑 MinerU（版面模型）。

---

## 练习 4（进阶）：实现「跨页表」的自动拼接

真实文档里，一个大表常跨多页。现在 `extract_tables` 是逐页独立抽的，跨页表会被拆成两个。实现自动拼接：

```python
# doc_parser.py 加一个函数：
def extract_tables_merged(pdf_path):
    """抽表 + 跨页拼接：相邻页的表如果列数相同，判为同一表的延续，拼起来。"""
    tables = extract_tables(pdf_path)
    merged = []
    for t in tables:
        if merged and len(t[0]) == len(merged[-1][0]):  # 列数相同 → 可能是延续
            # 拼接：去掉重复表头（延续页的第一行如果是表头就跳过）
            merged[-1].extend(t[1:] if _is_header(t[0]) else t)
        else:
            merged.append(t)
    return merged
```

**思考**：跨页拼接的判据是什么？——**列数相同 + 延续页第一行像表头**。但这不完美（两个不同的表恰好列数相同会误拼）。更可靠的做法是看 pdfplumber 给的 `table.bbox` 的 y 坐标——如果上一页的表底部接近页底、下一页的表顶部接近页顶，大概率是跨页延续。**工程里没有完美的启发式，只有「误拼率可接受」的权衡。** 你的文档集跨页表多吗？多的话值得做自动拼接；少的话手动核对更省心。

---

## ✅ 完成本课后，你应该能回答

1. 表格被 `get_text()` 抽成串行文本后，丢失了什么关键信息？（行×列的二维对应）
2. pdfplumber 怎么表达合并单元格？空串 `""` 在这里承载什么语义？
3. markdown / HTML / 串行 三种表示的准确率和字符成本分别是多少？本课为什么默认 markdown？
4. 什么场景下 HTML 比 markdown 值得？（复杂合并、套娃 rowspan/colspan）
5. 为什么文本层有的表不截图给 VLM？（本地抽取免费 + 检索友好；VLM 只给扫描表）
6. 跨页表为什么必须表头冗余？按行切有什么后果？
7. （落地）kb-qa 的 `parse_pdf` 表格分支现在 content 是什么？`table_format` 怎么切换表示？
