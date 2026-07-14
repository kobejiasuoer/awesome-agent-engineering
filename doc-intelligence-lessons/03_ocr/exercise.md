# Lesson 03 练习

> 改 `code.py` 和 `src/kb_qa/ocr.py` 里的代码，运行 `python code.py` 观察变化。本课依赖 RapidOCR（venv 已装），毒文档在 `data/multimodal_docs/`。

---

## 练习 1：调 dpi，观察 OCR 准确率和耗时的权衡

`ocr.py` 的 `render_page_image` 默认 dpi=200。调低看准确率、调高看耗时：

```python
# ocr.py
def render_page_image(pdf_path, page_idx, dpi=200):
    # 改成 dpi=100（低分辨率）
    pix = page.get_pixmap(dpi=dpi)
```

在 `code.py` 的演示 2 里临时改成调 100 dpi 渲染，跑 `python code.py`，对比置信度和耗时。

**思考**：100 dpi 下置信度降了多少？有没有识别错的块？——**dpi 太低，字迹模糊，OCR 开始出错**。但 dpi 太高（如 400）耗时翻倍且图片体积暴涨。200 是经验平衡点：字迹清晰 + 耗时可接受。**你的扫描件质量越差，越需要高 dpi 补偿，但代价是速度。** 这个权衡在 L08 的成本评估里要量化。

---

## 练习 2：调置信度阈值，观察 hybrid 路由行为

`ocr.py` 顶部有 `_LOW_CONFIDENCE_THRESHOLD = 0.7`。调高它看路由变化：

```python
# ocr.py
_LOW_CONFIDENCE_THRESHOLD = 0.95   # 改成 0.95（严格）
```

跑 `code.py` 演示 4（hybrid），看毒文档扫描页（avg_score 0.946）的路由结果变化。

**思考**：阈值改成 0.95 后，avg_score 0.946 < 0.95 → needs_vlm=True → 建议升级 VLM。这意味着**每页都要花 0.075 元**。阈值定在哪是成本-精度的权衡：
- 阈值低（0.5）：省钱，但低质量识别可能漏网（精度损失）
- 阈值高（0.95）：保精度，但大部分页都升级（成本飙升）
- 0.7 是经验值，**你的文档集需要重新校准**——跑 50 页，人工核对，找「识别开始出错的边界」。

---

## 练习 3（设计实验）：构造一个「模糊扫描页」，触发 VLM 升级

这是本课的**设计实验验证**题——亲手造一个本地 OCR 搞不定的场景。

在 `generate_poison_pdf.py` 里，给扫描页加点「噪声」模拟低质扫描——降低渲染 dpi 再加点模糊：

```python
# make_scan_page 里，把 dpi 降低 + 渲染后加高斯模糊（模拟传真件质量）
pix = src.get_pixmap(dpi=72)   # 极低 dpi，模拟传真/老扫描件
# 或者用 PIL 加模糊：
from PIL import Image, ImageFilter
import io
img = Image.open(io.BytesIO(pix.tobytes("png")))
img = img.filter(ImageFilter.GaussianBlur(radius=1.5))  # 加模糊
```

重新生成 PDF，跑 `code.py` 演示 2，看本地 OCR 的置信度——应该明显下降。

**思考**：
1. 模糊后 avg_score 降到多少？有没有识别错的字？（记录具体数字）
2. 此时 hybrid 路由会不会标记 needs_vlm？（如果 < 0.7 就会）
3. **这就是 hybrid 路由的价值证明**：清晰页白嫖本地、模糊页升级 VLM。把模糊页和清晰页的 OCR 结果对比，量化「本地 vs VLM」在低质扫描上的精度差。

---

## 练习 4（进阶）：实现「印章遮挡」场景的 VLM 优先路由

真实扫描件常有红章盖在文字上。本地 OCR 会把印章当背景，识别率暴跌。实现一个「检测到印章就跳过本地、直接 VLM」的智能路由：

```python
# ocr.py 加一个启发式：
def _has_red_stamp(image_bytes: bytes) -> bool:
    """检测图片里是否有大面积红色（印章）。"""
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # 统计红色像素占比（R>150 且 G<100 且 B<100）
    pixels = list(img.getdata())
    red_count = sum(1 for r, g, b in pixels if r > 150 and g < 100 and b < 100)
    return red_count / len(pixels) > 0.01  # 红色占比 > 1%
```

在 `ocr_page` 的 hybrid 分支里：先检印章，有印章直接走 VLM。

**思考**：这个启发式靠谱吗？——**部分靠谱**。红色检测能抓住大部分红章，但也会误判（红色背景、彩色表格）。更可靠的是用 VLM 做版面分析，但那又回到「全 VLM 烧钱」的问题。**工程里多层启发式 + 抽查兜底**比追求单点完美更务实。你的扫描件印章多吗？多的话值得做这个检测；少的话 hybrid 的置信度路由已经够用。

---

## ✅ 完成本课后，你应该能回答

1. 扫描件为什么让 text-only 管线全盲？（无文本层，字在图像像素里）
2. 本地 RapidOCR vs VLM 直读，各自的成本、精度、延迟、离线性？
3. 为什么选 hybrid（置信度路由）而不是全 VLM 或全本地？
4. 置信度阈值 0.7 怎么定的？太高或太低各有什么后果？
5. 印章遮挡/手写体/低质扫描，本地 OCR 为什么弱？VLM 为什么强？
6. OcrBox 为什么要带 bbox 和 score？（bbox 给 L06 溯源，score 给路由判定）
7. （落地）kb-qa 的 `ocr_page` 怎么按 `ocr_engine` 路由？off 时扫描页行为是什么？
