"""图表与图片理解：glm-4v-plus 的两段式消费（doc-intelligence L04）。

两段式设计（成本-精度主线在此）：
    ① 入库时 describe_image：VLM 提结构化描述（轴标签/数值/趋势），做索引 + 缓存
    ② 问答时 answer_with_image：检索命中图表后，现场看图作答（忠实但花钱）

为什么两段式：
    - 只用描述（入库时生成）：检索友好但可能丢细节（描述写不下的数字）
    - 只现场看图（问答时）：忠实但每问都花钱（重复问同一张图反复调 VLM）
    - 两段式：描述负责「被搜到」，原图负责「答得准」，钱花在刀刃上

缓存：describe_image 的结果按图片内容哈希落盘，重复入库不重复调 VLM。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import settings

# 描述缓存目录（落盘，按图片哈希去重）
_CACHE_DIR = Path(settings.docs_dir).parent / "vision_cache"

# 描述 prompt：要求提取结构化信息，不要「这是一张柱状图」式的废话
_DESCRIBE_PROMPT = """请仔细分析这张图片，提取结构化信息用于知识库检索。要求：
1. 图表类型（柱状图/折线图/饼图/表格/示意图/其他）
2. 所有能读到的数值和它们对应的标签（如「Q1: 1800」「Q2: 2400」）
3. 坐标轴标签和单位
4. 关键趋势或对比结论（如「Q4 最高」「逐季上升」）
5. 如果是示意图/流程图，描述其中的文字和结构关系

用简洁的条目列出，不要写「这是一张...」式的废话开头。直接给数据和结论。"""


def _image_hash(image_bytes: bytes) -> str:
    """图片内容的 MD5，作缓存 key（去重依据）。"""
    return hashlib.md5(image_bytes).hexdigest()


def _cache_path(img_hash: str) -> Path:
    """缓存文件路径：vision_cache/{hash}.json。"""
    return _CACHE_DIR / f"{img_hash}.json"


def describe_image(
    image_bytes: bytes,
    *,
    force_refresh: bool = False,
    use_mock: bool = False,
) -> str:
    """用 glm-4v-plus 给图片生成结构化描述（带哈希缓存）。

    缓存逻辑：按图片内容 MD5 落盘到 vision_cache/，重复入库命中缓存不调 VLM。
    force_refresh=True 时忽略缓存强制重新描述（描述质量抽查用）。
    use_mock=True 时不调 VLM，返回预录描述（教学/测试用，省 token）。
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    img_hash = _image_hash(image_bytes)
    cache_file = _cache_path(img_hash)

    # ① 命中缓存直接返回（重复入库不重复调 VLM）
    if not force_refresh and cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data["description"]

    # ② 生成描述（真调 VLM 或 mock）
    if use_mock or not settings.zhipuai_api_key:
        # mock：返回占位描述（教学/测试用，诚实标注）
        desc = "[mock 描述] 需配置 ZHIPUAI_API_KEY 调 glm-4v-plus 生成真实描述。"
    else:
        desc = _call_vlm_describe(image_bytes)

    # ③ 落盘缓存
    cache_file.write_text(
        json.dumps({"hash": img_hash, "description": desc}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return desc


def _call_vlm_describe(image_bytes: bytes) -> str:
    """真调 glm-4v-plus 生成描述（需 API key）。

    用 LangChain 的 ChatZhipuAI，多模态消息格式：
    [{"role": "user", "content": [{"type": "image_url", ...}, {"type": "text", ...}]}]
    """
    import base64

    from langchain_community.chat_models import ChatZhipuAI

    # 图片转 base64 data URL（ChatZhipuAI 接受 data:image/png;base64,... 格式）
    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:image/png;base64,{b64}"

    vlm = ChatZhipuAI(
        model=settings.vision_model,  # glm-4v-plus
        api_key=settings.zhipuai_api_key,
        temperature=0.1,  # 描述要稳定，低温
    )
    resp = vlm.invoke([
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": _DESCRIBE_PROMPT},
        ]}
    ])
    return resp.content.strip() if hasattr(resp, "content") else str(resp)


def answer_with_image(
    image_bytes: bytes,
    question: str,
    *,
    use_mock: bool = False,
) -> str:
    """现场看图作答：把图片 + 问题丢给 glm-4v-plus，返回答案。

    这是两段式的第二段——检索命中图表元素后，用原图（而非描述）作答。
    优势：忠实（直接看图，不受描述质量限制）；劣势：每次调用都花钱。
    use_mock=True 时返回占位答案（教学/测试用）。
    """
    if use_mock or not settings.zhipuai_api_key:
        return (
            f"[mock 答案] 需配置 ZHIPUAI_API_KEY 调 glm-4v-plus 现场看图。"
            f"问题：{question}"
        )

    import base64

    from langchain_community.chat_models import ChatZhipuAI

    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:image/png;base64,{b64}"

    vlm = ChatZhipuAI(
        model=settings.vision_model,
        api_key=settings.zhipuai_api_key,
        temperature=0.1,
    )
    resp = vlm.invoke([
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": f"请根据图片回答：{question}。直接给答案，简明扼要。"},
        ]}
    ])
    return resp.content.strip() if hasattr(resp, "content") else str(resp)


def is_cached(image_bytes: bytes) -> bool:
    """检查图片是否已有缓存（诊断用：看缓存命中率）。"""
    return _cache_path(_image_hash(image_bytes)).exists()


def clear_cache() -> int:
    """清空描述缓存（测试/重新描述用）。返回清除的文件数。"""
    if not _CACHE_DIR.exists():
        return 0
    count = 0
    for f in _CACHE_DIR.glob("*.json"):
        f.unlink()
        count += 1
    return count
