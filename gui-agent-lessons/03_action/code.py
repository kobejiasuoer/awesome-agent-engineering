"""L03 · 行动空间：动作 DSL 解析器 + 校验器 + 执行器。

核心产出：
    - parse_action(text)     把 LLM 输出的文本解析成 Action 对象
    - validate_action(action, elements)  校验动作合法性（编号存在/参数合法）
    - execute_action(action, session, elements)  执行动作（调 L01 BrowserSession）

设计灵魂（README 详述）：
    - 受限 DSL（5 招）：click(n) / type(n, text) / scroll(dir) / back() / finish(answer)
    - 非法动作不崩：返回结构化错误 {ok:False, error:...}，让 L04 agent 循环回注重试
    - 可校验可白名单：动作集合固定，编号必须存在于当前观察

单测部分零 API 纯 Python 可跑；执行演示需 playwright + L00 服务。

跑法：
    cd gui-agent-lessons/03_action
    python code.py            # 跑单测（无需环境）
    python code.py --demo     # 跑执行演示（需 playwright + L00 服务 8765）
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ──────────────────────────────────────────────────────────────
# Action 数据结构
# ──────────────────────────────────────────────────────────────

@dataclass
class Action:
    """一个解析后的动作。"""
    name: str          # click / type / scroll / back / finish
    idx: int | None = None        # 元素编号（click/type 用）
    text: str | None = None       # 输入文本（type 用）或答案（finish 用）
    direction: str | None = None  # up/down（scroll 用）

    def __str__(self) -> str:
        if self.name == "click":
            return f"click({self.idx})"
        if self.name == "type":
            return f'type({self.idx}, "{self.text}")'
        if self.name == "scroll":
            return f"scroll({self.direction})"
        if self.name == "back":
            return "back()"
        if self.name == "finish":
            return f"finish({self.text})"
        return f"<unknown:{self.name}>"


# DSL 文法（正则）
_PATTERNS = [
    ("click",  re.compile(r'^click\((\d+)\)$')),
    ("type",   re.compile(r'^type\((\d+),\s*"(.*)"\)$')),
    ("scroll", re.compile(r'^scroll\((up|down)\)$')),
    ("back",   re.compile(r'^back\(\)$')),
    ("finish", re.compile(r'^finish\((.*)\)$')),
]

# 动作白名单（安全主线伏笔：动作集合固定，想加新动作必须改代码）
ACTION_WHITELIST = {"click", "type", "scroll", "back", "finish"}

# type 文本长度上限（防 LLM 输出一坨塞爆）
MAX_TYPE_LEN = 500

# 可交互元素选择器（与 L02 page_to_obs 保持一致；本地副本避免跨模块同名 import 冲突）
INTERACTIVE_SELECTOR = (
    'a, button, input, select, textarea, '
    '[role="button"], [role="link"], [role="textbox"], [role="checkbox"]'
)


# ──────────────────────────────────────────────────────────────
# 解析器
# ──────────────────────────────────────────────────────────────

def parse_action(text: str) -> Action | None:
    """把 LLM 输出的文本解析成 Action。

    匹配失败返回 None（调用方据此生成「格式错误」结构化错误）。
    允许前后空白；取第一个非空行（LLM 可能带解释）。
    """
    if not text:
        return None
    # 取第一个非空行，strip
    line = text.strip().split("\n")[0].strip()
    for name, pat in _PATTERNS:
        m = pat.match(line)
        if m:
            if name == "click":
                return Action(name="click", idx=int(m.group(1)))
            if name == "type":
                return Action(name="type", idx=int(m.group(1)), text=m.group(2))
            if name == "scroll":
                return Action(name="scroll", direction=m.group(1))
            if name == "back":
                return Action(name="back")
            if name == "finish":
                return Action(name="finish", text=m.group(1))
    return None


# ──────────────────────────────────────────────────────────────
# 校验器
# ──────────────────────────────────────────────────────────────

def validate_action(action: Action | None, elements: list[dict]) -> dict:
    """校验动作合法性。

    Args:
        action: parse_action 的结果（可能 None）
        elements: L02 page_to_obs 返回的 elements 列表（含 idx）

    Returns:
        {"ok": bool, "error": str, "action": Action}
        ok=False 时 error 是可回注给 LLM 的中文错误信息。
    """
    # 解析失败（格式错）
    if action is None:
        return {"ok": False, "error": "动作格式无法解析。请用 click(n)/type(n,\"文本\")/scroll(up|down)/back()/finish(答案) 之一。", "action": None}

    # 白名单检查（未知动作名）
    if action.name not in ACTION_WHITELIST:
        return {"ok": False, "error": f"未知动作「{action.name}」。允许的动作：{ACTION_WHITELIST}。", "action": action}

    n_elements = len(elements)

    # click/type 需校验编号存在
    if action.name in ("click", "type"):
        if action.idx is None or action.idx < 1 or action.idx > n_elements:
            return {"ok": False, "error": f"元素编号 {action.idx} 不存在，当前页只有 1-{n_elements} 号元素。请重新选择合法编号。", "action": action}

    # type 需校验文本非空且不超长
    if action.name == "type":
        if not action.text:
            return {"ok": False, "error": "type 的文本不能为空。", "action": action}
        if len(action.text) > MAX_TYPE_LEN:
            return {"ok": False, "error": f"type 的文本超长（{len(action.text)}>{MAX_TYPE_LEN}）。请缩短。", "action": action}

    # scroll 需方向合法
    if action.name == "scroll":
        if action.direction not in ("up", "down"):
            return {"ok": False, "error": f"scroll 方向非法：{action.direction}（应为 up 或 down）。", "action": action}

    # finish 需答案非空
    if action.name == "finish":
        if not action.text:
            return {"ok": False, "error": "finish 的答案不能为空。", "action": action}

    return {"ok": True, "error": "", "action": action}


# ──────────────────────────────────────────────────────────────
# 执行器
# ──────────────────────────────────────────────────────────────

def execute_action(action: Action, session, elements: list[dict]) -> dict:
    """执行已校验通过的动作。调 L01 BrowserSession。

    执行也可能失败（元素 detach/页面跳转）——同样返回结构化错误，不抛。
    Returns: {"ok": bool, "error": str, "result": str, "done": bool}
    """
    try:
        if action.name == "click":
            el = elements[action.idx - 1]
            # 优先用 id selector，否则用编号定位（重新查 DOM）
            if el.get("selector"):
                session.click(el["selector"])
            else:
                # 无 id：用 INTERACTIVE_SELECTOR 重新枚举，按编号取
                loc = session.page.locator(INTERACTIVE_SELECTOR).nth(action.idx - 1)
                loc.click()
            return {"ok": True, "error": "", "result": f"点击了 [{action.idx}] {el.get('label','')}", "done": False}

        if action.name == "type":
            el = elements[action.idx - 1]
            if el.get("selector"):
                session.type(el["selector"], action.text)
            else:
                loc = session.page.locator(INTERACTIVE_SELECTOR).nth(action.idx - 1)
                loc.fill(action.text)
            return {"ok": True, "error": "", "result": f"在 [{action.idx}] 输入了「{action.text}」", "done": False}

        if action.name == "scroll":
            dy = 800 if action.direction == "down" else -800
            session.page.mouse.wheel(0, dy)
            return {"ok": True, "error": "", "result": f"滚动 {action.direction}", "done": False}

        if action.name == "back":
            session.page.go_back()
            return {"ok": True, "error": "", "result": "后退", "done": False}

        if action.name == "finish":
            return {"ok": True, "error": "", "result": action.text, "done": True}

    except Exception as e:
        # 执行失败（元素 detach/超时）转结构化错误，不崩
        return {"ok": False, "error": f"执行失败（{type(e).__name__}: {e}）。元素可能已失效，建议重新观察页面。", "result": "", "done": False}

    return {"ok": False, "error": f"未实现的动作：{action.name}", "result": "", "done": False}


# ──────────────────────────────────────────────────────────────
# 单测（零 API）
# ──────────────────────────────────────────────────────────────

def run_unit_tests() -> int:
    """DSL 单测：合法/非法/边界。返回失败数。"""
    print("=" * 60)
    print("L03 DSL 单测（零 API 纯解析校验）")
    print("=" * 60)
    failures = 0

    def check(name: str, cond: bool, detail: str = ""):
        nonlocal failures
        mark = "✅" if cond else "❌"
        print(f"  {mark} {name}" + (f"  ({detail})" if detail and not cond else ""))
        if not cond:
            failures += 1

    # 模拟 L02 的 elements（9 个元素）
    elements = [{"idx": i, "role": "link", "label": f"元素{i}", "selector": None} for i in range(1, 10)]

    print("\n── ① 合法动作解析 ──")
    cases_ok = [
        ("click(3)", "click", 3),
        ('type(3, "查询词")', "type", 3),
        ("scroll(down)", "scroll", None),
        ("scroll(up)", "scroll", None),
        ("back()", "back", None),
        ("finish(答案是 v0.8.0)", "finish", None),
    ]
    for text, exp_name, exp_idx in cases_ok:
        a = parse_action(text)
        check(f"解析「{text}」", a is not None and a.name == exp_name,
              f"got {a}")
        if a and exp_idx is not None:
            check(f"  编号/方向正确", a.idx == exp_idx or a.direction == exp_idx)

    print("\n── ② 非法动作（格式错）──")
    cases_bad_format = [
        "click(abc)",      # 参数非整数
        "foo(1)",          # 未知动作名
        "click 3",         # 缺括号
        "type(3, 查询)",   # 缺引号
        "",                # 空
    ]
    for text in cases_bad_format:
        a = parse_action(text)
        check(f"格式非法「{text or '(空)'}」→ 解析失败", a is None, f"got {a}")

    print("\n── ③ 校验（编号越界/参数非法）──")
    # click(99) 编号越界
    a = parse_action("click(99)")
    v = validate_action(a, elements)
    check("click(99) 编号越界 → 拒", not v["ok"] and "不存在" in v["error"], v["error"])

    # click(0) 编号过小
    a = parse_action("click(0)")
    v = validate_action(a, elements)
    check("click(0) 编号过小 → 拒", not v["ok"], v["error"])

    # click(9) 合法边界
    a = parse_action("click(9)")
    v = validate_action(a, elements)
    check("click(9) 合法边界 → 通过", v["ok"], v["error"])

    # type(3, "") 文本空
    a = parse_action('type(3, "")')
    v = validate_action(a, elements)
    check('type(3,"") 文本空 → 拒', not v["ok"] and "空" in v["error"], v["error"])

    # finish() 答案空
    a = parse_action("finish()")
    v = validate_action(a, elements)
    check("finish() 答案空 → 拒", not v["ok"], v["error"])

    # 未知动作（parse 阶段就 None，但测白名单逻辑：手动构造）
    v = validate_action(Action(name="goto", idx=1), elements)
    check("goto 不在白名单 → 拒", not v["ok"] and "白名单" not in v["error"] or "未知" in v["error"], v["error"])

    print("\n── ④ 结构化错误回注演示 ──")
    a = parse_action("click(99)")
    v = validate_action(a, elements)
    print(f"  LLM 输出: click(99)")
    print(f"  校验结果: ok={v['ok']}")
    print(f"  回注错误: 「{v['error']}」")
    print(f"  → 这个错误信息会喂回 LLM，让它重新选合法编号（L04 agent 循环用）")

    print(f"\n{'='*60}")
    print(f"单测结果：{'全部通过 ✅' if failures == 0 else f'{failures} 项失败 ❌'}")
    print(f"{'='*60}")
    return failures


# ──────────────────────────────────────────────────────────────
# 执行演示（需 playwright + L00 服务）
# ──────────────────────────────────────────────────────────────

def run_demo() -> None:
    print("\n" + "=" * 60)
    print("L03 执行演示（click 进详情 + finish 提取答案）")
    print("=" * 60)
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("⚠️ playwright 未安装，跳过执行演示。")
        return

    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:8765/index.html", timeout=1).read()
    except Exception:
        print("⚠️ L00 本地服务未起，请先跑: cd 00_overview/test_pages && python -m http.server 8765")
        return

    _L01 = Path(__file__).resolve().parent.parent / "01_playwright"
    _L02 = Path(__file__).resolve().parent.parent / "02_observation"
    # 用 importlib 按路径加载，避免多目录下同名 code.py 模块冲突
    import importlib.util
    spec1 = importlib.util.spec_from_file_location("l01_code", _L01 / "code.py")
    mod1 = importlib.util.module_from_spec(spec1)
    spec1.loader.exec_module(mod1)
    BrowserSession = mod1.BrowserSession
    spec2 = importlib.util.spec_from_file_location("l02_code", _L02 / "code.py")
    mod2 = importlib.util.module_from_spec(spec2)
    # L02 的 code.py 顶部会 sys.path.insert L01 并 from code import BrowserSession；
    # 为避免它再触发同名冲突，先把 L01 放进 path（让它的 from code 命中 L01）
    sys.path.insert(0, str(_L01))
    spec2.loader.exec_module(mod2)
    page_to_obs = mod2.page_to_obs

    with BrowserSession(headless=True) as s:
        s.goto("http://127.0.0.1:8765/search.html?q=LangGraph&page=1")
        s.wait_for_selector("#results")
        obs = page_to_obs(s, include_html=False)
        els = obs["elements"]
        print(f"\n  当前观察：{len(els)} 个可交互元素")

        # 找第 1 条结果链接的编号
        target_idx = None
        for e in els:
            if "v0." in e["label"]:
                target_idx = e["idx"]
                break
        if target_idx is None:
            print("  ⚠️ 未找到结果链接")
            return

        # 演示：合法动作执行
        action = parse_action(f"click({target_idx})")
        v = validate_action(action, els)
        print(f"\n  动作: {action}  校验: {'通过' if v['ok'] else '拒绝'}")
        r = execute_action(v["action"], s, els)
        print(f"  执行: ok={r['ok']}  {r['result']}")
        s.wait_for_url("**/detail.html**")
        s.wait_for_selector("#ver")
        ver = s.extract_text("#ver", wait=False)
        date = s.extract_text("#date", wait=False)

        # 演示：finish 提交答案
        ans = f"版本 {ver}，发布于 {date}"
        action = parse_action(f"finish({ans})")
        v = validate_action(action, els)
        r = execute_action(v["action"], s, els)
        print(f"\n  动作: finish(...)  执行: done={r['done']}")
        print(f"  提交答案: {r['result']}")

        # 演示：非法动作回注
        action = parse_action("click(999)")
        v = validate_action(action, els)
        print(f"\n  动作: click(999)  校验: {'通过' if v['ok'] else '拒绝'}")
        print(f"  回注错误: 「{v['error']}」")

    print("\n💡 DSL 解析+校验+执行全链路通。L04 把这套装进 observe→think→act 循环。")


# ──────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    failures = run_unit_tests()
    if "--demo" in sys.argv:
        run_demo()
    sys.exit(1 if failures else 0)
