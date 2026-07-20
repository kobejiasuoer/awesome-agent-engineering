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

    # ── 长任务账本（Frontier L10 · 跨会话任务状态）─────────────────
    # 启用后，Agent 跨多次运行推进同一主题：TODO 树持久化 + 断点续跑 + 增量简报。
    # 区别于记忆（经验）和 checkpoint（对话）——账本是「计划进度」。
    # 默认关：不破坏现有测试；开启后第三次运行接着第二次做而非从头来。
    enable_ledger: bool = False
    ledger_db_path: str = "task_ledger.db"
    # 产出模式：full=完整报告（现状）/ incremental=增量简报（L10）
    output_mode: str = "full"

    # ── 服务（阶段 3）──────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── 浏览器工具（GUI Agent 课程 L09 · 会上网的研究智能体）──────
    # 启用后，researcher 从「只看 ddgs 搜索摘要」升级到「真开浏览器进详情页取证」，
    # 带回 URL+访问时间的证据链（L10）。默认关：不破坏现有测试；开启后能拿到
    # 搜索 API 拿不到的详情页结构化字段/翻页内容/时效证据。
    # 工具分层：search（快浅便宜）打头，需要详情页才开 browse（慢深贵），失败降级回 search。
    enable_browser: bool = False
    # 浏览器 agent 循环步数上限（成本控制，每步一次 LLM+一次浏览器操作）
    browser_max_steps: int = 12
    # 单页操作超时（秒）
    browser_page_timeout: int = 15
    # 无头模式（测试/CI 用 True，调试用 False）
    browser_headless: bool = True
    # 域名 allowlist（L07 安全：逗号分隔，空=用默认 DEFAULT_ALLOWED_DOMAINS）
    browser_domain_allowlist: str = ""
    # 视觉模型（混合路线卡住时截图求助用，L05）
    vision_model: str = "glm-4v-plus"

    # ── 全局步数预算（AgentOps L01 · 给轨迹装里程表）──────────────
    # 与 max_rewrites/max_re_research 这类「局部限位」正交：那些只约束各自回路，
    # 叠乘后（3 子题 × 重查 2 × 打回 3）总步数仍无界。本开关给整条轨迹一个总里程表。
    # 超限走「诚实收尾」——带着已有材料直接进 writer 出部分结果（标注截断），而非 raise 崩掉。
    # 默认关：不破坏现有测试；开启后配合 max_total_steps 用。
    enable_step_budget: bool = False
    # 轨迹总步数上限（每经过一个父图节点 +1；recursion_limit 是 langgraph 最后保险丝）
    max_total_steps: int = 30
    # 动作签名循环检测（同节点+同参数哈希连续重复 N 次 → 判定原地打转，触发收尾）
    enable_loop_detect: bool = False
    loop_detect_window: int = 3

    # ── 轨迹级成本预算（AgentOps L02 · 轨迹级的钱包）──────────────
    # 与 ops-L12 静态选型（管单价）正交：本开关管「一次运行的 token 总量」。
    # Agent 成本是涌现的（步数×每步消耗都不确定），没有刹车会烧穿。
    # 软预算（80%）进节俭模式（剩余子题降级 flash），硬预算（100%）触发诚实收尾。
    # 默认关：不破坏现有测试；开启后配合 max_budget_tokens 用。
    enable_cost_budget: bool = False
    # 一次运行的 token 硬上限（mock 下为估算值；结构结论同真实）
    max_budget_tokens: int = 50000

    # ── 超时、熔断与诚实降级（AgentOps L03）──────────────────────
    # 现状 web_search 超时返回「搜索超时」字符串混进材料被当事实（不诚实降级）。
    # 本开关启用后：工具返回结构化结果（ok/degraded/failed + 原因），
    # degraded 材料在 prompt 里标注、报告里声明「N 个子题检索失败」。
    # 配合手写熔断器（breaker.py）治持续故障：连续 N 次失败 → 快速失败不再等超时。
    # 默认关：不破坏现有测试；开启后 web_search_structured 生效。
    enable_circuit_breaker: bool = False
    # 熔断阈值：连续失败几次打开（治持续故障，不是抖动）
    breaker_fail_threshold: int = 3
    # 熔断冷却（秒）：打开后多久半开试探
    breaker_cooldown: float = 30.0
    # 搜索重试次数（治抖动，0=不重试；熔断器治持续故障，重试治偶发抖动）
    search_retry: int = 0

    # ── 副作用与幂等（AgentOps L04）──────────────────────────────
    # 现状全是只读工具，所以「没出过事」是因为「没做过危险的事」。
    # 本开关启用后：reviewer PASS 后加一个 publish 节点（写 outputs/ + sqlite 注册表），
    # 带幂等键 hash(thread_id+内容指纹)——重复触发返回上次结果（no-op）。
    # 这是 L06 断点续跑不重放副作用的地基。
    # 默认关：图结构与现状完全一致（不加 publish 节点）。
    enable_publish: bool = False
    # dry-run：只打印将执行的动作不真执行（上线前演练）
    publish_dry_run: bool = False

    # ── 人在环审批（AgentOps L05 · 危险动作的门闸）────────────────
    # 用 langgraph interrupt() 给危险动作装审批门：节点内打断→State 存入 checkpointer
    # →进程可退出→带 resume 值重新 invoke 同 thread 继续。
    # 策略分层：dry_run 自动过 / 首次发布必审 / 同 thread 重复发布（幂等 no-op）免审。
    # 默认关：publish 节点不调 interrupt；开启后 publish 前 interrupt 等审批。
    enable_hitl: bool = False
    # 审批策略：auto（全过）/ first_only（仅首次发布审）/ always（每次都审）
    hitl_policy: str = "first_only"

    # ── 断点续跑（AgentOps L06 · 崩溃后的重做量有界）────────────
    # 现状 AsyncSqliteSaver 被动存了状态，但服务层没有任务注册——崩溃后没人知道
    # 「哪些任务没跑完、该从哪继续」。本开关启用 jobs 注册表：
    # 提交即登记、完成即更新、启动时扫描 running 的孤儿任务续跑。
    # 恢复语义：同 thread_id 以 None 输入重新 ainvoke → langgraph 从最后 checkpoint 续跑
    # （已完成的节点不重做）+ 副作用靠 L04 幂等键不重放。
    # 默认关：invoke/stream 不登记 jobs；开启后走注册表 + 恢复入口。
    enable_job_registry: bool = False

    # ── 轨迹级可观测（AgentOps L07 · 一次运行一行体检报告）──────
    # 与 ops-L01/L02 请求级日志/tracing 的区别：那些看 span（单步），
    # 本开关看整条轨迹的运行级聚合（回答「这次跑得健康吗」）。
    # 每次运行结束输出一行 run summary + 阈值告警。
    # 默认关：不输出 run summary（现状行为）；开启后每次必出 summary 行。
    enable_run_summary: bool = False
    # 阈值告警（超阈值打 WARNING 结构化事件）
    alert_steps_high: int = 25
    alert_budget_ratio_high: float = 0.9
    alert_degraded_high: int = 2

    # ── 触发与调度（Ambient L01 · 谁来叫醒 Agent）────────────────
    # 会话式的一切开始于人发消息——人忘了问，Agent 就永远沉默。
    # 本开关启用调度器：sqlite 调度表 + 可注入时钟（clock.py），到点触发
    # 盯梢任务（登记进 jobs 注册表，由常驻 daemon（L06）认领执行）。
    # 默认关：不影响现有会话式入口；测试用 FakeClock 快进，零真实等待。
    enable_schedules: bool = False
    # 注册盯梢调度时的缺省扫描间隔（小时）
    default_scan_interval_hours: float = 24.0

    # ── 信源与变化检测（Ambient L02 · 世界变了什么）──────────────
    # 常驻 Agent 醒来先做机械层变化检测（item 级内容哈希 + 快照 diff），
    # 五毛钱回答「有没有新东西」——没有就不花研究的钱。
    # 两条纪律：①「没有变化」是一等公民结果（空变化集→不进研究图）；
    # ②「没能看到」≠「没有变化」（fetch 失败→ok=False，快照不动，绝不冒充没变）。
    # 默认关：daemon（L06）不接 watcher；模块本身随时可独立调用。
    enable_source_watch: bool = False

    # ── 增量研究回路（Ambient L03 · 只研究变化，不重研全量）──────
    # watcher 变化集 → 焦点子题直进研究图（split 跳过 LLM 拆题）；
    # 旧结论（TaskLedger 已确认项）注入 researcher prompt「只补新的」；
    # 产出走 ledger 增量简报（🆕新增/✏️修正/➡️不变）——frontier-L10 账本
    # 首次接入运行时主链路（此前只有模块与测试，无调用方）。
    # 默认关：split/researcher/service 行为与现状完全一致（全量研究）。
    enable_incremental_run: bool = False

    # ── 打扰决策（Ambient L04 · 值得说吗、现在说吗）──────────────
    # 常驻 Agent 的价值观核心：每班的产出先判级（major/minor/none，LLM judge
    # + 解析失败降级 minor 宁攒勿丢），再按政策+配额决定 notify/digest/silent。
    # 与 agent-ops L07 告警的边界：那边是系统健康（我跑得不健康），
    # 这边是内容价值（世界的变化值不值得你抬头）。
    # 默认关：daemon 不做判级（产出全部落 digest，行为最保守）。
    enable_proactivity: bool = False
    # 政策：threshold（判级+配额）/ all（全推，基线对照）/ digest_only（绝不打扰）
    proactivity_policy: str = "threshold"
    # 每日立即打扰配额（notify_now 次数上限；尽了 major 也降 digest 并记档）
    daily_interrupt_quota: int = 2

    # ── 收件箱与自主级别（Ambient L05 · 不打断的交付面）──────────
    # 常驻产出的异步交付面：notify/digest/proposal/approval/alert 五类条目。
    # 隔夜审批复用 agent-ops L05 HITL（interrupt 状态在 checkpoint 里等人）。
    # 默认关：daemon 不投递收件箱（模块本身随时可独立调用）。
    enable_inbox: bool = False
    # 自主级别阶梯（「自主-控制」总旋钮）：
    #   notify=只报告不代办 / propose=拟稿等人确认 / act=先斩后奏（幂等+留痕）
    agency_level: str = "notify"

    # ── 常驻守护进程（Ambient L06 · 把 L01-L05 串成服务）────────
    # AmbientDaemon 主循环：tick 到班 → overlap 检查 → 扫描→研究→判级→投递。
    # 三条常驻纪律：单轮失败不倒 daemon / 孤儿恢复复用 resume_job /
    # 时间全注入（FakeClock 下测试秒级跑 5 天）。
    # 默认关：不启动任何常驻进程（模块只在显式运行 daemon 入口时工作）。
    enable_ambient_daemon: bool = False
    # 主循环轮询间隔（秒）——真实时钟下的 tick 节奏
    daemon_poll_seconds: float = 30.0

    # ── 时段预算与常驻可观测（Ambient L07 · 睡觉时的钱和心跳）────
    # 三层预算的第三层：请求级限流（ops-L04）→ 轨迹级钱包（agent-ops L02）
    # → 时段级钱包（本课：一天 N 次自主运行的总预算）。
    # 软线 degrade 提醒省着花，硬线 pause 挡住下一班（不打断进行中的）。
    enable_period_budget: bool = False
    period_budget_tokens: int = 200_000
    period_soft_ratio: float = 0.8
    # 自适应扫描：连续无变化 → 间隔 ×2^streak（封顶）；有变化回基础网格。
    # source_failed 不动 streak（「没能看到」既不该退避也不该回冲）。
    enable_adaptive_scan: bool = False
    adaptive_backoff_cap: int = 8
    # 心跳与缺勤：daemon 每 tick 记心跳；启动时 gap 超阈值 = 缺勤告警。
    # 「沉默的日子也要有心跳」——安静和死了必须可区分。
    enable_heartbeat: bool = False
    absence_alert_hours: float = 6.0

    # ── 上下文账本（Harness L01 · 第四种预算：空间）──────────────
    # 三层钱包（请求/轨迹/时段）之后的空间预算：钱管「烧多少」，空间管
    # 「窗口里装什么」——花得起钱也可能装不下。启用后主链路每次 LLM 调用前
    # 把 prompt 拆四桶记账（system/task_state/tool_results/history），
    # 纯测量不拦截（enforce 仅 eval 模拟物理约束用）。tokenizer 可注入
    # （FakeTokenizer len//4，与 cost_budget 估算同口径），测试确定可复现。
    # 默认关：不记账，行为零差异。
    enable_context_ledger: bool = False
    # 假窗口物理限制（token）：水位三区（<60% safe / 60-85% caution /
    # >85% danger / >100% over）与越限判断的分母
    window_limit_tokens: int = 8000

    # ── 压缩（Harness L02 · 有损但有纪律）────────────────────────
    # 三步纪律：登记（must-survive 机械保留）→ 摘要（判断交给模型）→
    # 验证（纪律交给代码）；每次压缩留审计行——无痕压缩=篡史。
    # 运行时集成在 v5 长途模式（L09）；模块本身随时可独立调用（eval 已接）。
    # 默认关：主链路行为零差异。
    enable_compaction: bool = False
    # 触发水位：进警戒区就压（占 window_limit 比例）
    compact_threshold_pct: float = 0.60
    # 压缩目标：压到该水位以下（给后续增长留余量）
    compact_target_pct: float = 0.50

    # ── 跨会话记忆文件（Harness L03 · 操作记忆）──────────────────
    # 三种记忆各管一段：任务经验（memory.py 向量召回）/ 任务进度（ledger）/
    # 操作记忆（本模块：用户偏好、长期约束——单事实单文件 + MEMORY.md 索引，
    # 索引常驻正文按���）。写入纪律 gate：临时参数拒收、已记录拒收、可反悔。
    # 启用后 writer 按 trigger 命中召回注入（背景不是指令，过时以当前对话为准）。
    # 默认关：不召回不注入，行为零差异。
    enable_memory_files: bool = False
    # 记忆文件目录（相对运行目录；测试用 tmp_path 注入）
    memory_files_dir: str = "memory_files"

    # ── 工具返回值整形（Harness L04 · 控源胜于止损）───────────────
    # 账本证明工具结果是窗口最大消耗方——压缩是止损，整形是控源。
    # 启用后 researcher 的检索结果超预算即截断，**省略必须显式**
    # （标记注明省略多少字/原文多长/怎么拿全文）——静默掐尾会让模型
    # 把半篇当全篇引用。分页/引用板斧供显式调用（L06 工作区接管落盘）。
    # 默认关：检索结果全文直给，行为零差异。
    enable_tool_shaping: bool = False
    # 单条工具结果的 token 预算（超了截断加显式标记）
    tool_result_max_tokens: int = 600


@lru_cache
def get_settings() -> Settings:
    """单例配置。lru_cache 保证全进程只读一次 .env。"""
    return Settings()  # type: ignore[call-arg]


# 便捷别名，全项目用 `from .config import settings`
settings = get_settings()
