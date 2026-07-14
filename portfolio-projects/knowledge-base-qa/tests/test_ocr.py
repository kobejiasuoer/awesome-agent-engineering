"""OCR 测试：扫描件三路线 + 置信度路由（本地真跑 RapidOCR，VLM 走 mock/占位）。

测试策略：
    - RapidOCR 本地真跑（毒文档扫描页，离线可复现）
    - VLM 路线测占位行为（无 key 时 raise，L04 实现真逻辑后补）
    - hybrid 路由测置信度判定（mock 低置信度结果验证 needs_vlm）
    - ocr_engine=off 回归（扫描页行为同现状）
不碰真实智谱 API。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kb_qa.ocr import OcrBox, OcrResult, ocr_page, render_page_image

_REPO_ROOT = Path(__file__).resolve().parents[3]
POISON_PDF = _REPO_ROOT / "data" / "multimodal_docs" / "company_briefing.pdf"

pytestmark = pytest.mark.skipif(
    not POISON_PDF.exists(),
    reason="毒文档不存在（先跑 generate_poison_pdf.py）",
)


class TestRenderPageImage:
    """页面渲染为图片（OCR 前置）。"""

    def test_render_returns_png_bytes(self):
        img = render_page_image(POISON_PDF, page_idx=2)  # P3 扫描页
        assert isinstance(img, bytes)
        assert len(img) > 1000  # PNG 至少几 KB
        assert img[:4] == b"\x89PNG"  # PNG 魔数

    def test_render_different_dpi_changes_size(self):
        low = render_page_image(POISON_PDF, 2, dpi=100)
        high = render_page_image(POISON_PDF, 2, dpi=300)
        assert len(high) > len(low)  # 高 dpi 图片更大


class TestRapidOcr:
    """本地 RapidOCR 路线：真跑，验证扫描页能识别。"""

    def test_scan_page_recognizes_key_facts(self):
        """P3 扫描页 OCR 应识别出 4 个关键事实（试用期/竞业/赔偿/通知）。"""
        result = ocr_page(POISON_PDF, page_idx=2, engine="rapidocr")
        assert result is not None
        assert result.engine == "rapidocr"
        text = result.text
        # 4 个杀手事实必须被识别（L00 基线里它们全挂）
        assert "3个月" in text or "试用期" in text
        assert "2年" in text or "竞业" in text or "同业" in text
        assert "3倍" in text or "赔偿" in text
        assert "30天" in text or "书面通知" in text

    def test_ocr_result_has_boxes_with_bbox_and_score(self):
        """OcrResult 的 boxes 应带 bbox（4 元组）和 score（0-1）。"""
        result = ocr_page(POISON_PDF, page_idx=2, engine="rapidocr")
        assert result is not None
        assert len(result.boxes) > 0
        for box in result.boxes:
            assert len(box.bbox) == 4
            assert 0 <= box.score <= 1.0
            assert box.text  # 非空

    def test_ocr_elapsed_is_reasonable(self):
        """本地 OCR 一页应在合理时间内（CPU 环境，首次含模型加载）。"""
        result = ocr_page(POISON_PDF, page_idx=2, engine="rapidocr")
        assert result is not None
        # 首次运行含 ONNX 模型加载，可能 20-30s；后续约 1.6s。阈值给宽松些。
        # 这个测试验证「不挂死」，不是性能基准——真性能数字在 code.py 里打。
        assert result.elapsed_sec < 60.0


class TestHybridRouting:
    """hybrid 路线：置信度路由，低置信度标记 needs_vlm。"""

    def test_high_confidence_does_not_need_vlm(self):
        """构造高置信度结果：avg_score 高 → needs_vlm=False。"""
        result = OcrResult(
            page=3,
            boxes=(
                OcrBox(text="试用期3个月", bbox=(0, 0, 100, 20), score=0.98),
                OcrBox(text="赔偿3倍", bbox=(0, 30, 100, 50), score=0.95),
            ),
            engine="rapidocr",
        )
        assert result.avg_score > 0.7
        assert not result.needs_vlm

    def test_low_confidence_needs_vlm(self):
        """构造低置信度结果：avg_score 低 → needs_vlm=True（建议升级 VLM）。"""
        result = OcrResult(
            page=3,
            boxes=(
                OcrBox(text="模糊文字", bbox=(0, 0, 100, 20), score=0.45),
                OcrBox(text="看不清", bbox=(0, 30, 100, 50), score=0.52),
            ),
            engine="rapidocr",
        )
        assert result.avg_score < 0.7
        assert result.needs_vlm

    def test_hybrid_engine_runs_local_first(self):
        """hybrid 引擎应先跑本地 OCR（不直接调 VLM）。"""
        result = ocr_page(POISON_PDF, page_idx=2, engine="hybrid")
        assert result is not None
        assert result.engine == "rapidocr"  # hybrid 内部先走本地


class TestOcrEngineSwitch:
    """ocr_engine 开关：off 时扫描页抽空（现状回归）。"""

    def test_off_returns_none(self):
        """ocr_engine=off：不做 OCR，返回 None（扫描页 content 保持空）。"""
        result = ocr_page(POISON_PDF, page_idx=2, engine="off")
        assert result is None

    def test_unknown_engine_raises(self):
        """未知 engine 应 raise ValueError（防配置写错静默失败）。"""
        with pytest.raises(ValueError, match="未知 ocr_engine"):
            ocr_page(POISON_PDF, page_idx=2, engine="nonsense")

    def test_vlm_without_key_raises(self, monkeypatch):
        """vlm 路线无 API key 应 raise（提示配 key，不静默 mock）。"""
        from kb_qa.config import settings

        monkeypatch.setattr(settings, "zhipuai_api_key", "")
        with pytest.raises(RuntimeError, match="ZHIPUAI_API_KEY"):
            ocr_page(POISON_PDF, page_idx=2, engine="vlm")


class TestOcrResultText:
    """OcrResult.text 的阅读顺序排序。"""

    def test_text_sorted_by_y_coordinate(self):
        """text 应按 y 坐标从上到下排序（保持阅读顺序）。"""
        result = OcrResult(
            page=1,
            boxes=(
                OcrBox(text="第三行", bbox=(0, 60, 100, 70), score=0.9),
                OcrBox(text="第一行", bbox=(0, 10, 100, 20), score=0.9),
                OcrBox(text="第二行", bbox=(0, 35, 100, 45), score=0.9),
            ),
        )
        assert result.text == "第一行\n第二行\n第三行"

    def test_empty_boxes_text_is_empty(self):
        result = OcrResult(page=1, boxes=())
        assert result.text == ""
        assert result.avg_score == 0.0
