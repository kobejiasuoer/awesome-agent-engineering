"""L01 · Playwright 地基：确定性浏览器控制层。

核心产出：BrowserSession —— 把 Playwright sync API 封装成可复用原语。
    goto / click / type / screenshot / extract_text / 超时兜底 / 上下文管理器自动关闭

设计原则（README 详述）：
    - auto-wait 优先，显式等待补动态渲染
    - 超时兜底：动作超时不崩，抛可控异常让上层决策
    - 上下文管理器：__exit__ 一定 close()，防 chromium 进程泄漏
    - viewport 固定：保证截图/布局可复现（L05 视觉路线依赖）

零 LLM 零 API。在三个测试页上演示：
    1. slow.html  —— 动态渲染（关键内容延迟 1.5s 出现）
    2. popup.html —— 弹窗劫持（遮罩盖正文，必须先点同意）
    3. L00 search.html —— 确定性操作全链路（goto→type→click→翻页→extract）

跑法：
    # 先起两个本地服务（另开终端）
    cd gui-agent-lessons/00_overview/test_pages && python -m http.server 8765
    cd gui-agent-lessons/01_playwright/test_pages && python -m http.server 8766

    cd gui-agent-lessons/01_playwright
    python code.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Windows 编码兜底（任务书硬约束）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
L00_BASE = "http://127.0.0.1:8765"   # L00 的 test_pages
L01_BASE = "http://127.0.0.1:8766"   # L01 的 test_pages


# ──────────────────────────────────────────────────────────────
# BrowserSession：可复用的浏览器控制原语
# ──────────────────────────────────────────────────────────────

class BrowserSession:
    """封装 Playwright sync API 的可复用浏览器会话。

    用法：
        with BrowserSession(headless=True) as s:
            s.goto(url)
            text = s.extract_text("#ver")
    退出 with 块时自动 close()，即使中途抛异常也保证资源释放。

    为什么用上下文管理器：chromium 是子进程，不 close 就泄漏——
    跑几次基准内存就爆。__exit__ 兜底是最可靠的释放点。
    """

    def __init__(self, headless: bool = True, viewport: dict | None = None,
                 default_timeout: int = 10000):
        """Args:
            headless: 无头模式（测试/基准用 True，调试用 False）
            viewport: 固定视口（默认 1280x800，保证截图/布局可复现）
            default_timeout: 默认动作超时（ms），超时抛 TimeoutError
        """
        self.headless = headless
        self.viewport = viewport or {"width": 1280, "height": 800}
        self.default_timeout = default_timeout
        self._pw = None
        self._browser = None
        self._page = None

    # ── 上下文管理器 ──
    def __enter__(self) -> "BrowserSession":
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page(viewport=self.viewport)
        self._page.set_default_timeout(self.default_timeout)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        """关闭页面+浏览器+playwright，保证无残留进程。"""
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._page = self._browser = self._pw = None

    @property
    def page(self):
        if self._page is None:
            raise RuntimeError("BrowserSession 未启动：请在 `with` 块内使用")
        return self._page

    @property
    def url(self) -> str:
        return self.page.url

    # ── 原语 ──
    def goto(self, url: str, wait_until: str = "domcontentloaded"):
        """打开页面。wait_until=domcontentloaded 比 load 更可靠（本地 server 不总发 load）。"""
        self.page.goto(url, wait_until=wait_until)

    def click(self, selector: str, timeout: int | None = None):
        """点击。auto-wait 内置（等元素 visible+enabled+stable）。
        超时抛 Playwright TimeoutError——上层可捕获决定重试/换策略（L04/L06）。"""
        self.page.click(selector, timeout=timeout or self.default_timeout)

    def type(self, selector: str, text: str, timeout: int | None = None):
        """输入文本。auto-wait 等元素可输入。"""
        self.page.fill(selector, text, timeout=timeout or self.default_timeout)

    def extract_text(self, selector: str, wait: bool = True,
                     timeout: int | None = None) -> str:
        """提取元素文本。
        wait=True 时先 wait_for_selector——治动态渲染（元素 JS 延迟生成，auto-wait 救不了）。
        """
        if wait:
            self.page.wait_for_selector(selector, timeout=timeout or self.default_timeout)
        return self.page.inner_text(selector).strip()

    def screenshot(self, path: str | Path, full_page: bool = False):
        """截图。L05 视觉路线用。viewport 已固定，截图尺寸可复现。"""
        self.page.screenshot(path=str(path), full_page=full_page)

    def wait_for_selector(self, selector: str, timeout: int | None = None):
        """显式等待元素出现（动态渲染兜底）。"""
        self.page.wait_for_selector(selector, timeout=timeout or self.default_timeout)

    def wait_for_url(self, pattern: str, timeout: int | None = None):
        """等导航落定（点击 <a> 触发整页跳转后用）。"""
        self.page.wait_for_url(pattern, wait_until="domcontentloaded",
                               timeout=timeout or self.default_timeout)


# ──────────────────────────────────────────────────────────────
# 演示：三个测试页上的确定性操作
# ──────────────────────────────────────────────────────────────

def _server_up(base: str) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(base + "/", timeout=1).read()
        return True
    except Exception:
        return False


def demo_slow_page(s: BrowserSession) -> dict:
    """慢加载页：关键内容延迟 1.5s 由 JS 渲染。
    演示：显式 wait_for_selector 治动态渲染（sleep 会脆，auto-wait 救不了未生成元素）。
    """
    print("\n── demo 1: 慢加载页（动态渲染）──")
    s.goto(f"{L01_BASE}/slow.html")
    # ❌ 若直接 inner_text('#ver') 会抛——元素还没生成
    # ✅ 显式等元素出现
    t0 = time.time()
    s.wait_for_selector("#ver", timeout=5000)
    ver = s.extract_text("#ver", wait=False)
    date = s.extract_text("#date", wait=False)
    elapsed = time.time() - t0
    print(f"  等待 {elapsed:.2f}s 后提取到：版本={ver}, 日期={date}")
    return {"page": "slow", "version": ver, "date": date, "waited_s": round(elapsed, 2)}


def demo_popup_page(s: BrowserSession) -> dict:
    """弹窗劫持页：遮罩盖住正文，不点「同意」点不到下面。
    演示：弹窗处理——先关遮罩，再交互正文。
    """
    print("\n── demo 2: 弹窗劫持页 ──")
    s.goto(f"{L01_BASE}/popup.html")
    # 遮罩在，#content 是 display:none，#ver 虽在 DOM 但不可见
    # 点「同意」关遮罩
    s.click("#accept")
    s.wait_for_selector("#content")  # 等正文显示
    ver = s.extract_text("#ver", wait=False)
    date = s.extract_text("#date", wait=False)
    print(f"  关弹窗后提取到：版本={ver}, 日期={date}")
    return {"page": "popup", "version": ver, "date": date}


def demo_deterministic_flow(s: BrowserSession) -> dict:
    """L00 search.html：确定性操作全链路（goto→type→submit→翻页→进详情→提取）。
    演示：BrowserSession 把 L00 写死脚本泛化成原语调用。
    """
    print("\n── demo 3: 确定性操作全链路（L00 search.html）──")
    s.goto(f"{L00_BASE}/index.html")
    s.type('input[name="q"]', "LangGraph")
    s.click('button[type="submit"]')
    s.wait_for_url("**/search.html**")
    # 翻第 2 页（用 href 精确定位，不用 has-text——L00 踩过的歧义坑）
    s.click('#pager a[href*="page=2"]')
    s.wait_for_url("**page=2**")
    # 点第 1 条结果进详情
    first = s.page.locator('#results .result a').first
    href = first.get_attribute("href") or ""
    first.click()
    s.wait_for_url("**/detail.html**")
    s.wait_for_selector("#tag")
    tag = s.extract_text("#tag", wait=False)
    ver = s.extract_text("#ver", wait=False)
    date = s.extract_text("#date", wait=False)
    print(f"  全链路完成：tag={tag}, version={ver}, date={date}")
    return {"page": "flow", "tag": tag, "version": ver, "date": date, "detail_href": href}


# ──────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("L01 BrowserSession：确定性浏览器控制层")
    print("=" * 60)

    # 检查 playwright
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("\n⚠️ playwright 未安装，跳过演示。安装见 README。")
        return

    # 检查本地服务
    l00_up = _server_up(L00_BASE)
    l01_up = _server_up(L01_BASE)
    if not l01_up:
        print(f"\n⚠️ L01 本地服务未起（{L01_BASE}），请先跑:")
        print(f"   cd gui-agent-lessons/01_playwright/test_pages && python -m http.server 8766")
        return

    # 上下文管理器：保证 close()
    results = []
    with BrowserSession(headless=True) as s:
        print(f"\n✅ 浏览器已启动（headless, viewport=1280x800）")
        results.append(demo_slow_page(s))
        results.append(demo_popup_page(s))
        if l00_up:
            results.append(demo_deterministic_flow(s))
        else:
            print(f"\n── demo 3 跳过：L00 本地服务未起（{L00_BASE}）──")

    print(f"\n✅ 浏览器已关闭（上下文管理器保证资源释放，无残留进程）")

    # ── 汇总 ──
    print(f"\n── 演示汇总 ──────────────────────────────────────")
    for r in results:
        print(f"  {r['page']:<8} → {r}")
    print(f"\n💡 三个演示全绿 = 手稳。L02 在这之上加观察空间，L03 加动作 DSL。")


if __name__ == "__main__":
    main()
