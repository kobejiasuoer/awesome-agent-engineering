"""扫描件 OCR：给 image 元素装上眼睛（doc-intelligence L03）。

三条路线（成本-精度主线在此）：
    off      —— 不做 OCR（现状），扫描页抽空（config.ocr_engine 默认值）
    rapidocr —— 本地 RapidOCR：免费、快、离线，复杂版面/低质扫描弱
    vlm      —— glm-4v-plus 直读：版面理解强、按图计费（需 API key）
    hybrid   —— 置信度路由：先本地 OCR，低置信度页升级 VLM（本课推荐）

核心设计：OCR 结果带 bbox（每个识别块有自己的坐标），L06 区域引用靠它。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF：渲染页面为图片

OCREngine = Literal["off", "rapidocr", "vlm", "hybrid"]

# 置信度路由阈值：低于此分数的页/块标记「建议升级 VLM」
# 调参依据：毒文档扫描页 RapidOCR 结果，正文行 0.97+、短片段（如「一、」）0.58。
# 0.7 是经验平衡：高于此本地 OCR 通常够准；低于此可能识别错（印章遮挡/模糊）。
_LOW_CONFIDENCE_THRESHOLD = 0.7


@dataclass(frozen=True)
class OcrBox:
    """OCR 识别出的一个文本块（带坐标和置信度）。

    bbox 是页面坐标系（和 Element.bbox 一致），L06 区域引用溯源靠它。
    score 是 OCR 引擎给的置信度，hybrid 路由用它判是否升级 VLM。
    """

    text: str
    bbox: tuple[float, float, float, float]
    score: float


@dataclass(frozen=True)
class OcrResult:
    """一页的 OCR 结果（不可变）。

    boxes 是识别到的所有文本块；avg_score 是平均置信度；
    needs_vlm 是 hybrid 路由的判定（avg_score 低 → 建议升级 VLM）。
    """

    page: int
    boxes: tuple[OcrBox, ...] = field(default_factory=tuple)
    engine: str = "rapidocr"
    elapsed_sec: float = 0.0

    @property
    def text(self) -> str:
        """拼成纯文本（按 y 坐标从上到下排序，保持阅读顺序）。"""
        sorted_boxes = sorted(self.boxes, key=lambda b: (b.bbox[1], b.bbox[0]))
        return "\n".join(b.text for b in sorted_boxes if b.text)

    @property
    def avg_score(self) -> float:
        if not self.boxes:
            return 0.0
        return sum(b.score for b in self.boxes) / len(self.boxes)

    @property
    def needs_vlm(self) -> bool:
        """hybrid 路由：平均置信度低于阈值 → 建议升级 VLM。"""
        return 0 < self.avg_score < _LOW_CONFIDENCE_THRESHOLD

    @property
    def low_confidence_ratio(self) -> float:
        """低置信度块占比（诊断用）。"""
        if not self.boxes:
            return 0.0
        low = sum(1 for b in self.boxes if b.score < _LOW_CONFIDENCE_THRESHOLD)
        return low / len(self.boxes)


# ══════════════════════════════════════════════════════════════════
# 1. 渲染页面为图片（PyMuPDF，OCR 的前置）
# ══════════════════════════════════════════════════════════════════
def render_page_image(pdf_path: str | Path, page_idx: int, dpi: int = 200) -> bytes:
    """把 PDF 指定页渲染成 PNG bytes（OCR 引擎的输入）。

    dpi 越高越准但越慢：150 够清晰且快、200 平衡、300 最准但慢。
    本课默认 200（毒文档扫描页此 dpi 下 RapidOCR 准确率 >95%）。
    """
    doc = fitz.open(str(pdf_path))
    page = doc[page_idx]
    pix = page.get_pixmap(dpi=dpi)
    doc.close()
    return pix.tobytes("png")


# ══════════════════════════════════════════════════════════════════
# 2. 本地 OCR：RapidOCR（免费、快、离线）
# ══════════════════════════════════════════════════════════════════
def ocr_with_rapidocr(image_bytes: bytes, page: int = 0) -> OcrResult:
    """用 RapidOCR 识别图片，返回带 bbox + 置信度的 OcrResult。

    RapidOCR 返回 [[box, text, score], ...]，box 是 4 个点的多边形。
    这里把多边形转成矩形 bbox（取 min/max），和 Element.bbox 统一坐标系。
    """
    from rapidocr_onnxruntime import RapidOCR  # 延迟导入：ocr_engine=off 时不加载

    ocr = RapidOCR()
    result, elapse = ocr(image_bytes)
    boxes: list[OcrBox] = []
    if result:
        for item in result:
            # item = [box_points, text, score]
            box_points, text, score = item[0], item[1], item[2]
            # box_points 是 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] 四点多边形
            xs = [p[0] for p in box_points]
            ys = [p[1] for p in box_points]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            boxes.append(OcrBox(text=text, bbox=bbox, score=float(score)))
    total_elapse = sum(elapse) if elapse else 0.0
    return OcrResult(page=page, boxes=tuple(boxes), engine="rapidocr", elapsed_sec=total_elapse)


# ══════════════════════════════════════════════════════════════════
# 3. VLM 直读：glm-4v-plus（需 API key，L04 实现 vision.py 后复用）
# ══════════════════════════════════════════════════════════════════
def ocr_with_vlm(image_bytes: bytes, page: int = 0) -> OcrResult:
    """用 glm-4v-plus 直读扫描页。

    L04 会实现完整的 vision.py（describe_image / answer_with_image），
    这里先给占位：如果没 API key 就 raise，让调用方走 mock 路径。
    真实场景下 VLM 对复杂版面（印章遮挡、表格线干扰）比本地 OCR 强。
    """
    from .config import settings

    if not settings.zhipuai_api_key:
        raise RuntimeError(
            "ocr_with_vlm 需要 ZHIPUAI_API_KEY（glm-4v-plus 按图计费）。"
            "教学演示用 mock，真实落地配 key。"
        )
    # 真实实现接 L04 的 vision.py（此处 L03 先占位，避免循环依赖）
    # VLM 直读不返回逐块 bbox/score，这里把整页当一个 box，score 给 1.0（VLM 无置信度概念）
    # L04 的 describe_image 会做更精细的结构化提取
    raise NotImplementedError(
        "VLM OCR 在 L04 的 vision.py 实现。L03 的 code.py 用 mock 演示此路线的成本画像。"
    )


# ══════════════════════════════════════════════════════════════════
# 4. 统一入口：按 config.ocr_engine 路由
# ══════════════════════════════════════════════════════════════════
def ocr_page(
    pdf_path: str | Path, page_idx: int, engine: str | None = None
) -> OcrResult | None:
    """对 PDF 指定页跑 OCR，按 engine 路由。

    engine=None 时读 config.ocr_engine。
    off → 返回 None（扫描页抽空，行为同现状）。
    hybrid → 先 RapidOCR，低置信度页标记 needs_vlm=True（是否真升级由调用方决定）。
    """
    from .config import settings

    engine = engine or settings.ocr_engine
    if engine == "off":
        return None  # 不做 OCR，扫描页 content 为空（现状）

    image_bytes = render_page_image(pdf_path, page_idx)
    page_num = page_idx + 1

    if engine == "rapidocr":
        return ocr_with_rapidocr(image_bytes, page=page_num)
    elif engine == "vlm":
        return ocr_with_vlm(image_bytes, page=page_num)
    elif engine == "hybrid":
        # 置信度路由：先本地 OCR，低置信度标记升级
        local = ocr_with_rapidocr(image_bytes, page=page_num)
        if local.needs_vlm:
            # 低置信度：标记建议升级 VLM（但不自动调，成本控制由调用方决定）
            # 这里返回本地结果 + needs_vlm=True，调用方（service.py）按预算决定升不升
            return local  # needs_vlm 属性已自动 True
        return local
    else:
        raise ValueError(f"未知 ocr_engine: {engine}（应为 off/rapidocr/vlm/hybrid）")
