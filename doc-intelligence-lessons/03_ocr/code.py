"""Lesson 03 — 扫描件：OCR 三路线
==================================
本脚本演示给扫描页装上眼睛的三条路线，用真实数字裁决成本-精度：
    ① 现状（off）：扫描页抽空（L00 天花板）
    ② 本地 RapidOCR：真跑，打识别准确率/耗时/置信度（免费、离线）
    ③ VLM 直读：无 key 时 mock 成本画像（按图计费），诚实标注
    ④ 置信度混合路由（hybrid）：先本地 OCR，低置信度页标记升级 VLM

本地 OCR 是真跑（毒文档扫描页），VLM 路线无 key 时走 mock（成本估算）。

运行：python code.py
依赖：RapidOCR + PyMuPDF（venv 已装）；毒文档 data/multimodal_docs/company_briefing.pdf
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Windows GBK 坑：中文输出会 UnicodeEncodeError，统一 utf-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
POISON_PDF = ROOT / "data" / "multimodal_docs" / "company_briefing.pdf"
sys.path.insert(0, str(ROOT / "portfolio-projects" / "knowledge-base-qa" / "src"))
from kb_qa.ocr import ocr_page, render_page_image  # noqa: E402


# ══════════════════════════════════════════════════════════════════
# 1. 现状基线：off 模式，扫描页抽空
# ══════════════════════════════════════════════════════════════════
def show_off_baseline() -> None:
    """ocr_engine=off：扫描页 content 为空（L00 天花板，现状回归）。"""
    result = ocr_page(POISON_PDF, page_idx=2, engine="off")
    print(f"  engine=off → OCR 结果: {result}")
    print("  → 扫描页 content 保持空，4 个关键事实全丢失（L00 基线复现）")


# ══════════════════════════════════════════════════════════════════
# 2. 本地 RapidOCR：真跑，打真实数字
# ══════════════════════════════════════════════════════════════════
def show_rapidocr_result() -> dict:
    """本地 RapidOCR 真跑扫描页，返回真实指标。"""
    t0 = time.monotonic()
    result = ocr_page(POISON_PDF, page_idx=2, engine="rapidocr")
    wall = time.monotonic() - t0
    assert result is not None
    print(f"  识别到 {len(result.boxes)} 个文本块")
    print(f"  OCR 引擎耗时: {result.elapsed_sec:.2f}s | 挂钟(含渲染): {wall:.2f}s")
    print(f"  平均置信度: {result.avg_score:.3f} | 低置信块占比: {result.low_confidence_ratio:.0%}")
    print(f"  needs_vlm(升级判定): {result.needs_vlm}")
    print(f"\n  识别文本:")
    for box in result.boxes:
        flag = "⚠️ 低置信" if box.score < 0.7 else "✅"
        print(f"    [{box.score:.2f}] {flag} {box.text}")
    return {
        "engine": "rapidocr",
        "elapsed_sec": result.elapsed_sec,
        "avg_score": result.avg_score,
        "n_boxes": len(result.boxes),
        "needs_vlm": result.needs_vlm,
        "cost": 0.0,  # 本地免费
    }


# ══════════════════════════════════════════════════════════════════
# 3. VLM 直读：无 key 时 mock 成本画像
# ══════════════════════════════════════════════════════════════════
def show_vlm_cost_profile() -> dict:
    """VLM 直读的成本画像（无 key 时 mock，诚实标注）。

    VLM 路线：把扫描页截图丢给 glm-4v-plus，它直接读图返回文本。
    优势：版面理解强（印章遮挡/表格线干扰/手写体比本地 OCR 强）。
    劣势：按图计费（每页一次 VLM 调用），比本地 OCR 贵。
    本课无 key 走 mock，成本估算基于智谱定价页。
    """
    from kb_qa.config import settings

    has_key = bool(settings.zhipuai_api_key)
    if has_key:
        print("  [有 API key] 可真跑 VLM，但本课为省 token 用 mock 成本画像。")

    # 成本估算（基于智谱定价页 2026-07）
    # glm-4v-plus：输入 50 元/百万 token，一张图约 1000-2000 token（视分辨率）
    # 一页扫描件 200dpi 约 1500 token → 单页约 0.075 元
    img_bytes = render_page_image(POISON_PDF, page_idx=2, dpi=200)
    img_kb = len(img_bytes) / 1024
    est_image_tokens = 1500  # 经验估算
    est_cost = est_image_tokens / 1_000_000 * 50.0  # 元

    print(f"  [mock] 图片大小: {img_kb:.0f}KB | 估算 image tokens: ~{est_image_tokens}")
    print(f"  [mock] 单页成本: ~{est_cost:.4f} 元（glm-4v-plus 输入 50元/百万token）")
    print(f"  [mock] 版面理解: 强（印章/表格线/手写体优于本地 OCR）")
    print(f"  [mock] 延迟: ~2-4s/页（API 往返，本地 OCR 是 1.6-2.8s）")
    return {
        "engine": "vlm",
        "elapsed_sec": 3.0,  # 估算
        "avg_score": 0.98,   # VLM 无置信度概念，给近似
        "n_boxes": 0,        # VLM 返回整页文本，不逐块
        "needs_vlm": False,
        "cost": est_cost,
        "mock": True,
    }


# ══════════════════════════════════════════════════════════════════
# 4. 置信度混合路由（hybrid）：本课推荐
# ══════════════════════════════════════════════════════════════════
def show_hybrid_routing(rapidocr_metrics: dict) -> dict:
    """hybrid 路由：先本地 OCR，低置信度页升级 VLM。

    毒文档扫描页本地 OCR 置信度高（0.946），不需要升级。
    但演示「低置信度会触发升级」的逻辑——构造一个模糊场景。
    """
    result = ocr_page(POISON_PDF, page_idx=2, engine="hybrid")
    assert result is not None
    print(f"  本地 OCR 平均置信度: {result.avg_score:.3f}")
    if result.needs_vlm:
        print(f"  ⚠️ 置信度 < 0.7 → 标记升级 VLM（成本 +{show_vlm_cost_profile()['cost']:.4f}元）")
        route = "升级 VLM"
    else:
        print(f"  ✅ 置信度 ≥ 0.7 → 本地 OCR 够用，不升级（省钱）")
        route = "本地够用"
    print(f"  路由结果: {route}")
    return {
        "engine": "hybrid",
        "elapsed_sec": rapidocr_metrics["elapsed_sec"],
        "route": route,
        "cost": 0.0 if route == "本地够用" else show_vlm_cost_profile()["cost"],
    }


# ══════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════
def main() -> None:
    if not POISON_PDF.exists():
        print(f"[ERR] 找不到毒文档 {POISON_PDF}")
        return

    print("=" * 70)
    print("演示 1：现状（off）—— 扫描页的天花板")
    print("=" * 70)
    show_off_baseline()

    print("\n" + "=" * 70)
    print("演示 2：本地 RapidOCR —— 真跑，免费离线")
    print("=" * 70)
    print("（首次运行含模型加载，可能 20-30s；稳态约 2-3s/页）")
    rapidocr_metrics = show_rapidocr_result()

    print("\n" + "=" * 70)
    print("演示 3：VLM 直读 —— 成本画像（mock，无 key）")
    print("=" * 70)
    vlm_metrics = show_vlm_cost_profile()

    print("\n" + "=" * 70)
    print("演示 4：置信度混合路由（hybrid）—— 本课推荐")
    print("=" * 70)
    hybrid_metrics = show_hybrid_routing(rapidocr_metrics)

    # ── 三路线对照表 ──
    print("\n" + "=" * 70)
    print("三路线对照（成本-精度主线）")
    print("=" * 70)
    print(f"{'路线':<12} {'耗时/页':<10} {'置信度':<10} {'成本/页':<10} {'适合'}")
    print("-" * 70)
    print(f"{'off(现状)':<12} {'—':<10} {'—':<10} {'0元':<10} 🚫 扫描页全盲")
    print(f"{'rapidocr':<12} {rapidocr_metrics['elapsed_sec']:.1f}s{'':<5} {rapidocr_metrics['avg_score']:.3f}{'':<5} {'0元':<10} ✅ 清晰扫描、预算敏感")
    vlm_tag = "[mock]" if vlm_metrics.get("mock") else ""
    print(f"{'vlm'+vlm_tag:<12} ~{vlm_metrics['elapsed_sec']:.0f}s{'':<5} ~{vlm_metrics['avg_score']:.2f}{'':<5} {vlm_metrics['cost']:.4f}元{'':<4} ✅ 复杂版面、印章遮挡")
    print(f"{'hybrid':<12} {hybrid_metrics['elapsed_sec']:.1f}s{'':<5} {rapidocr_metrics['avg_score']:.3f}{'':<5} {hybrid_metrics['cost']:.4f}元{'':<4} 🎯 生产推荐")

    print(f"\n> 🎯 结论：hybrid 是工程答案——本地 RapidOCR 打头阵（免费、{rapidocr_metrics['elapsed_sec']:.1f}s/页），")
    print(f"  低置信度页（<0.7）才升级 glm-4v 直读。毒文档扫描页置信度 {rapidocr_metrics['avg_score']:.3f}，本地够用。")
    print(f"  全 VLM 是烧钱（每页 ~{vlm_metrics['cost']:.4f}元），全本地是赌运气（模糊页识别错），路由是平衡。")

    print("\n" + "=" * 70)
    print("诚实标注")
    print("=" * 70)
    print("  - RapidOCR 的耗时/置信度是真跑实测（毒文档 200dpi 扫描页）。")
    print("  - VLM 的成本是估算（基于定价页 + 图片 token 经验值），未真调 API。")
    print("  - hybrid 的「升级」在本课只标记 needs_vlm，不自动调 VLM（成本控制）。")
    print("  - 真实 OCR 精度需人工核对（L08 评估时抽样标注）。")


if __name__ == "__main__":
    main()
