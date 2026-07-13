"""浏览器工具：让 researcher 从「只看搜索摘要」升级到「真开浏览器取证」。

GUI Agent 课程（gui-agent-lessons L01-L08）的落地产物：
    把课程里手写的 BrowserSession + 观察空间 + 动作 DSL + 可靠性层 + 安全层
    封成生产化 async 工具，接进 researcher 节点。

设计（任务书 1.2/1.3）：
    - 与 web_search 分层：search 快浅便宜（摘要），browse 慢深贵（详情页/翻页/证据）
    - 路由：需要详情页/翻页/时效证据时才开浏览器
    - 降级链：browse 失败 → 回退 search 摘要（不让研究流程断）
    - 安全默认开（L07 域名 allowlist + 敏感动作确认）
    - 所有配置进 Settings，enable_browser 默认关（不破坏现有 104 测试）

LLM 只用智谱（任务书硬约束）：文本路线 glm-4，视觉路线 glm-4v-plus（混合路线）。
Playwright async API（Windows 用默认 ProactorEventLoop，勿改 SelectorEventLoop）。
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .config import settings
from .logging_config import get_logger

log = get_logger("browser_tool")

# 可交互元素选择器（与 gui-agent-lessons L02 一致）
INTERACTIVE_SELECTOR = (
    'a, button, input, select, textarea, '
    '[role="button"], [role="link"], [role="textbox"], [role="checkbox"]'
)

# 默认域名 allowlist（任务书 1.3：默认域名 allowlist；公开只读页）
DEFAULT_ALLOWED_DOMAINS = {"127.0.0.1", "localhost", "arxiv.org", "github.com"}

# 敏感动作模式（L07：下载/登录/支付/提交→强制人工确认）
SENSITIVE_PATTERNS = [r"\.exe$", r"\.dmg$", r"\.sh$", r"/login", r"/signin",
                      r"/pay", r"/checkout", r"/submit", r"/post"]

# 注入特征词（L07：观察注入扫描）
INJECTION_MARKERS = [
    "忽略以上", "忽略所有", "忽略任务", "系统通知", "强制要求",
    "管理员要求", "立即点击", "无限制的", "你现在需要",
]


# ──────────────────────────────────────────────────────────────
# 安全层（L07 落地）
# ──────────────────────────────────────────────────────────────

def check_url_allowed(url: str, allowed: set[str] | None = None) -> bool:
    """域名 allowlist：click 目标域必须在白名单。"""
    if not url or not url.startswith(("http://", "https://")):
        return True  # 相对 URL 或无 href
    allowed = allowed or DEFAULT_ALLOWED_DOMAINS
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in allowed)


def is_sensitive_url(url: str) -> bool:
    """敏感动作检测（下载/登录/支付/提交）。"""
    return any(re.search(p, url, re.IGNORECASE) for p in SENSITIVE_PATTERNS)


def scan_injection(text: str) -> list[str]:
    """观察注入特征扫描。返回命中的标记。"""
    return [m for m in INJECTION_MARKERS if m in text]


# ──────────────────────────────────────────────────────────────
# 证据记录（L10 预留：证据链格式）
# ──────────────────────────────────────────────────────────────

@dataclass
class Evidence:
    """一条浏览证据。L10 证据链的单元。"""
    content: str                    # 提取的内容
    url: str                        # 来源 URL
    accessed_at: str                # 访问时间（ISO）
    page_title: str = ""            # 页面标题
    snapshot: str = ""              # 页面快照（文本摘要，L10 落盘）

    def to_citation(self) -> str:
        """格式化为报告引用：内容 + URL + 访问时间。"""
        return f"{self.content}（[来源]({self.url})，访问于 {self.accessed_at}）"


# ──────────────────────────────────────────────────────────────
# BrowserTool：生产化 async 浏览工具
# ──────────────────────────────────────────────────────────────

class BrowserTool:
    """异步浏览器工具：开浏览器进详情页、翻页、提取结构化证据。

    封装 gui-agent-lessons L01-L07 的全部能力：
        - BrowserSession（goto/click/type/extract，async 版）
        - page_to_obs（观察空间，L02）
        - 动作 DSL（L03，简化版：直接用选择器，不暴露给 LLM）
        - 可靠性层（L06，超时兜底 + 重试预算）
        - 安全层（L07，allowlist + 敏感确认，默认开）

    用法（researcher 节点）：
        tool = get_browser_tool()  # 单例，enable_browser=false 时返回 None
        if tool:
            evidence = await tool.browse_for_evidence(query, urls)
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._allowed_domains = set(settings.browser_domain_allowlist) if settings.browser_domain_allowlist else DEFAULT_ALLOWED_DOMAINS
        self._max_steps = settings.browser_max_steps
        self._timeout = settings.browser_page_timeout
        self._headless = settings.browser_headless

    async def _ensure_browser(self):
        """懒启动 Playwright + chromium。"""
        if self._browser is not None:
            return
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        log.info("browser_tool: chromium 已启动")

    async def close(self):
        """关闭浏览器。"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def _new_page(self):
        await self._ensure_browser()
        page = await self._browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_default_timeout(self._timeout * 1000)
        return page

    async def _safe_goto(self, page, url: str) -> bool:
        """安全导航：allowlist 检查 + 超时兜底。返回是否成功。"""
        if not check_url_allowed(url, self._allowed_domains):
            log.warning(f"browser_tool: 域名拦截 {url}")
            return False
        try:
            await page.goto(url, wait_until="domcontentloaded",
                            timeout=self._timeout * 1000)
            return True
        except Exception as e:
            log.warning(f"browser_tool: goto 失败 {url}: {e}")
            return False

    async def extract_from_page(self, url: str, selectors: list[str] | None = None) -> Evidence | None:
        """打开一个页面，提取结构化内容作为证据。

        Args:
            url: 目标页 URL（必须过 allowlist）
            selectors: 要提取的 CSS 选择器列表（None=自动提取正文）
        Returns:
            Evidence 或 None（失败/被拦）
        """
        from datetime import datetime, timezone
        page = await self._new_page()
        try:
            if not await self._safe_goto(page, url):
                return None
            # 等正文渲染
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass

            # 提取内容
            if selectors:
                parts = []
                for sel in selectors:
                    try:
                        parts.append(await page.inner_text(sel))
                    except Exception:
                        continue
                content = "\n".join(parts)
            else:
                content = await page.inner_text("body")
            content = (content or "").strip()[:2000]  # 截断防过长

            # 注入扫描（L07）
            hits = scan_injection(content)
            if hits:
                log.warning(f"browser_tool: 检出注入特征 {hits} @ {url}")
                content = f"[⚠️ 本页内容含疑似注入标记 {hits}，已隔离标注]\n{content}"

            title = await page.title()
            accessed = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            return Evidence(content=content, url=url, accessed_at=accessed,
                            page_title=title, snapshot=content[:200])
        except Exception as e:
            log.warning(f"browser_tool: 提取失败 {url}: {e}")
            return None
        finally:
            await page.close()

    async def browse_for_evidence(self, query: str, urls: list[str],
                                  max_pages: int = 3) -> list[Evidence]:
        """为研究问题浏览多个详情页取证。

        Args:
            query: 研究子问题（用于日志）
            urls: 候选详情页 URL 列表（通常来自 web_search 的来源链接）
            max_pages: 最多浏览几个页（成本控制）
        Returns:
            证据列表（失败的页跳过，不抛）
        """
        evidences: list[Evidence] = []
        # 安全：只浏览 allowlist 内的 URL
        safe_urls = [u for u in urls if check_url_allowed(u, self._allowed_domains)]
        if len(safe_urls) < len(urls):
            log.info(f"browser_tool: 过滤掉 {len(urls)-len(safe_urls)} 个非 allowlist URL")
        # 成本：限制页数
        safe_urls = safe_urls[:max_pages]
        log.info(f"browser_tool: 为「{query[:30]}」浏览 {len(safe_urls)} 页")

        for url in safe_urls:
            ev = await self.extract_from_page(url)
            if ev:
                evidences.append(ev)
        return evidences

    def format_evidence_for_prompt(self, evidences: list[Evidence]) -> str:
        """把证据格式化成 researcher prompt 可用的文本。"""
        if not evidences:
            return ""
        lines = ["【浏览器取证（详情页提取，带 URL+访问时间）】"]
        for i, ev in enumerate(evidences, 1):
            lines.append(f"[证据{i}] {ev.page_title}")
            lines.append(f"  内容: {ev.content[:300]}")
            lines.append(f"  来源: {ev.url}")
            lines.append(f"  访问时间: {ev.accessed_at}")
        return "\n".join(lines)

    async def deep_browse(self, query: str, entry_url: str, max_steps: int = 4,
                          link_hint: str = "") -> list[Evidence]:
        """多步深度浏览：从入口页出发，跟链接跨页取证（L10 证据链）。

        与 browse_for_evidence 的区别：
            - browse_for_evidence: 并行开多个独立详情页（广度）
            - deep_browse: 从一个入口跟链接深入（深度），适合「翻页/跟链接」场景

        Args:
            query: 研究子问题
            entry_url: 入口页 URL（如搜索结果列表页）
            max_steps: 最多跟几步链接（成本控制）
            link_hint: 链接提示词（如含"release/版本"的链接优先跟）
        Returns:
            证据链（每步一条 Evidence，按访问顺序）
        """
        evidences: list[Evidence] = []
        page = await self._new_page()
        current_url = entry_url
        try:
            for step in range(max_steps):
                if not check_url_allowed(current_url, self._allowed_domains):
                    log.info(f"deep_browse: 域名拦截，停在第{step}步 {current_url}")
                    break
                if not await self._safe_goto(page, current_url):
                    break
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass

                from datetime import datetime, timezone
                content = await page.inner_text("body")
                content = (content or "").strip()[:2000]
                title = await page.title()
                accessed = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                # 注入扫描
                hits = scan_injection(content)
                if hits:
                    log.warning(f"deep_browse: 检出注入 {hits} @ {current_url}")
                    content = f"[⚠️ 注入隔离] {content}"
                evidences.append(Evidence(
                    content=content, url=current_url, accessed_at=accessed,
                    page_title=title, snapshot=content[:200]))

                # 找下一步要跟的链接（含 hint 的优先）
                next_url = await self._pick_next_link(page, link_hint, self._allowed_domains)
                if not next_url:
                    log.info(f"deep_browse: 第{step}步无更多可跟链接，停")
                    break
                # 相对 URL 解析
                if not next_url.startswith(("http://", "https://")):
                    next_url = f"{urlparse(current_url).scheme}://{urlparse(current_url).hostname}" + next_url
                current_url = next_url
        finally:
            await page.close()
        log.info(f"deep_browse: 为「{query[:30]}」跟了 {len(evidences)} 步")
        return evidences

    async def _pick_next_link(self, page, hint: str, allowed: set[str]) -> str | None:
        """从当前页挑下一个要跟的链接（含 hint 优先，过 allowlist）。"""
        try:
            links = await page.locator("a").all()
            for link in links:
                href = await link.get_attribute("href")
                if not href or href.startswith("#"):
                    continue
                # 绝对化
                if not href.startswith(("http://", "https://")):
                    base = page.url
                    href = f"{urlparse(base).scheme}://{urlparse(base).hostname}" + href
                if not check_url_allowed(href, allowed):
                    continue
                # hint 优先
                if hint and hint.lower() in (await link.inner_text()).lower():
                    return href
            # 无 hint 命中，取第一个 allowlist 内的链接
            for link in links:
                href = await link.get_attribute("href")
                if href and not href.startswith("#"):
                    if not href.startswith(("http://", "https://")):
                        base = page.url
                        href = f"{urlparse(base).scheme}://{urlparse(base).hostname}" + href
                    if check_url_allowed(href, allowed):
                        return href
        except Exception:
            pass
        return None


# ──────────────────────────────────────────────────────────────
# 单例（仿 memory_store 模式：懒加载，enable_browser=false 时返回 None）
# ──────────────────────────────────────────────────────────────

_browser_tool: BrowserTool | None = None


def get_browser_tool() -> BrowserTool | None:
    """获取全局 BrowserTool 单例。

    enable_browser=false 时返回 None（完全不介入，现有测试不受影响）。
    仿 nodes.py 的 get_memory_store 模式。

    注意：运行时读 get_settings() 而非模块级 settings，保证测试改环境变量后生效。
    """
    global _browser_tool
    # 运行时读配置（lru_cache），保证测试 monkeypatch env 后能感知
    from .config import get_settings
    if not get_settings().enable_browser:
        return None
    if _browser_tool is None:
        _browser_tool = BrowserTool()
    return _browser_tool


async def close_browser_tool():
    """关闭单例（服务停时调）。"""
    global _browser_tool
    if _browser_tool is not None:
        await _browser_tool.close()
        _browser_tool = None
