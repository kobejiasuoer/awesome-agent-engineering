# Lesson 02 — 表格：从串行文本到结构化上下文

> 本课目标：**解决表格的抽取与表示——用 pdfplumber 把串行文本升级成结构化的 markdown/HTML，并用对照实验（准确率 + token 成本）裁决哪种表示最划算**。
>
> 学完你能回答面试官那句：**「表格进 RAG 你怎么处理的？直接塞文本不就丢了结构？」**——表格是二维的，串行文本是一维的，降维就丢信息；选什么表示是成本-精度的权衡，我的选型有数字支撑。

---

## 1. 表格三大坑

L01 把表格页认出来了（矢量线段 ≥ 6 条 → table 元素），但 content 还是串行文本。真正抽取表格，有三大坑：

| 坑 | 是什么 | L00 毒文档里的例子 | 后果 |
|---|---|---|---|
| **合并单元格** | 表头跨多列（colspan）或跨多行（rowspan） | 薪酬表「薪酬（元/月）」跨「基本工资」「岗位津贴」两列 | 列归属混乱 |
| **跨页表** | 一个表被分页截断，下半段在下一页 | （真实文档常见，毒文档未构造，exercise 会模拟） | 后半段断头、无表头 |
| **无边框表** | 靠对齐而非框线分列，`get_drawings()` 数不到线 | 财务报表常见 | L01 的线段阈值漏判 |

> 🎯 **核心认知**：表格的本质是**二维结构**（行 × 列），而文本是一维的（串）。任何「把表格转成一维」的操作都是降维，降维就丢信息——丢的是「哪个值属于哪一行哪一列」。L00 基线里表格题 0% 通过，根因就在这：`P5\n22000\n6000` 这串文字，LLM 分不清 22000 是 P5 的基本工资还是岗位津贴。

```
表格降维的灾难（L00 基线复盘）：

   原始表格（二维）：              串行文本（一维，get_text 抽出）：
   ┌──────┬─────────────┐         职级
   │ 职级 │ 基本工资     │         基本工资
   ├──────┼─────────────┤         P3
   │ P3   │ 12000       │         12000
   ├──────┼─────────────┤         P5
   │ P5   │ 22000       │         22000
   └──────┴─────────────┘         → 「P5 的基本工资」？P5 和 22000 的对应丢了！
```

---

## 2. pdfplumber 抽取：拿回二维结构

pdfplumber 基于**文本片段的坐标对齐**判网格——不只看框线（所以无边框表也能抽），比 L01 的「数线段」更可靠：

```python
import pdfplumber
with pdfplumber.open("company_briefing.pdf") as pdf:
    tables = pdf.pages[3].find_tables()
    rows = pdf.pages[3].within_bbox(tables[0].bbox).extract_table()
    # rows = [
    #   ["职级", "薪酬（元/月）", "", "绩效系数"],   ← 合并单元格的延续位是空串
    #   ["", "基本工资", "岗位津贴", "范围"],
    #   ["P3", "12000", "3000", "0.8 - 1.2"],
    #   ["P5", "22000", "6000", "1.0 - 1.5"],
    # ]
```

> 💡 **合并单元格怎么表达？** pdfplumber 把合并单元格的「延续位」填空串 `""`——「薪酬（元/月）」跨 2 列，所以第 2 列是 `""`。这个空串承载了「这一格属于左边的合并」的语义。后面转 markdown/HTML 时，怎么处理这个空串是关键差异。

### pdfplumber 的局限

| 场景 | pdfplumber 表现 |
|---|---|
| 有框线表格 | ✅ 准确（坐标对齐 + 框线双重定位） |
| 无边框表 | 🟡 靠文本对齐，列多时可能错位 |
| 嵌套表（表里有表） | 🚫 扁平化，丢嵌套结构 |
| 图片里的表（扫描表） | 🚫 完全抽不到（要 L03 OCR + 表格识别） |

> 💡 毒文档的薪酬表是有框线的简单网格，pdfplumber 抽得很准。真实文档里遇到扫描表（图里的表），pdfplumber 抽不到——那是 L03 OCR + 表格识别的活，本课只处理「文本层里有」的表。

---

## 3. 方案对比：表格进上下文的三种表示（本课灵魂）

抽到二维 `rows` 后，怎么塞进 LLM 的上下文？三种表示，成本-精度不同。**这不是拍脑袋选的，是对照实验裁决的：**

| 表示 | 怎么做 | 合并单元格 | 字符数（毒文档薪酬表） | 结构保留 |
|---|---|---|---|---|
| **串行文本**（L00 现状） | 所有单元格拍平成一维 | 🚫 完全丢失 | 124 | 🚫 0/5 题 |
| **markdown**（本课默认） | `\|` 分隔行列，空串留空 | 🟡 靠 `\|\|` 空位承载 | 204 | ✅ 5/5 题 |
| **HTML**（最忠实） | `<table><tr><td>` + `colspan` | ✅ 精确 `colspan="2"` | 529 | ✅ 5/5 题 |

### 对照实验结果（code.py 跑出来的真数字）

```
表示            准确率      字符数    说明
串行(L00现状)   0/5=0%     124      🚫 行列对应完全丢失
markdown        5/5=100%   204      ✅ 行列保留，合并空位靠 || 承载
HTML            5/5=100%   529      ✅ 最忠实，但 token 贵 2.6x
```

> 🎯 **本课选 markdown 的理由**：markdown 用 204 字（最省）达到 100% 准确率，HTML 要 529 字（2.6 倍成本）换合并单元格的精确表达。**企业表格多数是简单网格，markdown 够用；只有复杂合并表（财务报表那种 rowspan/colspan 套娃）才值得上 HTML。** config 里 `table_format` 默认 `markdown`，复杂场景一行切到 `html`。

```
选型决策树（成本-精度主线）：

   表格进上下文
       │
       ├── 简单网格（无合并）→ markdown（最省，100% 准确）
       ├── 有合并单元格 ────→ markdown 够用（空位承载，LLM 认得）
       │                      除非合并极复杂（套娃）
       └── 合并极复杂 ───────→ HTML（colspan 精确，2.6x 成本值得）
       
   截图 + VLM 直读？→ 最忠实但最贵（整表一张图丢给 glm-4v），
                      只在「表格本身是扫描图」时才考虑（L03 场景）
```

### 为什么不「整表截图 + VLM 直读」？

这是第四种路线——把表格截图丢给 glm-4v-plus 直接读。理论上最忠实（VLM 直接看图），但：

| 维度 | markdown/HTML | 整表截图 + VLM |
|---|---|---|
| 成本 | 0（本地抽取） | 每表一次 VLM 调用（按图计费） |
| 检索友好 | ✅ 文本能 embedding | 🚫 图片不能直接 embedding（要 L04 描述中转） |
| 精度 | 取决于抽取质量 | 取决于 VLM 读图能力（复杂表可能读错） |
| 适合 | 文本层有的表 | 扫描表、图片表（文本层没有） |

> 💡 **文本层有的表，绝不截图给 VLM**——本地抽取免费且检索友好。截图 + VLM 只在「表格是图片」（扫描件里的表）时才用，那是 L03 OCR 的延伸。**成本-精度主线：能用免费的本地工具，绝不花 VLM 的钱。**

---

## 4. 表格切块策略：整表成块 + 表头冗余

表格抽出来后，怎么切块进向量库？关键原则：**整表一个 chunk，跨页时每段都带表头。**

| 策略 | 怎么切 | 跨页表 | 检索 |
|---|---|---|---|
| **整表成块**（推荐） | 一张表 = 一个 chunk | 每段重复表头 | ✅ 命中整表 |
| **按行切** | 每行或每几行一个 chunk | 后半段断头无表头 | 🚫 命中半截表 |
| **按列切** | 每列一个 chunk | 行对应丢失 | 🚫 完全错误 |

```
跨页表的表头冗余（code.py 演示）：

   原表（跨第 2 页）：
   ┌──────┬────────┐
   │ 职级 │ 基本工资│  ← 表头
   │ P3   │ 12000  │  ── 第 1 页
   │ P4   │ 16000  │
   ╞══════╪════════╡  ── 分页线
   │ P5   │ 22000  │  ── 第 2 页
   │ P6   │ 30000  │
   └──────┴────────┘

   策略 A（整表+表头冗余）：第 2 段也带表头
   第 2 段: | 职级 | 基本工资 |    ← 表头冗余！
           | P5   | 22000    |
           | P6   | 30000    |
   → LLM 知道 22000 是基本工资 ✅

   策略 B（按行切）：第 2 段没表头
   第 2 段: P5, 22000, P6, 30000
   → LLM 不知道 22000 是什么 🚫
```

> 🎯 **表头冗余是跨页表的命根子。** 宁可多花几十 token 重复表头，也不能让后半段断头。这在 kb-qa 的 ingest 里体现为：表格元素**整表一个 Document**（不按行切），metadata 标 `element_type=table`。

---

## 5. 本课代码会做什么

### `code.py`（教学，可独立跑）
- ① pdfplumber 抽薪酬表，生成三种表示（串行/markdown/HTML）
- ② 对照实验：5 道表格题的结构保留判定 + 字符成本对照表
- ③ 切块策略演示：整表成块 + 表头冗余 vs 按行切（模拟跨页）

### 落地到 kb-qa
- `doc_parser.py` 加表格结构化：`extract_tables` + `table_to_markdown` + `table_to_html` + `table_to_naive`
- `parse_pdf` 表格分支升级：content 从串行文本 → markdown（默认）/ HTML（按 `config.table_format`）
- `tests/test_doc_parser.py` 加 `TestTableRepresentation`（6 个测试）

---

## 6. 跑起来

### 教学代码（独立可跑）
```bash
cd doc-intelligence-lessons/02_table
python code.py
```
预期：markdown 5/5 准确 / 204 字符；HTML 5/5 / 529 字符；串行 0/5 / 124 字符。

### 落地验证（kb-qa）
```bash
cd portfolio-projects/knowledge-base-qa
python -m pytest tests/test_doc_parser.py::TestTableRepresentation -q   # 6 passed
python -m pytest -q                                                      # 95 passed
# 验证 table 元素 content 是 markdown：
python -c "
import sys; sys.path.insert(0, 'src')
from kb_qa.doc_parser import parse_pdf
els = parse_pdf('../../data/multimodal_docs/company_briefing.pdf')
t = [e for e in els if e.type=='table'][0]
print(t.content[:100])  # 应是 | 职级 | 薪酬... 的 markdown
"
```

### 验收检查
- [ ] pdfplumber 抽出薪酬表二维结构（含合并单元格的空位）
- [ ] markdown/HTML 都让表格题结构保留（5/5），串行 0/5
- [ ] markdown 字符数 < HTML（成本优势）
- [ ] `config.table_format=html` 时 table 元素 content 变成 HTML
- [ ] 跨页表表头冗余演示：第 2 段也带表头
- [ ] 硬任务表格题 before（L00: 0%）→ after（结构保留判定 100%）

---

## 🎯 面试话术

> 「表格进上下文我做过三种表示的对照实验：串行文本（现状）5 道表格题 0% 结构保留、markdown 100% 用 204 字符、HTML 100% 但要 529 字符（2.6 倍成本）。默认选 markdown——企业表格多数是简单网格，markdown 够用且最省 token；只有复杂合并表才切 HTML。抽取用 pdfplumber（基于坐标对齐判网格，比数线段可靠），整表成块加表头冗余保证跨页不断头。文本层有的表绝不截图给 VLM——本地抽取免费且检索友好，钱花在刀刃上。」

---

## 落地清单

| 文件 | 改动 | 如何验证 |
|---|---|---|
| `src/kb_qa/doc_parser.py` | 加 `extract_tables`/`table_to_markdown`/`table_to_html`/`table_to_naive`；`parse_pdf` 表格分支用结构化 content | `parse_pdf` 的 table 元素 content 是 `\| ... \|` markdown |
| `src/kb_qa/config.py` | `table_format` 字段已加（L01），默认 `markdown` | `settings.table_format == "markdown"` |
| `tests/test_doc_parser.py` | 加 `TestTableRepresentation`（6 测试：markdown/HTML/串行/成本/抽取） | `pytest tests/test_doc_parser.py -q` → 16 passed |

> 📌 **两条主线位置**：本课在**成本-精度主线**上是教科书案例——markdown vs HTML 的 2.6 倍成本差用对照实验量化，选型有数字支撑；在**溯源主线**上，表格元素带 `page`/`bbox`，L06 的「文档 P4·表格」引用 + 区域裁剪图就靠它（整表 bbox 此时是整页，L06 可细化到表格区域）。

下一课 [Lesson 03 — 扫描件：OCR 三路线](../03_ocr/) 给 image 元素装上眼睛——本地 RapidOCR、VLM 直读、置信度混合路由的成本-精度权衡。
