"""L00 · 裸基线：证明「搜索摘要 ≠ 会上网」，并展示浏览器脚本能拿到什么。

本脚本做两件事：
    1. 用 mock 搜索结果模拟 research-assistant 的 web_search 跑硬任务（翻页取证），
       记录「拿到了什么 / 拿不到什么」存 baseline_gui.jsonl —— 全程对照基线。
    2. 用一段【写死的】Playwright 脚本手工完成本地镜像版任务
       （搜索→点结果→翻页→进详情→提取版本号/日期），
       展示搜索 API 与浏览器之间的 gap。这段脚本就是 L01 要泛化的东西。

为什么用 mock：
    - 真实 DuckDuckGo 摘要内容会变、国内网络不稳，但「摘要拿不到翻页/详情证据」
      是搜索 API 的能力边界（结构性问题），不依赖具体内容。用 mock 省钱且稳定复现。
    - 诚实标注：本机跑出的演示数字附复现命令，结论不夸大。

跑法：
    # 先起本地测试页服务（另开一个终端）
    cd gui-agent-lessons/00_overview/test_pages
    python -m http.server 8765

    cd gui-agent-lessons/00_overview
    python code.py

环境要求：
    - playwright + chromium（写死脚本部分需要；未装则跳过并提示，基线部分仍产出）
    - 本地 http.server 跑在 8765（写死脚本部分需要；未跑则跳过并提示）
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Windows 编码兜底（任务书硬约束）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT_DIR = Path(__file__).resolve().parent
TEST_PAGES = OUT_DIR / "test_pages"
BASELINE_FILE = OUT_DIR / "baseline_gui.jsonl"
LOCAL_BASE = "http://127.0.0.1:8765"

# 默认硬任务（任务书 1.6，可配置）
DEFAULT_TASK = "对比 LangGraph 最近几次 release 的版本号、发布日期与主要变更"


# ──────────────────────────────────────────────────────────────
# Part 1 · 裸基线：mock web_search 跑硬任务，记录 gap
# ──────────────────────────────────────────────────────────────

def mock_web_search(query: str) -> str:
    """模拟 research-assistant 的 web_search（DuckDuckGo 摘要）。

    关键：返回的是【摘要片段】，不含详情页结构化字段、不含翻页内容、
    不带访问时间戳。这正是搜索 API 的能力边界。
    """
    # 模拟 DuckDuckGo 返回的 3 条摘要（与真实搜索同构：标题 + 片段 + 链接）
    return (
        "[1] LangGraph\n"
        "    LangGraph 是基于图的状态化 Agent 编排框架，近期持续更新发布。\n"
        "    来源: https://github.com/langchain-ai/langgraph/releases\n"
        "[2] LangGraph v0.2 released\n"
        "    新版本改进了 checkpoint 与并行子图，具体变更见 release notes。\n"
        "    来源: https://github.com/langchain-ai/langgraph\n"
        "[3] LangGraph documentation\n"
        "    官方文档涵盖 graph/state/checkpointer 等概念。\n"
        "    来源: https://langchain-ai.github.io/langgraph/\n"
    )


def run_baseline(task: str) -> dict:
    """用 web_search 摘要跑硬任务，返回「拿到了什么/拿不到什么」的 gap 诊断。

    gap 判定依据：硬任务要求的四样东西，摘要里有没有。
    """
    query = "LangGraph release version date changelog"
    snippet = mock_web_search(query)

    # 硬任务要求 vs 摘要实际有的
    has_title = "LangGraph" in snippet
    has_link = "github.com" in snippet
    # 摘要里【没有】的：
    has_version_number = bool(__import__("re").search(r"v0\.\d+\.\d+", snippet))  # 无具体版本号
    has_release_date = bool(__import__("re").search(r"\d{4}-\d{2}-\d{2}", snippet))  # 无发布日期
    has_changelog = "变更要点" in snippet  # 摘要只有「见 release notes」，无具体要点
    has_page2 = False  # 翻页内容必然没有
    has_access_time = False  # 摘要只有搜索时间，无页面访问时间

    record = {
        "run": "baseline_web_search",
        "task": task,
        "query": query,
        "snippet": snippet,
        "gap": {
            "has_title": has_title,             # ✅ 摘要有
            "has_link": has_link,               # ✅ 摘要有
            "has_version_number": has_version_number,   # ❌ 摘要没有
            "has_release_date": has_release_date,       # ❌ 摘要没有
            "has_changelog_details": has_changelog,     # ❌ 摘要没有
            "has_page2_content": has_page2,             # ❌ 翻页必然没有
            "has_access_timestamp": has_access_time,    # ❌ 摘要没有
        },
        "verdict": (
            "搜索摘要只能拿到标题+片段+链接，"
            "拿不到版本号/发布日期/变更要点/翻页内容/访问时间戳"
        ),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    return record


# ──────────────────────────────────────────────────────────────
# Part 2 · 写死脚本：真开浏览器完成本地镜像版任务
# 这段就是 L01 要泛化成 BrowserSession 的东西。
# ──────────────────────────────────────────────────────────────

def _local_server_up() -> bool:
    """探测本地测试页服务是否在跑。"""
    try:
        urllib.request.urlopen(f"{LOCAL_BASE}/index.html", timeout=1).read()
        return True
    except Exception:
        return False


def hardcoded_browser_script() -> dict:
    """【写死的】Playwright 脚本：搜索→点结果→翻页→进详情→提取证据。

    每一步都是硬编码的选择器和动作，没有 LLM、没有泛化。
    它的存在只为展示「浏览器能拿到搜索 API 拿不到的东西」。
    L01 会把它拆成 goto/click/type/extract 等可复用原语。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "reason": "playwright 未安装，跳过写死脚本（基线部分不受影响）"}

    if not _local_server_up():
        return {"ok": False, "reason": f"本地服务未起，请先跑: cd test_pages && python -m http.server 8765"}

    evidence = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            # Step 1: 打开首页
            page.goto(f"{LOCAL_BASE}/index.html", wait_until="domcontentloaded")
            # Step 2: 在搜索框输入并提交（表单 GET 提交 → 导航到 search.html?q=LangGraph）
            page.fill('input[name="q"]', "LangGraph")
            page.click('button[type="submit"]')
            # 等表单提交后的导航落定（domcontentloaded 比 load 更可靠，本地 server 不总发 load）
            page.wait_for_url("**/search.html**", wait_until="domcontentloaded")
            # Step 3: 翻到第 2 页（点分页器里 href 含 page=2 的 <a>，触发导航）
            #   注意：不能用 a:has-text("2")——结果文本里也可能含"2"导致匹配多元素。
            #   用 href 属性精确定位是「确定性操作」的示范（L01 会强调这个原则）。
            page.locator('#pager a[href*="page=2"]').first.click()
            page.wait_for_url("**page=2**", wait_until="domcontentloaded")
            # Step 4: 点第 2 页第 1 条结果进详情（同样导航到 detail.html?id=...）
            first_link = page.locator('#results .result a').first
            href = first_link.get_attribute("href") or ""
            first_link.click()
            page.wait_for_url("**/detail.html**", wait_until="domcontentloaded")
            # Step 5: 提取结构化字段（版本号/日期/变更要点）
            page.wait_for_selector("#tag")
            tag = page.inner_text("#tag")
            ver = page.inner_text("#ver")
            date = page.inner_text("#date")
            notes = page.inner_text("#notes")
            access_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            evidence.append({
                "tag": tag,
                "version": ver,
                "date": date,
                "changelog": notes,
                "url": f"{LOCAL_BASE}/detail.html" + (href.split("detail.html")[1] if "detail.html" in href else ""),
                "access_time": access_time,
                "from_page": 2,
            })
        finally:
            browser.close()

    return {"ok": True, "evidence": evidence}


# ──────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────

def main(task: str = DEFAULT_TASK):
    print(f"{'='*64}")
    print(f"L00 裸基线：硬任务「{task}」")
    print(f"{'='*64}\n")

    # ── Part 1：web_search 摘要基线 ──────────────────────────
    print("── Part 1: web_search 摘要基线 ──────────────────────")
    record = run_baseline(task)
    print(f"  模拟搜索: {record['query']}")
    print(f"  摘要片段:\n{record['snippet']}")
    print(f"  ── gap 诊断（硬任务要求 vs 摘要实际有）──")
    for k, v in record["gap"].items():
        mark = "✅有" if v else "❌无"
        print(f"    {mark}  {k}")
    print(f"\n  结论: {record['verdict']}")

    # 存基线（全程对照，L11 收益表对照它算增量）
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"\n  ✅ 基线已存: {BASELINE_FILE}")

    # ── Part 2：写死浏览器脚本展示 gap ──────────────────────
    print(f"\n── Part 2: 写死 Playwright 脚本（L01 要泛化的东西）──")
    result = hardcoded_browser_script()
    if not result["ok"]:
        print(f"  ⚠️ 跳过: {result['reason']}")
        print(f"     （不影响基线产出，L01 会装好环境再跑）")
    else:
        print(f"  浏览器执行: 搜索→翻页→进详情→提取证据")
        for ev in result["evidence"]:
            print(f"  ── 证据 ──")
            print(f"    tag:        {ev['tag']}")
            print(f"    version:    {ev['version']}")
            print(f"    date:       {ev['date']}")
            print(f"    changelog:  {ev['changelog'][:60]}...")
            print(f"    url:        {ev['url']}")
            print(f"    access_time:{ev['access_time']}")
            print(f"    from_page:  第 {ev['from_page']} 页（翻页拿到的）")

    # ── 对照表 ──────────────────────────────────────────────
    print(f"\n── 对照表：搜索摘要 vs 浏览器 ──────────────────────")
    print(f"  {'能力':<20} {'web_search 摘要':<18} {'写死浏览器脚本'}")
    rows = [
        ("标题/片段", "✅", "✅"),
        ("来源链接", "✅", "✅"),
        ("版本号", "❌", "✅" if result.get("ok") else "（需环境）"),
        ("发布日期", "❌", "✅" if result.get("ok") else "（需环境）"),
        ("变更要点", "❌", "✅" if result.get("ok") else "（需环境）"),
        ("翻页内容", "❌", "✅" if result.get("ok") else "（需环境）"),
        ("访问时间戳", "❌", "✅" if result.get("ok") else "（需环境）"),
    ]
    for name, a, b in rows:
        print(f"  {name:<20} {a:<18} {b}")

    print(f"\n💡 这个 gap 就是 GUI agent 的价值证明。")
    print(f"   baseline_gui.jsonl 是全程对照——L09 落地后看 browse 工具多拿到了什么，")
    print(f"   L11 收益表对照它算增量。")


if __name__ == "__main__":
    main()
