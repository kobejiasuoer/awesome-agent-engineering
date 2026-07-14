# Lesson 03 — 扫描件：OCR 三路线

> 本课目标：**给扫描页装上眼睛——本地 RapidOCR、glm-4v-plus 直读、置信度混合路由三路线，用真实成本-精度数字裁决，最终选 hybrid 作为生产推荐**。
>
> 学完你能回答面试官那句：**「扫描件你怎么处理的？全丢给 GPT-4V 看图不就行了？」**——全 VLM 是烧钱，全本地是赌运气，置信度路由才是工程答案。

---

## 1. 扫描件为什么是盲区（L00 复盘）

L00 基线里扫描题 0/4 全挂——根因是扫描页**没有文本层**：

```
扫描件的诞生：                  text-only 管线的视角：
   纸质文件                       page.get_text()
      │                              │
   扫描仪拍照                        ▼
      │                          返回空串 ""
      ▼                          → 这页的知识等于不存在
   位图嵌入 PDF（无文本层）
```

> 🎯 **核心认知**：扫描件的字在「图像像素」里，不在「文本层」里。`get_text()` 只读文本层，所以抽到空。OCR 的本质是**把图像像素里的字重新识别成文本**——给扫描页「补」上一个文本层。

### 扫描页的判定（L01 的成果）

L01 已经解决了「认出这是扫描页」：文本层字符数 ≈ 0 且有图片 → image 元素。本课解决的是「认出之后怎么办」——给 image 元素的 content 填上识别文本。

---

## 2. 方案对比：三条 OCR 路线（本课灵魂）

| 路线 | 怎么做 | 成本/页 | 精度 | 延迟 | 离线 |
|---|---|---|---|---|---|
| **本地 RapidOCR** | ONNX 模型本地推理 | **0 元** | 🟡 清晰扫描高、复杂版面弱 | ~2.8s | ✅ |
| **VLM 直读** | 截图丢 glm-4v-plus | ~0.075 元 | 🟢 版面理解最强 | ~3s | 🚫 |
| **置信度混合路由**（推荐） | 先本地，低置信升级 VLM | 0-0.075 元 | 🟢 按需升级 | ~2.8s | 部分 |

### 本地 RapidOCR 实测（毒文档扫描页，真跑）

```
识别到 9 个文本块 | 耗时 2.79s | 平均置信度 0.946
  [0.99] 保密与竞业协议（扫描件）
  [1.00] 本页为纸质文件扫描件，以下条款具有同等效力：
  [0.58] ⚠️ 一、                          ← 短片段，低置信
  [0.99] 试用期3个月，试用期工资为转正后基本工资的80%。
  [1.00] 员工在职期间及离职后2年内，不得从事同业竞争业务。
  [1.00] 三、违反保密义务的，赔偿金额为年薪的3倍。
  [0.98] 四、离职需提前30天书面通知，并完成工作交接。
```

> 🎯 **本地 OCR 对清晰扫描够用**：4 个杀手事实全部识别（试用期3个月/2年/3倍/30天），正文行置信度 0.97-1.00。但短片段「一、」只有 0.58——这是置信度路由的触发点。

### VLM 直读的成本画像

```
glm-4v-plus：输入 50 元/百万 token
一页扫描件 200dpi ≈ 1500 image tokens → 单页 ~0.075 元
版面理解：强（印章遮挡/表格线干扰/手写体优于本地 OCR）
延迟：~2-4s/页（API 往返）
```

> 💡 **VLM 的优势在复杂版面**：印章盖在字上、表格线干扰、低质扫描/手写体——这些场景本地 OCR 会识别错，VLM 的版面理解能力强得多。但 **清晰扫描用 VLM 是杀鸡用牛刀**——本地 OCR 免费 + 离线，凭啥每页花 0.075 元？

```
成本-精度决策树（成本-精度主线在此）：

   扫描页进来
       │
       ├── 清晰扫描（高置信度）→ 本地 OCR（免费，够准）
       │
       ├── 模糊/复杂版面     → 本地 OCR 先试
       │       │
       │       └── 置信度 < 0.7 → 升级 VLM（花钱但准）
       │
       └── 印章遮挡/手写体   → 直接 VLM（本地 OCR 大概率挂）
       
   这就是 hybrid 路由：大部分页白嫖本地，少数页才花 VLM 的钱
```

---

## 3. 置信度混合路由（hybrid）：本课推荐

hybrid 的逻辑：**先本地 OCR，低置信度页升级 VLM**。这是成本-精度主线的教科书案例：

```python
def ocr_page(pdf_path, page_idx, engine="hybrid"):
    if engine == "off":
        return None  # 不做 OCR（现状）
    
    image = render_page_image(pdf_path, page_idx)
    
    if engine in ("rapidocr", "hybrid"):
        result = ocr_with_rapidocr(image)  # 先本地
        if engine == "hybrid" and result.needs_vlm:
            # 低置信度 → 标记升级（是否真调 VLM 由调用方按预算决定）
            return result  # needs_vlm=True，service.py 决定升不升
        return result
    
    if engine == "vlm":
        return ocr_with_vlm(image)  # 直接 VLM
```

### 毒文档的路由结果

```
本地 OCR 平均置信度: 0.946 ≥ 0.7
→ ✅ 本地够用，不升级（省钱）
→ 成本: 0 元（而不是 0.075 元）
```

> 🎯 **hybrid 的价值是「按需花钱」**。假设 100 页扫描件，90 页清晰（本地够用）、10 页模糊（需升级）：
> - 全 VLM：100 × 0.075 = **7.5 元**
> - 全本地：0 元，但 10 页模糊的识别错（精度损失）
> - hybrid：10 × 0.075 = **0.75 元**，90 页白嫖 + 10 页升级保精度
>
> **hybrid 用 10% 的成本买到接近全 VLM 的精度。** 这就是工程答案。

### 置信度阈值怎么定？

`_LOW_CONFIDENCE_THRESHOLD = 0.7`，依据：

| 置信度 | 含义 | 处理 |
|---|---|---|
| ≥ 0.9 | 高置信，识别可靠 | 本地够用 |
| 0.7-0.9 | 中等，可能有小错 | 本地 + 抽查 |
| < 0.7 | 低置信，可能识别错 | 升级 VLM |

> 💡 阈值 0.7 是在毒文档上校准的（正文行 0.97+、短片段 0.58）。**你的文档集不同，阈值要重新校准**——取 50 页扫描件跑本地 OCR，人工核对识别质量，找到「识别开始出错的置信度边界」。这是 L08 评估的一部分。

---

## 4. 中文 OCR 的坑

| 坑 | 是什么 | 对策 |
|---|---|---|
| **印章遮挡** | 红章盖在文字上，OCR 把章当背景丢掉或乱识别 | VLM 直读（印章是图像特征，VLM 能区分） |
| **表格线干扰** | 扫描表的框线被识别成字符（如 `|` → `1`） | 表格区单独处理（L02 的 pdfplumber + OCR 兜底） |
| **繁简混排** | 繁体字识别率低于简体 | RapidOCR 默认简体，繁体文档需切模型 |
| **手写体** | 本地 OCR 几乎识别不了 | VLM（手写体是 VLM 的强项） |
| **低质扫描** | 模糊/倾斜/曝光 | 先图像预处理（去倾斜/增强），再 OCR |

> 💡 **本课的毒文档是「清晰扫描」**（150dpi 渲染，字迹清楚），所以本地 OCR 准确率高。真实企业的扫描件质量参差不齐——这正是 hybrid 路由存在的理由：**不能假设所有扫描页都清晰**。

---

## 5. OCR 结果带 bbox（溯源主线）

本课的 `OcrBox` 不只是文本，还带 **bbox + score**：

```python
@dataclass(frozen=True)
class OcrBox:
    text: str
    bbox: tuple[float, float, float, float]  # 识别区域坐标
    score: float                              # 置信度
```

> 🎯 **bbox 是溯源主线的延伸**。L06 的引用溯源要回到原文档位置——扫描页的「原始位置」就是 OCR 识别到的 bbox。说「试用期3个月」出自「文档 P3 的 (x0,y0,x1,y1) 区域」，用户能裁剪原图核对。没有 bbox，扫描件的引用只能到页码，到不了区域。

---

## 6. 本课代码会做什么

### `code.py`（教学，本地真跑 + mock）
- ① 现状（off）：扫描页抽空（L00 天花板复现）
- ② 本地 RapidOCR：真跑，打耗时/置信度/识别文本
- ③ VLM 直读：无 key 时 mock 成本画像（按图计费估算）
- ④ hybrid 路由：先本地，低置信度标记升级

### 落地到 kb-qa
- 新增 `src/kb_qa/ocr.py`：`OcrBox`/`OcrResult` + `ocr_page`（按 `config.ocr_engine` 路由）
- `doc_parser.py` 扫描页分支：`ocr_engine != off` 时用 OCR 填充 image 元素 content
- `tests/test_ocr.py`：13 个测试（真跑 RapidOCR + hybrid 路由 mock + 开关回归）

---

## 7. 跑起来

### 教学代码（本地真跑 OCR）
```bash
cd doc-intelligence-lessons/03_ocr
python code.py
```
预期：RapidOCR 识别出 4 个扫描事实、置信度 0.946、hybrid 判定本地够用。

> ⚠️ **首次运行**：RapidOCR 会下载 ONNX 模型（~10MB），首次耗时 20-30s；后续稳态约 2.8s/页。

### 落地验证（kb-qa）
```bash
cd portfolio-projects/knowledge-base-qa
python -m pytest tests/test_ocr.py -q                    # 13 passed
python -m pytest -q                                       # 108 passed
# 验证扫描页 OCR 填充：
python -c "
import sys; sys.path.insert(0, 'src')
from kb_qa.config import settings
settings.ocr_engine = 'rapidocr'
from kb_qa.doc_parser import parse_pdf
els = parse_pdf('../../data/multimodal_docs/company_briefing.pdf')
p3 = [e for e in els if e.page==3][0]
print('扫描页识别到', len(p3.content), '字符')
print('含试用期:', '试用期' in p3.content)
"
```

### 验收检查
- [ ] RapidOCR 识别出 4 个杀手事实（试用期/竞业/赔偿/通知）
- [ ] hybrid 路由：高置信度页不升级 VLM（成本 0）
- [ ] `ocr_engine=off` 回归：扫描页 content 为空（现状不变）
- [ ] 硬任务扫描题 before（L00: 0%）→ after（本地 OCR 识别出答案）
- [ ] OCR 单测全绿（真跑 RapidOCR + hybrid mock）

---

## 🎯 面试话术

> 「扫描件我用置信度路由：本地 RapidOCR 打头阵——免费、离线、清晰扫描每页 2.8s 准确率 95%+。低置信度页（<0.7，通常是印章遮挡或模糊扫描）才升级 glm-4v 直读，单页 0.075 元。全 VLM 是烧钱（100 页 7.5 元），全本地是赌运气（模糊页识别错），路由用 10% 的成本买到接近全 VLM 的精度。OCR 结果带 bbox 和置信度——bbox 给 L06 的区域引用溯源用，置信度给路由判定用。」

---

## 落地清单

| 文件 | 改动 | 如何验证 |
|---|---|---|
| `src/kb_qa/ocr.py` | **新增**：`OcrBox`/`OcrResult` + `render_page_image` + `ocr_with_rapidocr` + `ocr_with_vlm` + `ocr_page`（路由） | `python -c "from kb_qa.ocr import ocr_page; print(ocr_page('毒文档', 2, 'rapidocr') is not None)"` |
| `src/kb_qa/doc_parser.py` | 扫描页分支：`ocr_engine != off` 时用 `ocr_page` 填充 image 元素 content | 开 `ocr_engine=rapidocr` 后 P3 content 非空 |
| `src/kb_qa/config.py` | `ocr_engine` 字段已加（L01），默认 `off` | `settings.ocr_engine == "off"` |
| `tests/test_ocr.py` | **新增**：13 个测试（RapidOCR 真跑 + hybrid 路由 + 开关回归 + bbox/score） | `pytest tests/test_ocr.py -q` → 13 passed |

> 📌 **两条主线位置**：本课是**成本-精度主线**的核心案例——三路线的对照表用真实数字（本地 0 元/2.8s/0.946 vs VLM 0.075 元/3s/0.98 vs hybrid 按需）量化权衡；在**溯源主线**上，OCR 结果带 bbox，扫描页的引用能回到识别区域（L06 的「P3·(x0,y0,x1,y1)」）。

下一课 [Lesson 04 — 图表与图片理解](../04_chart_vision/) 解决图表页——glm-4v-plus 把柱状图里的数字变成可问答的知识，设计「描述缓存 + 现场看图」两段式消费模式。
