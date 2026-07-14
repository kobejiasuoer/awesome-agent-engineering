"""doc_parser 测试：版面感知解析 + 多模态 ingest 开关（全程本地、零 API）。

用 conftest 的 isolated_store 风格：PDF 用 L00 的毒文档（随课交付、可复现），
不碰真实智谱 API（embedding 走 DeterministicFakeEmbedding）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kb_qa.doc_parser import (
    Element,
    extract_tables,
    parse_pdf,
    summarize,
    table_to_html,
    table_to_markdown,
    table_to_naive,
)

# 毒文档（L00 随课交付）：6 页，含扫描/表格/图表/图文混排
# tests/ → knowledge-base-qa/ → portfolio-projects/ → RAG-test/（仓库根）
_REPO_ROOT = Path(__file__).resolve().parents[3]
POISON_PDF = _REPO_ROOT / "data" / "multimodal_docs" / "company_briefing.pdf"


# ── 需要毒文档；CI 无该文件时跳过而非报错（保持测试套件可移植） ──
pytestmark = pytest.mark.skipif(
    not POISON_PDF.exists(),
    reason="毒文档 data/multimodal_docs/company_briefing.pdf 不存在（先跑 generate_poison_pdf.py）",
)


class TestParsePdf:
    """parse_pdf 的分类路由：把 PDF 拆成 text/table/image 三类元素。"""

    def test_returns_elements_with_required_fields(self):
        """每个 Element 必带 type/content/page/bbox/source（L06 溯源的数据底座）。"""
        elements = parse_pdf(POISON_PDF)
        assert len(elements) > 0
        for el in elements:
            assert el.type in ("text", "table", "image")
            assert isinstance(el.page, int) and el.page >= 1
            assert len(el.bbox) == 4  # (x0, y0, x1, y1)
            assert el.source == "company_briefing.pdf"

    def test_scan_page_detected_as_image(self):
        """P3 扫描页（无文本层）应被识别为 image 元素而非空 text（L00 失败模式的起点）。"""
        elements = parse_pdf(POISON_PDF)
        p3_elements = [e for e in elements if e.page == 3]
        assert len(p3_elements) >= 1
        # 扫描页整页是图，应为 image 类型
        assert any(e.type == "image" for e in p3_elements)
        # 且不应有内容为空的 text 元素（否则说明分类漏了）
        empty_text_on_p3 = [e for e in p3_elements if e.type == "text" and not e.content]
        assert empty_text_on_p3 == []

    def test_table_page_detected_as_table(self):
        """P4 薪酬表（有交叉直线）应被识别为 table 元素（L02 结构化的前置）。"""
        elements = parse_pdf(POISON_PDF)
        p4_tables = [e for e in elements if e.page == 4 and e.type == "table"]
        assert len(p4_tables) == 1
        # 表格 content 暂存串行文本（含数字，但结构丢失——L02 升级）
        assert "12000" in p4_tables[0].content or "P3" in p4_tables[0].content

    def test_chart_page_has_image_element(self):
        """P5 图表页的 matplotlib 图应被识别为 image 元素（L04 现场看图的前置）。"""
        elements = parse_pdf(POISON_PDF)
        p5_images = [e for e in elements if e.page == 5 and e.type == "image"]
        assert len(p5_images) >= 1

    def test_text_blocks_carry_precise_bbox(self):
        """纯文本页的 text 元素应有精确 bbox（非整页），L06 区域引用靠它。"""
        elements = parse_pdf(POISON_PDF)
        p1_texts = [e for e in elements if e.page == 1 and e.type == "text"]
        assert len(p1_texts) >= 3  # P1 公司简介有多行
        # 每个 text block 的 bbox 应是局部矩形，不是整页 (0,0,595,842)
        for el in p1_texts:
            assert el.bbox[2] - el.bbox[0] < 595  # 宽度小于页宽
            assert el.bbox[3] - el.bbox[1] < 842  # 高度小于页高

    def test_summarize_counts_by_type(self):
        """summarize 报告的三类计数应与元素流一致。"""
        elements = parse_pdf(POISON_PDF)
        rep = summarize(elements)
        assert rep.pages == 6
        assert rep.text_count + rep.table_count + rep.image_count == len(elements)
        assert rep.text_count > 0  # 纯文本页正常抽出
        assert rep.image_count >= 2  # 扫描页 + 图表 + 混排图
        assert rep.table_count == 1

    def test_element_to_metadata_serializes_bbox(self):
        """to_metadata 把 bbox 序列化成字符串（Chroma metadata 不收 tuple）。"""
        el = Element(type="text", content="x", page=3, bbox=(1.0, 2.0, 3.0, 4.0), source="a.pdf")
        meta = el.to_metadata()
        assert meta["page"] == 3
        assert meta["element_type"] == "text"
        assert isinstance(meta["bbox"], str)
        assert meta["source"] == "a.pdf"

    def test_table_element_carries_structured_content(self):
        """L02：table 元素 content 是 markdown（不再串行），行列对应保留。"""
        elements = parse_pdf(POISON_PDF)
        p4_tables = [e for e in elements if e.page == 4 and e.type == "table"]
        assert len(p4_tables) == 1
        content = p4_tables[0].content
        # markdown 表格特征：有 | 分隔
        assert "|" in content
        # 行列对应保留：P5 和它的基本工资 22000 应该在同一行
        for line in content.split("\n"):
            if "P5" in line:
                assert "22000" in line  # 同行 = 结构保留（L00 串行化时做不到）


class TestTableRepresentation:
    """L02 表格三种表示：markdown / HTML / 串行，对照实验的基础。"""

    # 薪酬表的二维数据（模拟 pdfplumber 抽取结果，含合并表头的空位）
    SAMPLE_ROWS = [
        ["职级", "薪酬（元/月）", "", "绩效系数"],
        ["", "基本工资", "岗位津贴", "范围"],
        ["P3", "12000", "3000", "0.8 - 1.2"],
        ["P5", "22000", "6000", "1.0 - 1.5"],
    ]

    def test_markdown_preserves_row_column_association(self):
        """markdown：P5 的基本工资 22000 和 P5 在同一行（结构保留）。"""
        md = table_to_markdown(self.SAMPLE_ROWS)
        lines = md.split("\n")
        # 找到 P5 所在行
        p5_line = next(line for line in lines if "P5" in line)
        assert "22000" in p5_line  # 同行 = 列对应保留
        assert "6000" in p5_line   # 岗位津贴也在同行

    def test_html_emits_colspan_for_merged_cells(self):
        """HTML：合并单元格（薪酬跨 2 列）应输出 colspan="2"。"""
        html = table_to_html(self.SAMPLE_ROWS)
        assert "<table>" in html and "</table>" in html
        # 「薪酬（元/月）」跨 2 列 → 应有 colspan="2"
        assert 'colspan="2"' in html

    def test_naive_loses_structure(self):
        """串行（现状）：P5 和 22000 被打散，无法判断列对应。"""
        naive = table_to_naive(self.SAMPLE_ROWS)
        # 串行化后每个值单独一行，P5 和 22000 不在同一「行」
        lines = naive.split("\n")
        p5_line = next((i for i, l in enumerate(lines) if l == "P5"), -1)
        idx_22000 = next((i for i, l in enumerate(lines) if l == "22000"), -1)
        # 它们不相邻（中间隔着 6000 等其他列值），证明结构丢失
        assert p5_line != idx_22000

    def test_markdown_smaller_than_html(self):
        """成本对比：markdown 字符数 < HTML（合并单元格场景）。"""
        md = table_to_markdown(self.SAMPLE_ROWS)
        html = table_to_html(self.SAMPLE_ROWS)
        assert len(md) < len(html)

    def test_extract_tables_from_poison_pdf(self):
        """pdfplumber 能从毒文档抽出薪酬表的二维结构。"""
        tables = extract_tables(POISON_PDF)
        assert len(tables) >= 1
        # 第一个表应包含 P5 / 22000 等
        flat = [c for row in tables[0] for c in row]
        assert "P5" in flat
        assert "22000" in flat


class TestIngestMultimodalSwitch:
    """多模态 ingest 开关：off 时 PDF 不入库，on 时 PDF 走版面感知解析。"""

    def test_switch_off_ignores_pdf(self, isolated_store: Path, monkeypatch):
        """enable_multimodal_ingest=False（默认）：目录里有 PDF 也不入库，行为同现状。"""
        import kb_qa.ingest as ingest_mod

        monkeypatch.setattr(ingest_mod.settings, "enable_multimodal_ingest", False)
        # 放一个 PDF 进 docs 目录
        (isolated_store / "a.md").write_text("# A\n内容A", encoding="utf-8")
        (isolated_store / "poison.pdf").write_bytes(POISON_PDF.read_bytes())

        report = ingest_mod.ingest_directory(isolated_store)
        # PDF 不应出现在 added_files（开关 off 只认 md/txt）
        assert "poison.pdf" not in report.added_files
        assert "a.md" in report.added_files

    def test_switch_on_ingests_pdf_with_element_metadata(
        self, isolated_store: Path, monkeypatch
    ):
        """enable_multimodal_ingest=True：PDF 入库，chunk 带 page/element_type metadata。"""
        import kb_qa.ingest as ingest_mod

        monkeypatch.setattr(ingest_mod.settings, "enable_multimodal_ingest", True)
        (isolated_store / "poison.pdf").write_bytes(POISON_PDF.read_bytes())

        report = ingest_mod.ingest_directory(isolated_store)
        assert "poison.pdf" in report.added_files
        assert report.added_chunks > 0

        # 从库里读回，验证 metadata 带多模态字段
        vs = ingest_mod.get_vectorstore()
        data = vs._collection.get(where={"source": "poison.pdf"}, include=["metadatas"])
        metas = data.get("metadatas") or []
        assert len(metas) > 0
        # 至少有一个 chunk 带 page 和 element_type（L06 引用溯源依赖）
        has_multimodal_meta = any("page" in m and "element_type" in m for m in metas)
        assert has_multimodal_meta
        # 空内容的 image 元素不应入库（OCR/描述未启用时跳过）
        docs_data = vs._collection.get(where={"source": "poison.pdf"}, include=["documents"])
        for doc_text in docs_data.get("documents") or []:
            assert doc_text  # 不该有空字符串 chunk

    def test_switch_on_idempotent_rerun(self, isolated_store: Path, monkeypatch):
        """多模态入库幂等：重跑同一 PDF，第二次应 skip（hash 没变）。"""
        import kb_qa.ingest as ingest_mod

        monkeypatch.setattr(ingest_mod.settings, "enable_multimodal_ingest", True)
        (isolated_store / "poison.pdf").write_bytes(POISON_PDF.read_bytes())

        first = ingest_mod.ingest_directory(isolated_store)
        assert "poison.pdf" in first.added_files
        first_chunks = first.total_chunks

        second = ingest_mod.ingest_directory(isolated_store)
        assert "poison.pdf" in second.skipped_files
        assert second.added_chunks == 0
        assert second.total_chunks == first_chunks  # 没重复入库
