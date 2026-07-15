"""联网搜索工具：真实 DuckDuckGo 搜索（替代 L09 的 LLM 幻觉）。

这是生产化的第一个关键升级：
    - L09 的 researcher 用 fast_llm.invoke("用2句话回答...") —— 凭模型知识"编"，无来源
    - 本项目的 researcher 用 web_search —— 真实联网，带来源链接，可溯源

复用自 agent-lessons/09_capstone/code.py:44-65 的实现，并补齐生产要素：
    1. 全局 Semaphore 限流（exercise 思考题 2：防 DuckDuckGo QPS 封禁）
    2. 超时控制（防单次请求挂死整个并行批次）
    3. 错误兜底（搜索失败返回友好提示，不崩溃，让 Agent 可重试/降级）
"""
from __future__ import annotations

import asyncio

# 优先用新包名 ddgs（duckduckgo_search 已更名，新版在国内网络更可用）；
# 兼容旧包名，两者 API 一致（都是 DDGS()）。
try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - 老环境兜底
    from duckduckgo_search import DDGS

from .config import settings

# 全局并发闸门：并行 researcher 共享，最多 max_concurrent_search 个同时联网。
# 例：3 个 researcher 并行，但 web_search 同时最多 5 个真实 HTTP 请求——
# 这里 researcher=3 < 上限=5，所以不阻塞；扩到 20 researcher 时才触发限流。
_search_semaphore = asyncio.Semaphore(settings.max_concurrent_search)


async def web_search(query: str, max_results: int | None = None) -> str:
    """异步联网搜索，返回格式化的结果文本。

    Args:
        query: 搜索关键词
        max_results: 返回条数（默认读配置 search_max_results）

    Returns:
        格式化文本：每条 [序号] 标题 / 摘要 / 来源链接；失败时返回友好提示。

    生产特性：
        - Semaphore 限流：全局并发上限，防止打爆搜索 API
        - 超时：单次搜索限时，超时走兜底
        - 异常兜底：网络错/解析错都不抛，返回可降级的字符串
    """
    max_results = max_results or settings.search_max_results

    async with _search_semaphore:
        # DDGS 是同步库，丢到线程池跑，避免阻塞 asyncio 事件循环
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_ddgs_search, query, max_results),
                timeout=settings.search_timeout,
            )
            return result
        except asyncio.TimeoutError:
            return f"搜索 '{query}' 超时（{settings.search_timeout}s）。可换关键词或稍后重试。"
        except Exception as e:
            return f"搜索 '{query}' 失败（{type(e).__name__}: {e}）。可换关键词重试。"


def _ddgs_search(query: str, max_results: int) -> str:
    """同步搜索实现（在线程池里跑）。"""
    ddgs = DDGS()
    results = list(ddgs.text(query, max_results=max_results))
    if not results:
        return f"搜索 '{query}' 没有返回结果。可以换个关键词试试。"

    # 整理成简洁文本：标题 + 摘要(截断) + 来源链接
    formatted = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        body = r.get("body", "")[:150]
        href = r.get("href", "")
        formatted.append(f"[{i}] {title}\n    {body}\n    来源: {href}")
    return "\n".join(formatted)


async def web_search_structured(query: str, max_results: int | None = None) -> dict:
    """结构化搜索（AgentOps L03 诚实降级协议）。

    与 web_search 的本质区别：返回结构化结果而非裸字符串。
        {"status": "ok"|"degraded"|"failed", "content": str, "reason": str}

    - ok：搜索成功，content 是格式化结果
    - degraded：超时（不等了的失败）/ 熔断打开快速失败 —— content 可能为空
    - failed：抛错（等了的失败）

    关键：degraded/failed 的 content 绝不是「搜索超时」字符串混进材料被当事实——
    下游（researcher）看 status 字段决定怎么用，而不是 parse 字符串。
    熔断器（enable_circuit_breaker）打开时，连续失败会快速失败不再等超时。

    默认走这个函数当 enable_circuit_breaker=True；否则现状用 web_search（字符串）。
    """
    from .breaker import get_breaker, call_with_breaker

    max_results = max_results or settings.search_max_results

    # 熔断器（按 web_search 实例隔离）
    if settings.enable_circuit_breaker:
        breaker = get_breaker(
            "web_search",
            fail_threshold=settings.breaker_fail_threshold,
            cooldown=settings.breaker_cooldown,
        )
        # 包装一次带超时的搜索调用
        async def _do_search():
            return await asyncio.wait_for(
                asyncio.to_thread(_ddgs_search, query, max_results),
                timeout=settings.search_timeout,
            )
        # 重试（治抖动）+ 熔断（治持续故障）
        retries = settings.search_retry
        last_result = None
        for attempt in range(retries + 1):
            result = await call_with_breaker(breaker, _do_search)
            last_result = result
            if result["status"] == "ok":
                return result
            # 失败：熔断打开时 call_with_breaker 已返回 degraded（不重试）
            if result["reason"].startswith("熔断器打开"):
                return result
            # 抖动重试（未到熔断阈值的偶发失败）
            if attempt < retries:
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
        return last_result

    # 未开熔断器：带超时的搜索，结构化包装（比 web_search 多一层诚实标注）
    try:
        content = await asyncio.wait_for(
            asyncio.to_thread(_ddgs_search, query, max_results),
            timeout=settings.search_timeout,
        )
        return {"status": "ok", "content": content, "reason": ""}
    except asyncio.TimeoutError:
        return {"status": "degraded", "content": "",
                "reason": f"搜索超时（{settings.search_timeout}s）"}
    except Exception as e:
        return {"status": "failed", "content": "",
                "reason": f"{type(e).__name__}: {e}"}
