# ── Dockerfile：多阶段构建，产出精简生产镜像 ──────────────
# 用法：docker build -t kb-qa .
#       docker run -p 8001:8001 --env-file .env -v $(pwd)/data:/app/data kb-qa

# ---- 构建阶段：装依赖（利用 layer cache）----
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# 先只拷 requirements，依赖不变时不重装（layer cache）
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# ---- 运行阶段：精简镜像 ----
FROM python:3.11-slim

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY src/ ./src/
COPY api/ ./api/
COPY static/ ./static/
COPY eval/ ./eval/
COPY cli.py pytest.ini ./

# 数据/向量库挂载点（容器重建后知识库与会话不丢）
RUN mkdir -p /app/data/docs /app/chroma_kb
ENV DOCS_DIR=/app/data/docs \
    CHROMA_PATH=/app/chroma_kb \
    SQLITE_DB_PATH=/app/data/kb_qa.db

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/health')" || exit 1

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
