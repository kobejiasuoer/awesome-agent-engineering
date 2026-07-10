# 企业知识库问答系统（生产级 RAG）

基于 LangChain 的企业知识库问答：上传文档 → 自动向量化入库 → **混合检索 + reranker 重排** → 带引用溯源的流式回答，附带 **ragas 四指标量化评估**与消融诊断报告。

与姊妹项目 [research-assistant](../research-assistant/)（LangGraph 多智能体）互补：一个吃 Agent 能力，一个吃 RAG 能力。

## 核心亮点（区别于「能跑个 RAG demo」）

| 能力 | 实现 | 量化证据 |
|---|---|---|
| 检索质量优化 | BM25(jieba)+向量混合召回 → 智谱 cross-encoder 重排 | context_recall **0.975**（vs 纯向量 0.925） |
| 可量化评估 | ragas 四指标 + 20 题 golden set + 三模式消融 | 见 [eval/REPORT.md](eval/REPORT.md) |
| 防幻觉 | 材料外拒答 prompt + 【材料N】引用溯源 + 低温 | faithfulness **0.848**，库外问题正确拒答 |
| 增量入库 | 文件 MD5 缓存，新增/修改/删除三路径幂等 | 重复 ingest 零 embedding 调用 |
| 多轮对话 | condense-question：追问先改写成独立问题再检索 | 「那企业版呢？」正确召回并回答 |
| 生产化 | FastAPI + SSE 流式、Docker、pytest 17 项全 mock | `make test` 1.3s 全绿 |

## 架构

```
┌─────────────── 数据层（Ingest）────────────────┐
│ 上传(md/txt) → MarkdownHeaderTextSplitter      │
│ 结构感知分块(带章节面包屑) → embedding-3        │
│ → Chroma 持久化 → 增量缓存(MD5，三路径幂等)     │
└────────────────────┬───────────────────────────┘
                     ▼
┌─────────────── 检索层（Retrieve）──────────────┐
│ 提问 → [追问改写 condense-question]             │
│ → EnsembleRetriever(BM25×0.4 + 向量×0.6) 召回8 │
│ → 智谱 rerank 重排 → top-4 带出处材料           │
│    （可开关 ENABLE_RERANK，评估消融用）          │
└────────────────────┬───────────────────────────┘
                     ▼
┌─────────────── 生成层（Generate）──────────────┐
│ 防幻觉 prompt + 【材料N】引用 → glm-4 流式      │
│ → 会话历史 sqlite 持久化（thread_id 隔离）       │
│ → SSE: progress / sources / token / done       │
└────────────────────────────────────────────────┘

┌─────────────── 评估层（Eval，独立）────────────┐
│ golden set 20 题 → 三模式跑批 → ragas 四指标    │
│ → 诊断报告（哪个环节拖后腿 → 优化方向）          │
└────────────────────────────────────────────────┘
```

## 快速开始

```bash
cd portfolio-projects/knowledge-base-qa
cp .env.example .env          # 填入 ZHIPUAI_API_KEY
make install                  # 或 pip install -r requirements.txt
make ingest                   # 8 个示例文档入库（增量，重复跑秒回）
make run                      # http://localhost:8001 打开前端
```

CLI 验证：

```bash
python cli.py query "试用期多久"            # 裸向量召回
python cli.py retrieve "P0 工单响应时限"    # 完整检索管线
python cli.py compare "报销时限"            # 三模式并排对比
```

Docker：

```bash
docker compose up -d          # 首次构建后 http://localhost:8001
```

评估（打真实 API，三模式约 30 分钟）：

```bash
make eval                     # 或 python eval/run_eval.py --modes rerank --limit 5 冒烟
```

## API

| 路由 | 说明 |
|---|---|
| `POST /api/upload` | 上传 md/txt（白名单文件名+5MB+UTF-8 校验）→ 增量入库 → 索引热更新 |
| `POST /api/ask` | SSE 流式问答：`progress` / `sources` / `token` / `done` / `error` 五事件 |
| `GET /api/health` | 健康检查（模型/rerank 开关/库内块数） |
| `GET /` | 极简前端（上传 + 对话 + 引用面板 + 模式切换） |

## 设计决策（面试可讲的部分）

**为什么结构感知分块？** 企业制度文档强结构（章/节/条款），纯字符切分会把条款和所属章节切散。先按标题切出带层级 metadata 的节、超长节再字符兜底，每个 chunk 自带「员工手册 > 考勤 > 迟到处理」面包屑——检索命中即知精确出处，引用溯源直接可用。

**为什么混合检索？** 向量吃语义（「工资的八成」≈「转正工资的 80%」）但对精确词弱（「帆修」「P0」这类 token 会糊）；BM25 恰好相反。加权 RRF 融合互补。**中文坑**：BM25 默认按空格分词，必须配 jieba，否则整句变一个 token 直接失效。

**为什么 reranker 且做成可开关？** cross-encoder 逐对精算 query×候选相关性，排序质量高于 bi-encoder 距离；只对召回后 8 条重排，成本可控。做成开关让评估层能跑消融——**量化出 reranker 价值**（context_recall +5pp）而不是拍脑袋说「加了更好」。

**实测坑：智谱 rerank 分数饱和。** 多数相关候选精确返回 1.0，同分时 API 排序不稳定，会打乱混合检索排好的头部。解法：本地按（分数降序，上游排名升序）稳定排序，rerank 只在真有区分度时改变顺序。评估还发现**只开混合不开重排是负优化**（BM25 词面噪声让 faithfulness 从 0.80 掉到 0.75，重排压掉噪声后回升到 0.85）——「混合检索必须配 reranker」是这个项目跑出来的结论，不是背的。

**为什么多轮记忆不用 LangGraph Checkpointer？** 研究助手是多节点图需要图状态检查点；本项目生成链是线性的，一张 sqlite messages 表就够。追问检索难题（「那企业版呢？」单独检索召不回）用 condense-question 解：glm-4-flash 先把追问改写成独立问题再检索。用对工具的复杂度也是生产判断力。

**ragas 0.4.3 兼容坑。** 它硬 import 已被 langchain-community sunset 删除的 `chat_models.vertexai`，import 即崩；ragas 只做 isinstance 判断不实例化，注入空壳 stub 即可（[ragas_compat.py](src/kb_qa/ragas_compat.py)）。judge 超时产生的 NaN 样本从聚合剔除并注明，不让脏数据污染均值。

## 评估结果摘要

| 指标 | vector | hybrid | rerank（生产默认） |
|---|---|---|---|
| context_recall | 0.9250 | 0.9000 | **0.9750** |
| context_precision | 0.8333 | 0.8796 | 0.8583 |
| faithfulness | 0.8028 | 0.7488 | **0.8483** |
| answer_relevancy | 0.6058 | 0.6431 | **0.6524** |

逐指标诊断与后续优化方向见 [eval/REPORT.md](eval/REPORT.md)。

## 项目结构

```
├── src/kb_qa/
│   ├── config.py        # pydantic-settings 配置中心（全部可 env 覆盖）
│   ├── loader.py        # 结构感知分块 + 溯源 metadata
│   ├── ingest.py        # 增量入库（MD5 缓存三路径）
│   ├── retriever.py     # 混合检索 KBRetriever（三模式）
│   ├── rerank.py        # 智谱 rerank（降级+稳定排序）
│   ├── generate.py      # 防幻觉 prompt + 流式生成 + 追问改写
│   ├── history.py       # sqlite 会话历史
│   ├── service.py       # SSE 事件流编排
│   └── ragas_compat.py  # ragas vertexai stub
├── api/                 # FastAPI（upload / ask / health）
├── static/index.html    # 极简前端
├── eval/                # golden set + ragas runner + 诊断报告
├── tests/               # pytest 17 项（全 mock 零 API 调用）
└── Dockerfile / docker-compose.yml / Makefile
```

## 课程能力映射

| 本项目模块 | 来自课程 | 升级点 |
|---|---|---|
| 增量入库缓存 | rag-09 src_hash 模式 | 补齐修改/删除路径，幂等 |
| 混合检索 | rag-06 BM25+RRF 玩具版 | EnsembleRetriever 生产版 + jieba |
| reranker | rag-06 token 命中率 | 真 cross-encoder API + 饱和坑处理 |
| 防幻觉+引用 | rag-05 | 系统 prompt + SSE sources 事件 |
| 评估 | rag-08 自制 mini-RAGAS | ragas 四指标 + 消融 + 诊断报告 |
| 分块 | rag-04 / framework-03 | MarkdownHeaderTextSplitter 结构感知 |
| FastAPI/SSE/Docker | research-assistant | 骨架复用，新增文件上传与索引热更新 |
