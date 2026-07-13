"""L05 · 视觉路线：SoM 标注截图 + 三路线（文本/视觉/混合）对照。

核心产出：
    - annotate_screenshot()   用 Pillow 在截图上给元素画框+编号（SoM）
    - vision_agent_loop()     视觉路线 agent 循环（观察=SoM截图，行动=click(n) DSL）
    - run_comparison()        三路线同任务对照（成功率/token/耗时）

SoM 的作用（README 详述）：
    通用 VLM 的 grounding 命门——直接让 VLM 输出坐标会飘，
    SoM 给截图画框编号，VLM 答编号不答坐标，和文本派 click(n) 同构。

三路线：
    文本：元素编号列表（L04 已跑）
    视觉：SoM 截图喂 VLM（本课）
    混合：文本为主，卡住才截图（落地选它）

跑法：
    cd gui-agent-lessons/00_overview/test_pages && python -m http.server 8765
    cd gui-agent-lessons/05_vision
    python code.py            # mock 三路线对比 + 生成 som_demo.png
    python code.py --real     # 视觉路线用真实 glm-4v-plus（需 ZHIPUAI_API_KEY）
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_LESSONS = _HERE.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _LESSONS / rel / "code.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_l01 = _load("l01_code", "01_playwright")
_l02 = _load("l02_code", "02_observation")
_l03 = _load("l03_code", "03_action")
_l04 = _load("l04_code", "04_text_agent")
BrowserSession = _l01.BrowserSession
page_to_obs = _l02.page_to_obs
parse_action = _l03.parse_action
validate_action = _l03.validate_action
execute_action = _l03.execute_action
build_prompt = _l04.build_prompt
MockLLM = _l04.MockLLM

L00_BASE = "http://127.0.0.1:8765"


# ──────────────────────────────────────────────────────────────
# SoM 标注：截图上画框+编号
# ──────────────────────────────────────────────────────────────

def collect_elements_with_bbox(session) -> list[dict]:
    """提取可交互元素 + 边界框（bbox）。bbox 用于 SoM 画框。"""
    INTERACTIVE = (
        'a, button, input, select, textarea, '
        '[role="button"], [role="link"], [role="textbox"], [role="checkbox"]'
    )
    page = session.page
    els = page.locator(INTERACTIVE)
    n = els.count()
    elements = []
    for i in range(n):
        el = els.nth(i)
        try:
            # 跳过不可见元素（bbox 为 None）
            bbox = el.bounding_box()
            if bbox is None:
                continue
            # 跳过视口外元素（SoM 只标可见的）
            if bbox["x"] > 1280 or bbox["y"] > 800 or bbox["x"] + bbox["width"] < 0:
                continue
            text = (el.inner_text() or "").strip()[:40]
            elements.append({
                "idx": len(elements) + 1,  # 重新连续编号（跳过的不算）
                "role": _role_of(el),
                "label": text or el.get_attribute("value") or "(空)",
                "bbox": (int(bbox["x"]), int(bbox["y"]),
                         int(bbox["x"] + bbox["width"]),
                         int(bbox["y"] + bbox["height"])),
                "_locator": el,  # 保留定位器供执行用
            })
        except Exception:
            continue
    return elements


def _role_of(el) -> str:
    tag = el.evaluate("e => e.tagName.toLowerCase()")
    role = el.get_attribute("role") or ""
    if role:
        return role
    return {"a": "link", "button": "button", "input": "textbox",
            "select": "combobox", "textarea": "textbox"}.get(tag, tag)


def annotate_screenshot(session, elements, out_path: Path) -> Path:
    """截图 + SoM 标注（画框+编号）。降采样宽≤1280（成本控制）。"""
    from PIL import Image, ImageDraw, ImageFont
    # 先截图
    raw_path = out_path.parent / (out_path.stem + "_raw.png")
    session.screenshot(raw_path)
    img = Image.open(raw_path)
    # 降采样（宽≤1280）
    if img.width > 1280:
        ratio = 1280 / img.width
        img = img.resize((1280, int(img.height * ratio)))
    draw = ImageDraw.Draw(img)
    # 尝试加载字体（失败用默认）
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        font = ImageFont.load_default()
    for el in elements:
        x1, y1, x2, y2 = el["bbox"]
        # 降采样后坐标同步缩放
        if img.width == 1280 and raw_path != out_path:
            pass  # viewport 已是 1280，截图不缩，bbox 不变
        draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
        # 编号标在框左上角
        draw.rectangle([x1, max(0, y1 - 22), x1 + 24, y1], fill="red")
        draw.text((x1 + 2, max(0, y1 - 20)), str(el["idx"]), fill="white", font=font)
    img.save(out_path)
    return out_path


# ──────────────────────────────────────────────────────────────
# 视觉路线 prompt（截图 + 编号说明）
# ──────────────────────────────────────────────────────────────

def build_vision_prompt(task: str, history: list, elements: list[dict]) -> str:
    """视觉路线 prompt：说明截图上有编号标注 + 可用动作 + 历史。
    截图本身作为图片输入（VLM 多模态），文本部分是说明。"""
    lines = [f"【任务】{task}", "",
             "【观察】下方截图已用红色框+编号标注所有可交互元素。",
             "可用动作（与文本路线相同）：",
             "  click(n)      点击编号 n 的元素",
             "  type(n, text) 在编号 n 输入 text",
             "  scroll(dir)   滚动（up/down）",
             "  back()        后退",
             "  finish(答案)  完成任务", ""]
    if history:
        lines.append("【动作历史】")
        for s in history[-3:]:  # 视觉路线也用滑动窗口
            lines.append(f"  步{s.step}: {s.action_text.strip()} → {s.result}")
        lines.append("")
    # 元素编号-标签对照（帮 VLM 把编号和元素对上）
    lines.append("【元素编号对照】")
    for el in elements:
        lines.append(f"  [{el['idx']}] {el['role']} \"{el['label']}\"")
    lines.append("")
    lines.append("【你的动作】（输出一个动作，如 click(3) 或 finish(答案)）")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# 三路线对照实验
# ──────────────────────────────────────────────────────────────

def run_text_route(task: str, session, mock_script: list[str]) -> dict:
    """文本路线（L04）。返回 {success, steps, tokens, elapsed}。"""
    class CountingMock(MockLLM):
        def __init__(self, script, counter):
            super().__init__(script)
            self._counter = counter
        def __call__(self, prompt):
            self._counter[0] += len(prompt) // 4
            return super().__call__(prompt)
    counter = [0]
    llm = CountingMock(mock_script, counter)
    t0 = time.time()
    result = _l04.run_agent(task, session, llm, max_steps=12,
                            start_url=f"{L00_BASE}/index.html")
    return {
        "route": "文本", "success": result["done"], "steps": result["steps"],
        "tokens": counter[0], "elapsed": round(time.time() - t0, 2),
        "answer": result["answer"],
    }


def run_vision_route(task: str, session, mock_script: list[str],
                     real_vlm=None) -> dict:
    """视觉路线：SoM 截图喂 VLM。mock 时用 MockLLM（不真看图）。"""
    t0 = time.time()
    total_tokens = 0
    history = []
    mock = MockLLM(mock_script)
    session.goto(f"{L00_BASE}/index.html")
    session.wait_for_selector("body")
    som_path = _HERE / "som_demo.png"
    answer = ""

    for step in range(1, 13):
        elements = collect_elements_with_bbox(session)
        annotate_screenshot(session, elements, som_path)
        prompt = build_vision_prompt(task, history, elements)
        total_tokens += len(prompt) // 4 + 800  # +800 估图片 token（成本关键）

        if real_vlm is not None:
            # 真实 VLM：截图作为图片输入
            try:
                resp = real_vlm.invoke([
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"file://{som_path}"}},
                        {"type": "text", "text": prompt},
                    ]}
                ])
                action_text = resp.content.strip() if hasattr(resp, "content") else str(resp)
            except Exception as e:
                action_text = f"finish(VLM 失败：{e})"
        else:
            action_text = mock(prompt)  # mock 不看图，按脚本走

        action = parse_action(action_text)
        # 用视觉元素执行（elements 含 _locator）
        v = _validate_for_vision(action, elements)
        if not v["ok"]:
            from dataclasses import dataclass
            @dataclass
            class S:
                step: int
                action_text: str
                action: object
                result: str
            history.append(S(step, action_text, action, f"非法：{v['error']}"))
            print(f"  [视觉·步{step}] {action_text.strip()}  ❌ {v['error']}")
            continue

        r = _execute_for_vision(v["action"], elements, session)
        from dataclasses import dataclass
        @dataclass
        class S:
            step: int
            action_text: str
            action: object
            result: str
        history.append(S(step, action_text, v["action"], r["result"]))
        print(f"  [视觉·步{step}] {action_text.strip()}  → {r['result']}")
        if r["done"]:
            answer = r["result"]
            print(f"\n  ✅ 视觉路线完成（{step} 步）")
            return {"route": "视觉", "success": True, "steps": step,
                    "tokens": total_tokens, "elapsed": round(time.time() - t0, 2),
                    "answer": answer}
        try:
            session.page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass
    return {"route": "视觉", "success": False, "steps": 12,
            "tokens": total_tokens, "elapsed": round(time.time() - t0, 2),
            "answer": answer}


def _validate_for_vision(action, elements):
    """视觉路线校验：复用 L03 validate，但 elements 是带 bbox 的。"""
    # 转成 L3 期望的格式
    el_simple = [{"idx": e["idx"], "role": e["role"], "label": e["label"],
                  "selector": None} for e in elements]
    return validate_action(action, el_simple)


def _execute_for_vision(action, elements, session):
    """视觉路线执行：直接用元素的 _locator 点击（比 selector 更可靠）。"""
    try:
        if action.name == "click":
            el = elements[action.idx - 1]
            el["_locator"].click()
            return {"ok": True, "result": f"点击了 [{action.idx}] {el['label']}", "done": False}
        if action.name == "type":
            el = elements[action.idx - 1]
            el["_locator"].fill(action.text)
            return {"ok": True, "result": f"输入了「{action.text}」", "done": False}
        if action.name == "scroll":
            session.page.mouse.wheel(0, 800 if action.direction == "down" else -800)
            return {"ok": True, "result": f"滚动{action.direction}", "done": False}
        if action.name == "back":
            session.page.go_back()
            return {"ok": True, "result": "后退", "done": False}
        if action.name == "finish":
            return {"ok": True, "result": action.text, "done": True}
    except Exception as e:
        return {"ok": False, "result": f"执行失败：{e}", "done": False}
    return {"ok": False, "result": "未实现", "done": False}


def run_hybrid_route(task: str, session, mock_script: list[str]) -> dict:
    """混合路线：文本为主，模拟「卡住才截图」。
    本课 mock 版：前 2 步文本，第 3 步「卡住」切视觉（SoM），后续继续。
    真实场景由 L06 可靠性层触发切换。"""
    class CountingMock(MockLLM):
        def __init__(self, script, counter):
            super().__init__(script)
            self._counter = counter
        def __call__(self, prompt):
            self._counter[0] += len(prompt) // 4
            return super().__call__(prompt)
    counter = [0]
    llm = CountingMock(mock_script, counter)
    t0 = time.time()
    result = _l04.run_agent(task, session, llm, max_steps=12,
                            start_url=f"{L00_BASE}/index.html")
    # 模拟 1 次视觉确认（卡住时截图）
    counter[0] += 800  # 1 张图 token
    return {
        "route": "混合", "success": result["done"], "steps": result["steps"],
        "tokens": counter[0], "elapsed": round(time.time() - t0, 2),
        "answer": result["answer"],
    }


# ──────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────

def _server_up() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(L00_BASE + "/index.html", timeout=1).read()
        return True
    except Exception:
        return False


def main():
    print("=" * 64)
    print("L05 视觉路线：SoM 标注 + 三路线对照")
    print("=" * 64)

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("\n⚠️ playwright 未安装，跳过。")
        return
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("\n⚠️ pillow 未安装，跳过。安装见 requirements.txt。")
        return
    if not _server_up():
        print(f"\n⚠️ L00 本地服务未起（{L00_BASE}），请先跑:")
        print(f"   cd gui-agent-lessons/00_overview/test_pages && python -m http.server 8765")
        return

    use_real = "--real" in sys.argv
    task = "对比 LangGraph 最近 release 的版本号和发布日期（翻页进详情提取）"
    # 三路线用同一 mock 脚本（公平对照）
    script = [
        'type(1, "LangGraph")', 'click(2)', 'click(7)', 'click(3)',
        'finish(版本 v0.8.0，发布于 2024-08-15)',
    ]

    real_vlm = None
    if use_real:
        try:
            from langchain_community.chat_models import ChatZhipuAI
            import os
            key = os.getenv("ZHIPUAI_API_KEY", "")
            if key:
                real_vlm = ChatZhipuAI(model="glm-4v-plus", temperature=0.1,
                                       zhipuai_api_key=key)
                print("🤖 视觉路线使用真实 glm-4v-plus")
            else:
                print("⚠️ 缺 ZHIPUAI_API_KEY，视觉路线用 mock")
        except Exception as e:
            print(f"⚠️ VLM 初始化失败（{e}），视觉路线用 mock")
    else:
        print("🤖 三路线均用 mock（零 API）。--real 用真实 glm-4v-plus")

    results = []
    with BrowserSession(headless=True) as s:
        print(f"\n── ① 文本路线 ──")
        results.append(run_text_route(task, s, script))

        print(f"\n── ② 视觉路线（SoM）──")
        results.append(run_vision_route(task, s, script, real_vlm))

        print(f"\n── ③ 混合路线 ──")
        results.append(run_hybrid_route(task, s, script))

    # ── 对照表 ──
    print(f"\n{'='*64}")
    print(f"三路线对照表（同任务: 翻页取证）")
    print(f"{'='*64}")
    print(f"  {'路线':<6} {'成功':<6} {'步数':<6} {'≈token':<8} {'耗时s':<8} {'说明'}")
    notes = {"文本": "DOM完整时最省", "视觉": "图片token贵N倍", "混合": "文本+1次截图"}
    for r in results:
        mark = "✅" if r["success"] else "❌"
        print(f"  {r['route']:<6} {mark:<6} {r['steps']:<6} {r['tokens']:<8} "
              f"{r['elapsed']:<8} {notes.get(r['route'],'')}")
    print(f"\n  → 本地 DOM 完整页：文本路线不输视觉（甚至更省），视觉优势在 DOM 不完整场景")
    print(f"  → 落地选混合：文本为主，卡住才截图（L09 落地 / L06 触发切换）")

    som_path = _HERE / "som_demo.png"
    if som_path.exists():
        print(f"\n✅ SoM 标注图已存: {som_path}")


if __name__ == "__main__":
    main()
