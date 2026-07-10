# ── Makefile：常用命令快捷方式 ────────────────────────────
# 用法：make <target>；无 make 环境直接看各 target 下的命令。

PYTHON ?= python

.PHONY: help install ingest run test eval docker docker-up docker-down clean lint

help:  ## 显示所有命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## 安装依赖
	$(PYTHON) -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

ingest:  ## 文档目录同步入库（增量）
	$(PYTHON) cli.py ingest

run:  ## 启动 FastAPI 服务
	$(PYTHON) -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001

test:  ## 跑测试（全 mock，不打 API）
	$(PYTHON) -m pytest -v

eval:  ## ragas 消融评估（vector/hybrid/rerank × golden set 20 题，打真实 API）
	$(PYTHON) eval/run_eval.py --modes vector hybrid rerank

docker:  ## 构建 Docker 镜像
	docker build -t kb-qa .

docker-up:  ## docker compose 启动（后台）
	docker compose up -d

docker-down:  ## docker compose 停止
	docker compose down

clean:  ## 清理临时文件
	-find . -type d -name __pycache__ -exec rm -rf {} +
	-rm -f kb_qa.db
	-rm -rf .pytest_cache

lint:  ## 语法检查
	@$(PYTHON) -c "import py_compile, glob; [py_compile.compile(f, doraise=True) for f in glob.glob('src/**/*.py', recursive=True) + glob.glob('api/*.py') + glob.glob('eval/*.py') + glob.glob('tests/*.py') + ['cli.py']]; print('lint OK')"
