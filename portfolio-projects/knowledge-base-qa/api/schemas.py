"""API 请求/响应模型（pydantic 输入校验）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, description="用户问题")
    thread_id: str | None = Field(default=None, max_length=64, description="会话线程 id，不传则新开")
    mode: str | None = Field(
        default=None,
        pattern="^(vector|hybrid|rerank)$",
        description="检索模式，不传用配置默认",
    )


class UploadResponse(BaseModel):
    filename: str
    added_chunks: int
    total_chunks: int


class HealthResponse(BaseModel):
    status: str = "ok"
    answer_model: str
    enable_rerank: bool
    total_chunks: int
