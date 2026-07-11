"""配置中心：所有可配置项集中在这里，用 pydantic-settings 从 .env 读取。

设计原则（沿用 research-assistant）：
    - 所有"会变的值"（模型名、路径、阈值、开关）不写死在业务代码里
    - 环境变量可覆盖，方便 Docker / 评估脚本切换配置
    - 一处定义，全项目 `from kb_qa.config import settings` 复用
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py 在 src/kb_qa/ 下：parents[0]=kb_qa, [1]=src, [2]=项目根, [3]=portfolio-projects, [4]=仓库根
_HERE = Path(__file__).resolve().parent
PROJECT_ROOT = _HERE.parents[1]


def _env_files() -> tuple[str, ...]:
    """候选 .env 路径：当前目录 → 项目根 → 仓库根（兼容从任意目录启动/测试）。"""
    candidates = [
        Path(".env"),
        PROJECT_ROOT / ".env",
        _HERE.parents[3] / ".env",  # portfolio-projects/
        _HERE.parents[4] / ".env",  # 仓库根 RAG-test/
    ]
    return tuple(str(p) for p in candidates)


class Settings(BaseSettings):
    """应用配置。优先从 .env 读取，缺省值保证开箱即用。"""

    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 智谱 API ──────────────────────────────────────────────
    # 默认空串：允许 import 时不崩；运行前由 cli/api 校验非空。
    zhipuai_api_key: str = Field(default="", description="智谱 API Key，必填")

    embedding_model: str = "embedding-3"
    answer_model: str = "glm-4"          # 回答生成（质量关键）
    rewrite_model: str = "glm-4-flash"   # 查询改写（量大、免费）
    rerank_model: str = "rerank"         # 智谱 cross-encoder 重排
    llm_temperature: float = 0.1         # 知识库问答要克制，低温减少发挥

    # ── 数据层（Ingest）───────────────────────────────────────
    docs_dir: str = str(PROJECT_ROOT / "data" / "docs")
    chroma_path: str = str(PROJECT_ROOT / "chroma_kb")
    collection_name: str = "kb_qa"
    chunk_size: int = 500
    chunk_overlap: int = 80
    embed_batch_size: int = 32           # 智谱 embedding 单请求上限 64 条，留余量

    # ── 检索层（阶段 2）───────────────────────────────────────
    retrieve_k: int = 8                  # 混合召回条数（rerank 前）
    final_k: int = 4                     # 最终送入 prompt 的材料条数
    bm25_weight: float = 0.4             # EnsembleRetriever 权重（与向量检索互补）
    vector_weight: float = 0.6
    enable_rerank: bool = True           # 可开关：评估阶段跑有/无 reranker 对比
    enable_multi_query: bool = False     # 查询改写（默认关，延迟敏感场景不开）

    # ── 服务（阶段 3）─────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8001                     # 避开研究助手的 8000
    sqlite_db_path: str = str(PROJECT_ROOT / "kb_qa.db")
    upload_max_mb: int = 5               # 上传文档大小上限

    # ── 可观测性（LLMOps L01）────────────────────────────────────
    # log_json=True 生产用（机器可消费的 JSON 行）；False 开发期看人类可读文本。
    # log_level 调到 DEBUG 可看检索分词/中间状态（默认 INFO 只打关键业务节点）。
    log_json: bool = True
    log_level: str = "INFO"

    # ── 全链路追踪（LLMOps L02 · Langfuse）──────────────────────
    # 全空/关闭 → 自动降级为 ConsoleTracer（打印 trace 树到 stderr，不依赖任何服务）。
    # 启用条件：langfuse_enabled=true + host/public_key/secret_key 三项都配 + 装了 langfuse 包。
    langfuse_enabled: bool = False
    langfuse_host: str = ""            # 例：http://localhost:3000（自部署）
    langfuse_public_key: str = ""      # 面板建项目后获得
    langfuse_secret_key: str = ""

    # ── 线上评估（LLMOps L03）──────────────────────────────────
    # 真实问答按 eval_sample_rate 抽样，异步跑 ragas（faithfulness+answer_relevancy），
    # 任一指标低于 eval_score_threshold 即入 review_queue.jsonl 待优化。
    # 点踩样本 100% 入队（强信号，不受采样率约束）。
    eval_sample_rate: float = 0.05      # 生产典型 5%；内测/演示可调高到 0.3~1.0
    eval_score_threshold: float = 0.5   # min(faithfulness,relevancy) 低于此即低分
    eval_review_queue_path: str = str(PROJECT_ROOT / "eval" / "review_queue.jsonl")

    # ── 安全：鉴权 + 限流（LLMOps L04）─────────────────────────
    # API_KEYS 逗号分隔多个 key（每调用方一个，便于单独吊销 + 按key限流）。
    # auth_enabled=true 且配了 key 才启用鉴权；否则跳过（开箱即用，不锁死本地开发）。
    # 生产务必配 API_KEYS，否则 /api/ask /api/upload 等于公网裸奔。
    api_keys: str = ""
    auth_enabled: bool = True
    rate_limit_per_minute: int = 30     # 每个 key 每分钟请求上限（LLM 接口要克制）

    # ── 性能与成本：语义缓存（LLMOps L10）──────────────────────
    # 同义问法命中后跳过检索+生成，降延迟降成本。
    # 阈值太松（<0.85）会误命中（年假vs病假答错）；太紧（>0.98）几乎不命中。
    # 0.92 是 embedding-3 + cosine 的经验平衡点，按真实问法调。
    enable_cache: bool = True
    cache_similarity_threshold: float = 0.92

    @field_validator("api_keys", mode="after")
    @classmethod
    def _normalize_api_keys(cls, v: str) -> str:
        """规范化：去空白、去空项。运行时用 api_keys_set 取集合。"""
        return ",".join(k.strip() for k in v.split(",") if k.strip())

    @property
    def api_keys_set(self) -> set[str]:
        """合法 key 集合（O(1) 查询，鉴权用）。"""
        return set(self.api_keys.split(",")) if self.api_keys else set()


@lru_cache
def get_settings() -> Settings:
    """单例配置。lru_cache 保证全进程只读一次 .env。"""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
