# Lesson 04 — 图表与图片理解

> 本课目标：**让图表里的数字变成可问答的知识——用 glm-4v-plus 设计「描述缓存 + 现场看图」两段式消费模式，描述负责被搜到、原图负责答得准**。
>
> 学完你能回答面试官那句：**「图表里的数字能问吗？」**——能，两段式：入库时 VLM 提结构化描述做索引（缓存去重），命中后现场看图作答。钱花在刀刃上。

---

## 1. 图表是信息密度最高、损失最大的元素

L00 基线里图表题 0/4 全挂——柱状图的数值（1800/2400/2900）**只在图片像素里**，文本层完全没有：

```
图表页的尴尬：
   matplotlib 画的柱状图
      │
   嵌入 PDF（图片对象）
      │
   get_text() → 只拿到标题「2024 年度经营数据」
                柱子顶上的 1800/2400/2900 完全不可见！
```

> 🎯 **核心认知**：图表是企业文档里**信息密度最高**的元素——一张柱状图浓缩了 4 个季度的营收。它也是 text-only 管线**损失最大**的元素：整张图的数字全丢。图表理解的本质是让 VLM「看图说话」，把图形编码的数字提取成文本。

### 图表 vs 表格 vs 扫描：三种图片的 Different 处理

| 元素 | 图片里是什么 | 处理方式 | 本课/前课 |
|---|---|---|---|
| **扫描件** | 文字的位图 | OCR（字→文本） | L03 |
| **表格（图片表）** | 网格+文字的位图 | OCR 或 VLM | L03 延伸 |
| **图表** | 数据的图形编码（柱子高度=数值） | VLM 描述（图→结构化文本） | **L04** |

> 💡 **图表不能用 OCR**——OCR 识别的是「字」，但图表的数值是「柱子高度」「折线走势」这种图形编码，OCR 抽不到。必须用 VLM（视觉语言模型）理解图形语义。这是图表和扫描件的根本区别。

---

## 2. 方案对比：图片怎么被消费（本课灵魂）

图表抽出来后（L01 已识别为 image 元素），怎么让它能被检索和问答？三种消费模式：

| 模式 | 怎么做 | 检索 | 答案精度 | 成本 |
|---|---|---|---|---|
| **入库时生成描述** | VLM 描述 → embedding 入库 | ✅ 文本可检索 | 🟡 受描述质量限制 | 入库时一次性 |
| **问答时现场看图** | 每问都把图丢给 VLM | 🚫 图不能直接检索 | 🟢 最忠实 | 每问都花钱 |
| **两段式**（推荐） | 描述做索引 + 命中后现场看图 | ✅ 描述可检索 | 🟢 原图作答 | 入库 + 命中时 |

```
三种消费模式的成本画像（100 张图、每图被问 5 次）：

   只用描述：   100 次描述（入库）+ 0 次看图 = 100 次 VLM 调用
   只现场看图： 0 次描述 + 500 次看图（每问一次）= 500 次 VLM 调用 💰💰💰
   两段式：     100 次描述 + ~命中数×看图 ≈ 100 + 50 = 150 次 VLM 调用 💰
   
   两段式省在哪：大部分图「从没被问到」→ 只花了描述的钱，没花看图的钱
```

> 🎯 **本课选两段式的理由**：描述让图表「能被搜到」（文字 query 命中描述→找到图），原图让答案「答得准」（直接看图，不受描述遗漏限制）。**描述负责被搜到，原图负责答得准**——分工明确，钱花在刀刃上。只现场看图的问题是图不能直接检索（要 L05 的描述索引中转），只描述的问题是复杂判断（趋势/对比）描述可能写不全。

---

## 3. 两段式消费的工程实现

### 段一：入库时 describe_image（描述做索引 + 缓存）

```python
def describe_image(image_bytes, *, force_refresh=False):
    img_hash = md5(image_bytes)
    cache_file = vision_cache / f"{img_hash}.json"
    
    # ① 命中缓存直接返回（重复入库不重复调 VLM）
    if cache_file.exists() and not force_refresh:
        return load(cache_file)
    
    # ② 调 glm-4v-plus 生成结构化描述
    desc = vlm.invoke([image, DESCRIBE_PROMPT])
    
    # ③ 落盘缓存（按内容哈希去重）
    save(cache_file, desc)
    return desc
```

**描述 prompt 设计**（关键：不要废话描述，要结构化数据）：

```
请提取：1.图表类型 2.所有数值和标签 3.坐标轴 4.趋势结论
用简洁条目列出，不要写「这是一张柱状图」式的废话开头。直接给数据和结论。
```

> 🎯 **prompt 设计的核心**：要 VLM 提取「可检索、可问答」的结构化信息（数值/标签/趋势），而不是泛泛的「这是一张关于营收的柱状图」。后者对检索和问答毫无价值——用户问「Q3 多少」，描述里得有「Q3: 2100」才能命中。

### 段二：问答时 answer_with_image（现场看图作答）

```python
def answer_with_image(image_bytes, question):
    return vlm.invoke([image, f"请根据图片回答：{question}"])
```

> 💡 **现场看图什么时候触发**：L05 的检索路由——文字 query 命中图表元素（通过描述索引）后，`service.py` 按 `element_type=image` 触发现场看图。不是每问都看，是**命中图表时才看**。

### 缓存去重（成本控制的关键）

```
重复入库场景：同一份 PDF 被重新 ingest（内容没变）
   无缓存：每张图重新调 VLM 描述 → 烧钱
   有缓存：按图片内容 MD5 命中缓存 → 0 次调用
   
   缓存文件：vision_cache/{md5}.json
   去重依据：图片内容哈希（而非文件名/页码——同一图在不同页也去重）
```

---

## 4. glm-4v-plus 的能力边界（诚实给出读不准的例子）

用真实 glm-4v-plus 跑毒文档图表页（code.py 演示 1），它的表现：

| 任务 | glm-4v-plus 表现 |
|---|---|
| 识别图表类型（柱状图） | ✅ 准确 |
| 读取具体数值（Q1:1800） | ✅ 准确（4 个全对） |
| 找最大值（Q4 最高） | ✅ 准确 |
| **趋势判断（逐季上升？）** | 🟡 **读不准**：说「逐季上升」，但实际 Q2→Q3 下降 |

> ⚠️ **诚实标注**：glm-4v-plus 对「单点数值」读得准，对「整体趋势」有时过度概括（把波动说成单调）。这就是两段式的价值——简单数值题描述够答，复杂趋势判断现场看图让人/VLM 再确认。**不要盲信 VLM 的一次描述**，关键数字要可回溯（L06 的引用）。

---

## 5. 本课代码会做什么

### `code.py`（真实 VLM 或 mock）
- ① 图表页 → glm-4v-plus 生成结构化描述（有 key 真跑，无 key 预录 mock）
- ② 两段式对照：「只用描述答」vs「现场看图答」同一批图表题
- ③ 缓存演示：同一图片重复描述命中缓存（哈希去重）

### 落地到 kb-qa
- 新增 `src/kb_qa/vision.py`：`describe_image`（带缓存）+ `answer_with_image` + `is_cached`/`clear_cache`
- `doc_parser.py` image 元素分支：`enable_image_caption` 开启时附加 VLM 描述
- `tests/test_vision.py`：12 个测试（描述/缓存/开关回归，全 mock）

---

## 6. 跑起来

### 教学代码（真实 VLM 或 mock）
```bash
cd doc-intelligence-lessons/04_chart_vision
python code.py
```
- 有 `ZHIPUAI_API_KEY`：真调 glm-4v-plus，描述/答案是真实输出
- 无 key：走预录 mock（描述/答案预存，教学可复现）

### 落地验证（kb-qa）
```bash
cd portfolio-projects/knowledge-base-qa
python -m pytest tests/test_vision.py -q                    # 12 passed
python -m pytest -q                                          # 120 passed
# 验证图表描述填充：
python -c "
import sys; sys.path.insert(0, 'src')
from kb_qa.config import settings
settings.enable_image_caption = True
settings.enable_multimodal_ingest = True
from kb_qa.doc_parser import parse_pdf
els = parse_pdf('../../data/multimodal_docs/company_briefing.pdf')
p5 = [e for e in els if e.page==5 and e.type=='image'][0]
print('图表描述:', p5.content[:80])
"
```

### 验收检查
- [ ] glm-4v-plus 描述含图表类型 + 数值 + 趋势（或 mock 预录等价）
- [ ] 两段式对照：描述答 vs 现场看图答都覆盖图表题
- [ ] 缓存命中：重复描述同一图片不重复调 VLM（缓存日志）
- [ ] `enable_image_caption=off` 时图表 image 元素 content 为空（回归）
- [ ] 硬任务图表题 before（L00: 0%）→ after（VLM 能读出数值）

---

## 🎯 面试话术

> 「图表我是两段式：入库时 glm-4v-plus 提结构化描述做索引——要求它给数值/标签/趋势而非废话，按图片内容哈希缓存去重，重复入库不重复调 VLM。问答命中图表后现场看图作答，直接用原图而非描述，答得更准。描述负责被搜到，原图负责答得准，钱花在刀刃上。glm-4v-plus 读单点数值很准，但趋势判断会过度概括——所以关键数字必须可回溯到原图，这是 L06 引用溯源的事。」

---

## 落地清单

| 文件 | 改动 | 如何验证 |
|---|---|---|
| `src/kb_qa/vision.py` | **新增**：`describe_image`（带哈希缓存）+ `answer_with_image` + `is_cached`/`clear_cache` | `python -c "from kb_qa.vision import describe_image; print(describe_image(b'x', use_mock=True)[:20])"` |
| `src/kb_qa/doc_parser.py` | image 元素分支：`enable_image_caption` 开启时附加描述；加 `_render_page_region`（按 bbox 截图） | 开 `enable_image_caption` 后图表元素 content 非空 |
| `src/kb_qa/config.py` | `enable_image_caption`/`vision_model` 已加（L01），默认 off/glm-4v-plus | `settings.vision_model == "glm-4v-plus"` |
| `tests/test_vision.py` | **新增**：12 个测试（描述/缓存去重/两段式/开关回归，全 mock） | `pytest tests/test_vision.py -q` → 12 passed |

> 📌 **两条主线位置**：本课在**成本-精度主线**上是两段式的核心——描述（入库一次性）vs 现场看图（每问都花）vs 两段式（按需）的成本画像量化清楚；在**溯源主线**上，图表的引用必须能回到原图（数字是 VLM 读出来的，读错的可能），L06 的「图表元素 → 原图区域」靠 L01 的 bbox + 本课的 image_path。

下一课 [Lesson 05 — 多模态检索：图片怎么被搜到](../05_multimodal_retrieval/) 打通「文字 query 检索到图片元素」的链路——描述索引路线让图表可检索，命中后按类型路由现场看图。
