"""FastAPI 应用：企业知识库问答服务。

路由：
    POST /api/upload  —— 上传文档（md/txt）并增量入库
    POST /api/ask     —— SSE 流式问答（progress + sources + token + done）
    GET  /api/health  —— 健康检查
    GET  /             —— 极简前端（static/index.html）

运行：uvicorn api.main:app --port 8001  或  python -m api.main
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid
from pathlib import Path

# 让 api 包能 import 顶层 src（无论从哪启动）
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from kb_qa.config import settings
from kb_qa.ingest import get_vectorstore, ingest_directory
from kb_qa.service import reset_kb, stream_ask

from .schemas import AskRequest, HealthResponse, UploadResponse

app = FastAPI(
    title="企业知识库问答系统",
    description="混合检索 + reranker 重排 + 引用溯源的生产级 RAG",
    version="0.1.0",
)

_STATIC = _ROOT / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

_SAFE_FILENAME = re.compile(r"^[\w一-鿿.-]+\.(md|txt)$")


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    vs = get_vectorstore()
    return HealthResponse(
        answer_model=settings.answer_model,
        enable_rerank=settings.enable_rerank,
        total_chunks=vs._collection.count(),
    )


@app.post("/api/upload", response_model=UploadResponse)
async def upload(file: UploadFile) -> UploadResponse:
    """上传文档 → 存到 docs 目录 → 增量入库 → 作废检索索引。"""
    name = Path(file.filename or "").name
    if not _SAFE_FILENAME.match(name):
        raise HTTPException(400, "只支持 .md / .txt 文件，文件名仅限中英文、数字、点、横线、下划线")

    content = await file.read()
    if len(content) > settings.upload_max_mb * 1024 * 1024:
        raise HTTPException(413, f"文件超过 {settings.upload_max_mb}MB 上限")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "文件必须是 UTF-8 编码文本")

    dest = Path(settings.docs_dir) / name
    dest.write_bytes(content)

    report = await asyncio.to_thread(ingest_directory)
    await reset_kb()
    return UploadResponse(
        filename=name,
        added_chunks=report.added_chunks,
        total_chunks=report.total_chunks,
    )


@app.post("/api/ask")
async def ask(req: AskRequest):
    """SSE 流式问答。事件：progress / sources / token / done / error。"""
    thread_id = req.thread_id or f"web-{uuid.uuid4().hex[:8]}"

    async def event_generator():
        try:
            async for event in stream_ask(req.question, thread_id, req.mode):
                yield event
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@app.get("/")
async def index():
    index_html = _STATIC / "index.html"
    if index_html.exists():
        return FileResponse(str(index_html))
    raise HTTPException(404, "前端未构建（static/index.html 缺失）")


def main() -> None:
    import uvicorn

    uvicorn.run("api.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
