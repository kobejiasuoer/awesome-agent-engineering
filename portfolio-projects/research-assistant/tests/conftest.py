"""pytest 配置：测试环境的统一设置。

测试原则：
    - 不调用真实 LLM（慢、花钱、不确定）—— 节点测试用 mock LLM
    - 不依赖外网 —— web_search 测试走错误路径 / mock
    - 不污染生产 db —— 用临时 sqlite + InMemorySaver
    - 不需要真实 API key —— 占位符即可（mock LLM 不发请求）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 让测试能 import src/research_assistant 和 api
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO))

# 测试环境变量（必须在 import research_assistant 之前设置，因为 config 在 import 时读 .env）
os.environ.setdefault("ZHIPUAI_API_KEY", "test-key-not-real")
os.environ.setdefault("SQLITE_DB_PATH", "")  # 空 = InMemorySaver，测试不留文件
os.environ.setdefault("NUM_SUBTOPICS", "2")  # 测试用更少子题，加速
os.environ.setdefault("MAX_REWRITES", "2")


class FakeLLM:
    """假 LLM：按预设的回复字典返回，不联网。

    用法：llm = FakeLLM({"prompt关键词": "回复内容", ...})
    invoke 时按 content 命中第一个匹配的 key 返回。
    """

    def __init__(self, responses: dict[str, str], default: str = "测试回复"):
        self.responses = responses
        self.default = default
        self.call_count = 0

    def invoke(self, prompt, **kwargs):
        # prompt 可能是 str 或 message list
        text = prompt if isinstance(prompt, str) else str(prompt)
        self.call_count += 1
        for key, resp in self.responses.items():
            if key in text:
                return _Msg(resp)
        return _Msg(self.default)

    async def ainvoke(self, prompt, **kwargs):
        return self.invoke(prompt, **kwargs)


class _Msg:
    """模拟 LangChain 的 AIMessage（只需要 .content 属性）。"""
    def __init__(self, content):
        self.content = content


@pytest.fixture
def fake_llm():
    """默认的假 LLM 工厂。"""
    return FakeLLM


@pytest.fixture(autouse=True)
def reset_config_cache():
    """每个测试前重置 settings 的 lru_cache，保证环境变量改动生效。

    AgentOps L03：同时重置熔断器注册表（避免跨测试状态泄漏）。
    """
    from research_assistant import config
    config.get_settings.cache_clear()
    # AgentOps L03：每个测试前清空熔断器（_breakers 是模块全局，不隔离会泄漏）
    try:
        from research_assistant.breaker import reset_breakers
        reset_breakers()
    except Exception:
        pass
    yield
    config.get_settings.cache_clear()
    try:
        from research_assistant.breaker import reset_breakers
        reset_breakers()
    except Exception:
        pass
