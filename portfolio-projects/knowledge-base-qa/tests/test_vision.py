"""vision 测试：图表描述 + 两段式消费 + 哈希缓存（全 mock，零 API）。

测试策略：
    - describe_image / answer_with_image 用 use_mock=True（不调真 VLM）
    - 缓存逻辑真测（落盘 JSON + 哈希去重）
    - config.enable_image_caption 开关：off 时图片元素无描述（回归）
不碰真实智谱 API。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kb_qa.vision import (
    _image_hash,
    answer_with_image,
    clear_cache,
    describe_image,
    is_cached,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
POISON_PDF = _REPO_ROOT / "data" / "multimodal_docs" / "company_briefing.pdf"


@pytest.fixture(autouse=True)
def clean_cache():
    """每个测试前后清空缓存，避免相互污染。"""
    clear_cache()
    yield
    clear_cache()


class TestDescribeImage:
    """describe_image：VLM 结构化描述 + 哈希缓存。"""

    def test_mock_describe_returns_text(self):
        """use_mock=True 返回占位描述（不调真 VLM）。"""
        desc = describe_image(b"\x89PNG fake", use_mock=True)
        assert isinstance(desc, str)
        assert len(desc) > 0
        assert "mock" in desc  # 诚实标注

    def test_cache_persists_across_calls(self):
        """重复描述同一图片：第二次命中缓存，不重复调 VLM。"""
        img = b"\x89PNG test image data 1"
        desc1 = describe_image(img, use_mock=True)
        desc2 = describe_image(img, use_mock=True)
        assert desc1 == desc2  # 缓存命中，结果一致
        assert is_cached(img)

    def test_different_images_different_cache(self):
        """不同图片哈希不同，缓存独立。"""
        img1 = b"image1 data"
        img2 = b"image2 data"
        describe_image(img1, use_mock=True)
        describe_image(img2, use_mock=True)
        assert _image_hash(img1) != _image_hash(img2)
        assert is_cached(img1) and is_cached(img2)

    def test_force_refresh_ignores_cache(self):
        """force_refresh=True 忽略缓存强制重新描述。"""
        img = b"refresh test"
        desc1 = describe_image(img, use_mock=True)
        # 模拟描述变了（force_refresh 后重新生成）
        desc2 = describe_image(img, use_mock=True, force_refresh=True)
        # mock 模式下描述内容相同，但验证 force_refresh 不报错且仍落盘
        assert is_cached(img)

    def test_cache_files_on_disk(self):
        """缓存确实落盘成 JSON 文件（按哈希命名）。"""
        img = b"disk cache test"
        describe_image(img, use_mock=True)
        from kb_qa.vision import _cache_path

        cache_file = _cache_path(_image_hash(img))
        assert cache_file.exists()
        import json

        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert data["hash"] == _image_hash(img)
        assert "description" in data


class TestAnswerWithImage:
    """answer_with_image：现场看图作答（第二段）。"""

    def test_mock_answer_returns_text(self):
        """use_mock=True 返回占位答案（不调真 VLM）。"""
        ans = answer_with_image(b"\x89PNG fake", "Q3营收多少", use_mock=True)
        assert isinstance(ans, str)
        assert "Q3营收多少" in ans  # mock 回显问题

    def test_answer_does_not_cache(self):
        """现场看图不作答缓存（每问都可能不同，缓存无意义）。"""
        img = b"no cache answer"
        answer_with_image(img, "问题1", use_mock=True)
        # answer_with_image 不该产生描述缓存
        assert not is_cached(img)


class TestImageHash:
    """图片哈希：内容相同则哈希相同（去重依据）。"""

    def test_same_content_same_hash(self):
        assert _image_hash(b"abc") == _image_hash(b"abc")

    def test_different_content_different_hash(self):
        assert _image_hash(b"abc") != _image_hash(b"abd")

    def test_empty_bytes_has_hash(self):
        h = _image_hash(b"")
        assert isinstance(h, str) and len(h) == 32  # MD5 hex


class TestCaptionSwitch:
    """enable_image_caption 开关：off 时图片元素无描述（回归）。"""

    def test_caption_off_image_element_empty(self, monkeypatch):
        """enable_image_caption=False：图表页 image 元素 content 为空（现状）。"""
        from kb_qa.config import settings
        from kb_qa.doc_parser import parse_pdf

        monkeypatch.setattr(settings, "enable_image_caption", False)
        monkeypatch.setattr(settings, "enable_multimodal_ingest", True)
        if POISON_PDF.exists():
            elements = parse_pdf(POISON_PDF)
            # P5 图表页的 image 元素 content 应为空
            p5_images = [e for e in elements if e.page == 5 and e.type == "image"]
            for el in p5_images:
                assert el.content == ""  # 描述未启用，空

    def test_caption_on_image_element_has_description(self, monkeypatch):
        """enable_image_caption=True：图表页 image 元素有 mock 描述。"""
        from kb_qa.config import settings
        from kb_qa.doc_parser import parse_pdf
        from kb_qa import vision

        monkeypatch.setattr(settings, "enable_image_caption", True)
        # 拦截 describe_image 走 mock（不调真 VLM，也不真写默认缓存目录）
        monkeypatch.setattr(
            vision, "describe_image",
            lambda img_bytes, **kw: "[测试描述] 柱状图 Q1:1800 Q2:2400 Q3:2100 Q4:2900",
        )
        if POISON_PDF.exists():
            elements = parse_pdf(POISON_PDF)
            p5_images = [e for e in elements if e.page == 5 and e.type == "image"]
            assert len(p5_images) >= 1
            for el in p5_images:
                assert el.content  # 非空，有描述
                assert "测试描述" in el.content or "1800" in el.content
