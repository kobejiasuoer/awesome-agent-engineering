"""配置中心：所有可配置项集中在这里，用 pydantic-settings 从 .env 读取。

设计原则：
    - 所有"会变的值"（模型名、并发数、阈值、路径）都不写死在代码里
    - 通过环境变量覆盖，方便 Docker / 不同环境部署
    - 一处定义，全项目 import 复用（避免散落的 magic number）
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


def _env_files() -> tuple[str, ...]:
    """候选 .env 路径：项目目录 → 仓库根 → 上级。

    兼容三种运行方式：
        - 在项目目录跑（portfolio-projects/research-assistant/）
        - 在仓库根跑
        - 测试时从任意目录
    """
    # config.py 在 src/research_assistant/ 下：
    # parents[0]=research_assistant, [1]=src, [2]=项目根(research-assistant),
    # [3]=portfolio-projects, [4]=仓库根(RAG-test)
    here = Path(__file__).resolve().parent
    candidates = [
        Path(".env"),               # 当前工作目录
        here.parents[2] / ".env",   # 项目根 research-assistant/
        here.parents[3] / ".env",   # portfolio-projects/
        here.parents[4] / ".env",   # 仓库根 RAG-test/
    ]
    return tuple(str(p) for p in candidates)


from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。优先从 .env 读取，缺省值保证开箱即用。"""

    model_config = SettingsConfigDict(
        env_file=_env_files(),       # 多候选路径，pydantic 取第一个存在的
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM 模型（多模型路由：L06/L09 的成本优化）──────────────
    # 默认空串：允许 import 时（.env 还没加载）不崩；运行前由 cli/app 校验非空。
    zhipuai_api_key: str = Field(default="", description="智谱 API Key，必填")

    # 决策/写作模型：贵但聪明，用在质量关键节点（summarize/writer/reviewer）
    smart_model: str = "glm-4"
    # 执行模型：免费快，用在并行量大、对质量要求不极致的节点（split/researcher）
    fast_model: str = "glm-4-flash"

    # ── LLM 调用参数 ──────────────────────────────────────────
    llm_temperature: float = 0.3

    # ── 并行研究子图参数 ───────────────────────────────────────
    # 把主题拆成几个子问题（=并行研究员数量）
    num_subtopics: int = 3
    # web_search 并发限流（防 DuckDuckGo QPS 封禁，exercise 思考题 2 的生产解）
    max_concurrent_search: int = 5
    # 每个 web_search 拿几条结果
    search_max_results: int = 5
    # DuckDuckGo 单次请求超时（秒），超时走兜底
    search_timeout: int = 15

    # ── 审稿回路参数（阶段 2）──────────────────────────────────
    # 报告最多重写几次，达到上限强制通过（防 reviewer/writer 死循环）
    max_rewrites: int = 3

    # ── 持久化（阶段 2）────────────────────────────────────────
    # SqliteSaver 数据库路径；为空则用 InMemorySaver（测试用）
    sqlite_db_path: str = "research_assistant.db"

    # ── MCP 集成（LLMOps L09 · 内部知识库工具）──────────────────
    # 启用后，researcher 节点会先查 kb-qa 内部知识库（经 MCP 协议），再联网补充。
    # enable_kb_search=false 或 kb-qa 不可用时，自动降级为纯联网（不破坏现有功能）。
    enable_kb_search: bool = False
    kb_mcp_server_path: str = ""   # 留空=自动定位同仓库的 kb-qa/mcp_server.py

    # ── 记忆系统（Frontier L01 · Agent 记忆分层）─────────────────
    # 与 sqlite_db_path（Checkpointer 对话持久化）不同：这是 Agent 的经验记忆库。
    # 启用后，researcher 研究前先 recall 相关旧记忆注入 prompt，实现跨会话记忆。
    # 默认关：不破坏现有 25 个测试；开启后第二次研究同一主题能记得第一次查过什么。
    enable_memory: bool = False
    # 记忆库持久化路径（Chroma 向量库目录）
    memory_db_path: str = "memory_store"
    # 情景记忆上限（L02 遗忘策略用，0=不限）
    memory_max_episodic: int = 100
    # 记忆衰减天数（超过且未被检索的淘汰，0=不衰减）
    memory_decay_days: float = 30.0

    # ── Skills 加载（Frontier L03 · 上下文工程）──────────────────
    # 启用后，writer 写报告前先加载匹配的 skill（渐进式上下文加载）。
    # skill = 一个文件夹（SKILL.md 说明 + 资源），Agent 先看描述，用到才加载全文。
    # 默认关：不破坏现有测试；开启后 writer 产出遵循 skill 规定的格式。
    enable_skills: bool = False

    # ── 反思修正（Frontier L05 · 双通道 reviewer）─────────────────
    # reviewer 升级为双通道：文字问题→writer 重写（现状）；事实冲突→定向补研。
    # 补研次数上限（防死循环，复用 max_rewrites 思路）
    max_re_research: int = 2

    # ── 代码解释器（Frontier L07 · CodeAct 落地）──────────────────
    # 启用后，writer 写报告时若涉及数值对比/统计，路由到沙箱代码执行。
    # 报告附录附执行过的代码（可复算性）。默认关：不破坏现有测试。
    enable_code_interpreter: bool = False

    # ── 服务（阶段 3）──────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    """单例配置。lru_cache 保证全进程只读一次 .env。"""
    return Settings()  # type: ignore[call-arg]


# 便捷别名，全项目用 `from .config import settings`
settings = get_settings()
