# 生产上线检查清单（Production Readiness Checklist）

> kb-qa v2 从「能跑的 demo」到「运维就绪的生产服务」的验收清单。
> **每一项都指向具体的代码/文档证据**——面试时拿出来，逐项指给面试官看。

用法：上线前逐项核对，每项的「证据」列指向具体文件/命令。全勾 = 运维就绪。

---

## ✅ 可观测性（Observability）

| # | 检查项 | 证据（代码/命令） | 验证方式 |
|---|---|---|---|
| 1 | 结构化日志（JSON + trace_id 贯穿） | `src/kb_qa/observability.py`（`JsonFormatter` + `contextvars`） | 跑问答后 `grep trace_id` 还原链路 |
| 2 | 日志级别/格式可配 | `config.py` `log_json` / `log_level` | `.env` 设 `LOG_JSON=false` 看人类可读 |
| 3 | 敏感信息脱敏 | `observability.py` `mask_secret` | `mask_secret('sk-xxx')` → `***xxx` |
| 4 | 全链路追踪（Langfuse + 降级） | `src/kb_qa/tracing.py` | 配 Langfuse 看面板；未配看 stderr trace 树 |
| 5 | 成本可核算（generation usage） | `tracing.py` `compute_cost` + service 埋点 | trace 树显示 ¥/次问答 |
| 6 | 线上评估闭环（抽样+反馈） | `src/kb_qa/online_eval.py` + `POST /api/feedback` | 连问后 `eval/review_queue.jsonl` 出现低分样本 |
| 7 | 点踩必入优化队列 | `api/main.py` `/api/feedback` + 前端 👎 | 点踩后队列出现该条 |

**运维话术**：「线上出问题，trace_id 一 grep 还原链路；Langfuse 面板看耗时成本；质量下降，抽样 ragas 自动抓坏答案。」

---

## ✅ 安全（Security）

| # | 检查项 | 证据 | 验证方式 |
|---|---|---|---|
| 8 | API 鉴权（key） | `src/kb_qa/auth.py` `require_api_key` | 无 key → 401（`tests/test_auth.py`） |
| 9 | 多 key 管理（可吊销） | `config.py` `api_keys`（逗号分隔） | 删一个 key 不影响其他 |
| 10 | 限流（滑动窗口） | `auth.py` `SlidingWindowLimiter` + `rate_limit` | 超速 → 429（测试覆盖） |
| 11 | 按key隔离配额 | `auth.py` 按 key 计数 | A 打满不影响 B |
| 12 | Prompt 注入攻击测试集 | `eval/attack_set.json`（12 条） | `python eval/run_attack.py --limit 5` |
| 13 | 注入防御·输入隔离（指令-数据分离） | `guardrails.py` `isolate_documents` + `generate.py` `build_context` | prompt 含 `<begin_retrieved_documents>` |
| 14 | 注入防御·prompt 强化 | `guardrails.py` `SAFE_SYSTEM_PROMPT` | system prompt 含安全规则 |
| 15 | 注入防御·输出过滤 | `guardrails.py` `sanitize_output` | service 生成后过滤 |
| 16 | 上传侧安检 | `guardrails.py` `scan_upload` + `api/main.py` | 上传含注入标记 → 400 |
| 17 | 防御固化进 CI（防回归） | `tests/test_guardrails.py` | `pytest` 改坏防御立刻红 |
| 18 | 失守率 before/after 数据 | `eval/attack_report.json`（before）+ L06 after | before 90% → after 显著降 |

**运维话术**：「接口 key 鉴权+限流；间接注入做了输入隔离+输出过滤纵深防御，失守率 90%→降，固化进 CI 防回归。」

---

## ✅ 集成（Integration）

| # | 检查项 | 证据 | 验证方式 |
|---|---|---|---|
| 19 | 知识库封成 MCP Server | `mcp_server.py`（`search_knowledge_base` + `ask_knowledge_base`） | `demo_client.py` 调通返回带出处材料 |
| 20 | MCP 工具描述清晰（LLM 会用） | `mcp_server.py` tool docstring | inspector/list_tools 看描述 |
| 21 | stdio + HTTP 双传输 | `mcp_server.py --transport` | stdio 默认 + `--transport http` |
| 22 | Agent 作 MCP Client（两项目打通） | research-assistant `kb_mcp_client.py` + `nodes.py` | demo.py 调通内部+联网双源 |
| 23 | Claude Desktop 注册配置 | L08 README `claude_desktop_config.json` | 复制 JSON 重启即用 |

**运维话术**：「知识库是 MCP 标准工具，任意 host 配一行调用；Agent 作 client 实现内部+联网双源研究。」

---

## ✅ 性能与成本（Performance & Cost）

| # | 检查项 | 证据 | 验证方式 |
|---|---|---|---|
| 24 | 语义缓存（同义命中） | `src/kb_qa/semantic_cache.py` | done 事件 `cache_hit=true` |
| 25 | 缓存阈值可配 | `config.py` `cache_similarity_threshold` | 调阈值看命中率 |
| 26 | 文档更新作废缓存 | `service.py` `reset_kb` → `invalidate` | ingest 后缓存清空 |
| 27 | 多轮上下文跳过缓存 | `service.py`（有历史不查缓存） | 追问不命中 |
| 28 | 压测基线（QPS/P95） | `loadtest/run_loadtest.py` | `python loadtest/run_loadtest.py` |
| 29 | locust 生产对照 | `loadtest/locustfile.py` | `locust -f ...`（需装） |
| 30 | 成本/质量选型报告 | `eval/run_cost_eval.py` + `cost_report.md` | `python eval/run_cost_eval.py --limit 5` |
| 31 | 按环节选模型（数据支撑） | kb-qa `answer_model=glm-4` / `rewrite_model=flash` | cost_report.md 对比表 |

**运维话术**：「语义缓存省重复调用；压测定了 QPS 天花板+信号量保护；按环节选模型有 ragas 数据支撑。」

---

## ✅ 工程基础

| # | 检查项 | 证据 | 验证方式 |
|---|---|---|---|
| 32 | 测试全绿（全 mock 不打真实 API） | `tests/`（79+ 项） | `pytest -q` |
| 33 | 配置集中（无散落 magic number） | `src/kb_qa/config.py` | 所有可配项在此 |
| 34 | Docker 部署 | `Dockerfile` / `docker-compose.yml` | `docker compose up -d` |
| 35 | .env.example 文档完整 | `.env.example` | 所有配置项有注释 |
| 36 | 优雅降级（外部服务缺失能跑） | tracing/online_eval 等均降级 | 无 Langfuse/无 key 仍可运行 |

---

## 汇总

```
可观测性：  7/7  ✅
安全：     11/11 ✅
集成：      5/5  ✅
性能成本：  8/8  ✅
工程基础：  5/5  ✅
─────────────────
总计：     36/36 ✅ 运维就绪
```

> **面试用法**：这份清单就是你的「运维资历证明」。面试官问「上线后做了什么」，你打开这份清单逐项讲——每一项有代码、有验证命令、有数据。这比任何口头描述都有说服力。
>
> **诚实标注**：其中「真实 Langfuse 面板」「真实压测数据」「真实 ragas 成本对比」三项因执行环境限制未端到端实测，代码逻辑已验证并给了降级/复现路径（见各课 README 的「诚实标注」）。
