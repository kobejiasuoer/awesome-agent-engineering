"""L02 · 观察空间：page_to_obs 三种页面表示 + token 对比 + 编号稳定性。

核心产出：page_to_obs() —— 把页面表示成三种形式：
    1. raw_html       原始 HTML（token 爆炸、噪音大）
    2. element_list   可交互元素编号列表（本课主路线：省 token + 保留交互性）
    3. plain_text     纯文本正文（丢交互性，只配读）

对比维度：token 数（字符数÷4 粗估）。编号列表比原始 HTML 省一个数量级。
编号稳定性：重扫同一页编号一致（确定性）；操作后重扫编号重分配（动态性）。

复用 L01 的 BrowserSession（sys.path 加 L01）。

跑法：
    cd gui-agent-lessons/00_overview/test_pages && python -m http.server 8765
    cd gui-agent-lessons/02_observation
    python code.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_L01 = _HERE.parent / "01_playwright"
sys.path.insert(0, str(_L01))
from code import BrowserSession  # 复用 L01 的控制层  # noqa: E402

L00_BASE = "http://127.0.0.1:8765"

# 可交互元素选择器（可访问性树思路的工程落地）
INTERACTIVE_SELECTOR = (
    'a, button, input, select, textarea, '
    '[role="button"], [role="link"], [role="textbox"], [role="checkbox"]'
)


# ──────────────────────────────────────────────────────────────
# page_to_obs：三种表示
# ──────────────────────────────────────────────────────────────

def _role_of(el) -> str:
    """推断元素 role（标签 → role 映射，简化版可访问性树）。"""
    tag = el.evaluate("e => e.tagName.toLowerCase()")
    role = el.get_attribute("role") or ""
    if role:
        return role
    return {
        "a": "link", "button": "button", "input": "textbox",
        "select": "combobox", "textarea": "textbox",
    }.get(tag, tag)


def _label_of(el) -> str:
    """元素的可读标签（文本/value/aria-label/href）。"""
    text = (el.inner_text() or "").strip()
    if text:
        return text[:60]
    val = el.get_attribute("value") or ""
    if val:
        return val[:60]
    aria = el.get_attribute("aria-label") or ""
    if aria:
        return aria[:60]
    href = el.get_attribute("href") or ""
    return href[:60] if href else "(空)"


def page_to_obs(session: BrowserSession, include_html: bool = True) -> dict:
    """把当前页面表示成三种形式。

    Returns:
        {
          "raw_html": str,           # 原始 HTML（可选，最贵）
          "element_list": str,       # 元素编号列表（主路线）
          "plain_text": str,         # 纯文本正文
          "elements": [dict, ...],   # 结构化元素（含编号/role/label/selector）
        }
    """
    page = session.page

    # ── ① 原始 HTML ──
    raw_html = page.content() if include_html else ""

    # ── ② 元素编号列表 ──
    elements = []
    els = page.locator(INTERACTIVE_SELECTOR)
    count = els.count()
    for i in range(count):
        el = els.nth(i)
        try:
            role = _role_of(el)
            label = _label_of(el)
            # 生成稳定 selector（编号歧义时后备）：优先 id，否则 tag+文本
            sel = f"#{el.get_attribute('id')}" if el.get_attribute("id") else None
            elements.append({
                "idx": i + 1, "role": role, "label": label,
                "selector": sel,  # None 表示无稳定 id，靠编号
            })
        except Exception:
            continue  # 跳过已 detach 的元素

    el_lines = [f'[{e["idx"]}] {e["role"]} "{e["label"]}"' for e in elements]
    # 正文摘要（非交互的可见文本，截断）
    body_text = page.inner_text("body")[:200].replace("\n", " ")
    element_list = "可交互元素：\n" + "\n".join(el_lines) + f"\n\n正文摘要：{body_text}"

    # ── ③ 纯文本正文 ──
    plain_text = page.inner_text("body")

    return {
        "raw_html": raw_html,
        "element_list": element_list,
        "plain_text": plain_text,
        "elements": elements,
    }


# ──────────────────────────────────────────────────────────────
# token 估算
# ──────────────────────────────────────────────────────────────

def est_tokens(text: str) -> int:
    """粗估 token 数：字符数 ÷ 4（中文偏保守，够做对比）。
    真实场景用 tiktoken，本课只比较量级，粗估够用。"""
    return max(1, len(text) // 4)


def token_comparison(obs: dict) -> None:
    """打印三种表示的 token 对比表。"""
    print("\n── token 对比表（同一页面的三种表示）──")
    rows = [
        ("原始 HTML", obs["raw_html"]),
        ("元素编号列表", obs["element_list"]),
        ("纯文本正文", obs["plain_text"]),
    ]
    print(f"  {'表示':<16} {'字符数':>8} {'≈token':>8}")
    for name, text in rows:
        print(f"  {name:<16} {len(text):>8} {est_tokens(text):>8}")
    html_t = est_tokens(obs["raw_html"])
    el_t = est_tokens(obs["element_list"])
    ratio = html_t / el_t if el_t else 0
    print(f"\n  元素编号列表比原始 HTML 省 ~{ratio:.1f}x token")


# ──────────────────────────────────────────────────────────────
# 编号稳定性
# ──────────────────────────────────────────────────────────────

def test_index_stability(session: BrowserSession) -> None:
    """编号稳定性单测：
    - 确定性：重扫同一页（不操作），编号应一致。
    - 动态性：操作后页面变了，编号重分配（不跨步引用旧编号）。
    """
    print("\n── 编号稳定性单测 ──")

    # ① 确定性：扫两次同一页，编号应一致
    session.goto(f"{L00_BASE}/index.html")
    obs1 = page_to_obs(session, include_html=False)
    labels1 = [e["label"] for e in obs1["elements"]]
    obs2 = page_to_obs(session, include_html=False)
    labels2 = [e["label"] for e in obs2["elements"]]
    stable = labels1 == labels2
    print(f"  ① 确定性（重扫同一页编号一致）: {'✅ 通过' if stable else '❌ 失败'}")
    print(f"     首次扫描: {labels1}")
    print(f"     再次扫描: {labels2}")

    # ② 动态性：操作后页面跳转，编号重分配
    session.type('input[name="q"]', "LangGraph")
    session.click('button[type="submit"]')
    session.wait_for_url("**/search.html**")
    obs3 = page_to_obs(session, include_html=False)
    labels3 = [e["label"] for e in obs3["elements"]]
    changed = labels1 != labels3  # 跳转后元素变了
    print(f"\n  ② 动态性（操作后编号重分配）: {'✅ 通过' if changed else '❌ 失败'}")
    print(f"     跳转后扫描: {labels3[:4]}...（共 {len(labels3)} 个元素）")
    print(f"     → 编号 1 不再指首页的链接A，而是搜索结果的第1条")


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
    print("=" * 60)
    print("L02 观察空间：page_to_obs 三种表示 + token 对比")
    print("=" * 60)

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("\n⚠️ playwright 未安装，跳过。安装见 L01 README。")
        return
    if not _server_up():
        print(f"\n⚠️ L00 本地服务未起（{L00_BASE}），请先跑:")
        print(f"   cd gui-agent-lessons/00_overview/test_pages && python -m http.server 8765")
        return

    with BrowserSession(headless=True) as s:
        s.goto(f"{L00_BASE}/search.html?q=LangGraph&page=1")
        s.wait_for_selector("#results")

        obs = page_to_obs(s)

        # 打印三种表示样例（截断）
        print("\n── ① 原始 HTML（前 300 字符）──")
        print(obs["raw_html"][:300] + " ...")
        print("\n── ② 元素编号列表（主路线，全文）──")
        print(obs["element_list"])
        print("\n── ③ 纯文本正文（前 300 字符）──")
        print(obs["plain_text"][:300] + " ...")

        # token 对比
        token_comparison(obs)

        # 编号稳定性
        test_index_stability(s)

    print(f"\n💡 元素编号列表是观察空间主路线：省 token + 保留交互性。")
    print(f"   编号 = L03 动作 DSL 的目标（click(3) 点编号3），观察→行动的桥梁在此搭好。")


if __name__ == "__main__":
    main()
