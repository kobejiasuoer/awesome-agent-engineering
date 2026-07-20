"""长途任务：Harness 课程的贯穿硬任务信源（课程十一 L00 定死）。

设计（任务书 1.7「长途任务」）：
    30 源深度研究，窗口限制 8k 假 token（可注入）。全离线、确定性、可复现：

    - 30 个脚本化文档：内容确定性生成，长度不均（约 350–700 假 token），
      混入 3 个超长文档（S05/S17/S28，约 2800–3400 假 token，考验 L04 整形）
    - 20 个关键事实（KEY_FACTS 编号清单）散布其中：8 个在文档开头 450 字内
      （「硬截断也砍不掉」），12 个在 60% 深度之后（「只留开头就必丢」）
    - 1 对跨源矛盾：F06（S07：Nimbus 迁移到 CKPT-X 并停止维护私有格式）
      vs F16（S23：官方澄清不停止维护，CKPT-X 仅可选导出）——
      两个事实必须同时「在场」，矛盾才可能被发现
    - 2 个操作记忆钩子（PREF_HOOKS）：任务分两个「会话」跑（SESSION_SPLIT=15），
      会话 1 中用户给出偏好，会话间只有记忆文件与工作区存续（L03/L06 试金石）
    - 1 条改道线：第 STEERING_AT 源完成后投递改道指令（L07 试金石）；
      营销类文档不携带任何关键事实——改道跳过它们不损失在场率

关键事实「在场率」的定义（机械可测，任务书 1.7）：
    不是「报告文本里出现」（FakeLLM 写不出语义），而是「最终合成调用时，
    该事实以可用形态在场」——probe 子串出现在合成调用的窗口文本里
    （L06 之后扩展为：或工作区文件被指针引用且一跳可读）。

为什么用脚本化语料而不是真实信源：
    - 课程硬约束：零联网、零真实等待、确定性可复现（双跑逐字节一致）
    - 「长程运行怎么在有限窗口里保持连贯」是结构性问题，与语料真假无关

诚实标注：
    - 文档内容为教学虚构（结构对齐真实技术调研语料），事实/数字请勿当真
    - FakeTokenizer 为 len//4 字符近似（与 cost_budget 现有估算口径一致），
      对中文偏保守——绝对数字非真实 tokenizer，结构性结论不受影响
    - 裸基线的 assistant 轮取小恒量（真实推理轮更长）——对裸基线**有利**的
      保守估计：即便如此它仍死于中途
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# 让本模块无论从仓库根/项目根/课程目录跑都能 import research_assistant
_PROJ = Path(__file__).resolve().parent.parent
if str(_PROJ / "src") not in sys.path:
    sys.path.insert(0, str(_PROJ / "src"))

# Tokenizer 协议与 FakeTokenizer 的规范住所是 context_ledger（L01）——
# eval 与主链路用同一把尺子，数字才可对账（此处 re-export 供旧调用方使用）
from research_assistant.context_ledger import FakeTokenizer  # noqa: E402, F401

# ── 任务常量 ─────────────────────────────────────────────────
TOPIC = "Agent 运行时与框架生态深度调研"
N_SOURCES = 30
WINDOW_LIMIT_TOKENS = 8000       # 假窗口（L01 起进 config，可注入覆盖）
SESSION_SPLIT = 15               # 前 15 源=会话 1；后 15 源+合成=会话 2
STEERING_AT = 10                 # 第 10 源完成后投递改道指令
STEERING_INSTRUCTION = "优先研究 safety（运行时安全）类信源；跳过 marketing（营销通稿）类信源。"
# 会话 1 里用户给出的操作偏好（跨会话必须记得——L03 试金石）
PREF_HOOKS = ("报告必须用中文撰写", "报告正文控制在 500 字以内")


# ── 关键事实 ─────────────────────────────────────────────────
@dataclass(frozen=True)
class KeyFact:
    """一条必须在合成时「在场」的关键事实。

    probe：statement 的独特子串，全语料唯一（机械在场检测的探针）。
    early：True=埋在文档前 450 字内（硬截断也砍不掉）；
           False=埋在 60% 深度之后（「只留开头」策略必丢）。
    """
    fact_id: str
    doc_id: str
    statement: str
    probe: str
    early: bool


KEY_FACTS: tuple[KeyFact, ...] = (
    KeyFact("F01", "S01", "运行时 Argus 自 1.0 起默认以 WASM 沙箱执行全部工具调用", "默认以 WASM 沙箱执行", True),
    KeyFact("F02", "S02", "A2A 与 MCP 的桥接层 bridge-rs 进入 0.9，实测转换损耗低于 3%", "转换损耗低于 3%", False),
    KeyFact("F03", "S03", "TrajBench v2 将「循环率」升为一级指标，权重定为 0.25", "权重定为 0.25", True),
    KeyFact("F04", "S04", "插件市场引入强制签名，未签名插件自 2026Q4 起禁止分发", "2026Q4 起禁止分发", False),
    KeyFact("F05", "S05", "Argus 上下文页缓存命中时端到端延迟下降 41%", "延迟下降 41%", False),
    KeyFact("F06", "S07", "Nimbus 2.0 将把检查点迁移到开放的 CKPT-X 标准并停止维护私有格式", "迁移到开放的 CKPT-X 标准", True),
    KeyFact("F07", "S08", "过去一年间接提示注入占实际攻击案例的 62%", "占实际攻击案例的 62%", False),
    KeyFact("F08", "S10", "TCS 草案要求工具错误必须携带机器可读的 retryable 字段", "机器可读的 retryable 字段", True),
    KeyFact("F09", "S11", "1k 并发轨迹下 Argus 的调度开销约为 Nimbus 的三分之一", "约为 Nimbus 的三分之一", False),
    KeyFact("F10", "S13", "两起沙箱逃逸均利用符号链接跟随而非 WASM 本体漏洞", "利用符号链接跟随", False),
    KeyFact("F11", "S15", "LongArena 的中位任务需要 147 次工具调用才能完成", "需要 147 次工具调用", True),
    KeyFact("F12", "S16", "细粒度能力令牌使越权工具调用下降 88%", "越权工具调用下降 88%", False),
    KeyFact("F13", "S18", "Vela 1.0 内置轨迹回放器，支持逐步重放与状态 diff", "内置轨迹回放器", False),
    KeyFact("F14", "S20", "快照恢复把 Agent 冷启动从 1.8 秒压到 210 毫秒", "压到 210 毫秒", True),
    KeyFact("F15", "S22", "投毒包借 typosquatting 在市场存活 11 天才被下架", "存活 11 天才被下架", False),
    KeyFact("F16", "S23", "Nimbus 澄清：2.0 不停止维护私有检查点格式，CKPT-X 仅作为可选导出", "仅作为可选导出", False),
    KeyFact("F17", "S25", "公开基准题目在主流训练语料中的检出率达 34%", "检出率达 34%", True),
    KeyFact("F18", "S26", "维护者资助计划首期覆盖 40 个关键传递依赖", "覆盖 40 个关键传递依赖", False),
    KeyFact("F19", "S28", "跨节点轨迹合并采用向量时钟而非全序广播", "采用向量时钟", False),
    KeyFact("F20", "S30", "三大框架间会话迁移成功率实测为 71%", "成功率实测为 71%", True),
)

# 跨源矛盾对（两端都在场，矛盾才可能被发现）
CONTRADICTION_PAIR = ("F06", "F16")


# ── 30 源文档（确定性生成）───────────────────────────────────
@dataclass(frozen=True)
class LongHaulDoc:
    doc_id: str
    title: str
    category: str    # runtime/protocol/benchmark/ecosystem/release/safety/marketing
    content: str


# (doc_id, title, category, token_target)——营销类不携带关键事实（改道可跳过不损失）
_DOC_SPECS: tuple[tuple[str, str, str, int], ...] = (
    ("S01", "运行时 Argus 1.0 发布说明", "runtime", 350),
    ("S02", "A2A 与 MCP 桥接进展速览", "protocol", 500),
    ("S03", "TrajBench v2 方法论白皮书", "benchmark", 650),
    ("S04", "插件市场治理新规解读", "ecosystem", 420),
    ("S05", "Argus 内存与上下文页缓存深度解析", "runtime", 2800),
    ("S06", "Nimbus 2.0 路线图公开信", "release", 580),
    ("S07", "Nimbus 检查点格式迁移公告", "release", 380),
    ("S08", "提示注入攻防年度报告", "safety", 540),
    ("S09", "「全自动数字员工」产品发布通稿", "marketing", 460),
    ("S10", "工具调用规范 TCS 草案导读", "protocol", 620),
    ("S11", "主流运行时调度器横向评测", "runtime", 560),
    ("S12", "生态峰会议程与赞助商预告", "marketing", 400),
    ("S13", "沙箱逃逸事件复盘报告", "safety", 660),
    ("S14", "开发者生态年度调查", "ecosystem", 440),
    ("S15", "长程任务基准 LongArena 介绍", "benchmark", 520),
    ("S16", "Agent 权限模型比较研究", "safety", 600),
    ("S17", "开源 Agent 生态依赖图谱（全文）", "ecosystem", 3400),
    ("S18", "框架 Vela 1.0 发布说明", "release", 480),
    ("S19", "云厂商联合推广计划通稿", "marketing", 380),
    ("S20", "Agent 冷启动优化实践", "runtime", 560),
    ("S21", "记忆交换格式 MemX 提案", "protocol", 420),
    ("S22", "供应链投毒事件调查", "safety", 640),
    ("S23", "Nimbus 维护者关于检查点格式的澄清", "release", 500),
    ("S24", "认证培训与招生简章", "marketing", 360),
    ("S25", "基准评测污染问题研究", "benchmark", 580),
    ("S26", "关键依赖维护者资助计划", "ecosystem", 460),
    ("S27", "审计日志规范草案", "safety", 520),
    ("S28", "分布式轨迹一致性设计长文", "runtime", 3000),
    ("S29", "年度影响力榜单评选通稿", "marketing", 400),
    ("S30", "跨框架互操作实测报告", "protocol", 540),
)

DOC_IDS: tuple[str, ...] = tuple(s[0] for s in _DOC_SPECS)
OVERSIZED_DOC_IDS = ("S05", "S17", "S28")

# 确定性伪正文句池（教学虚构；刻意不含任何 probe 子串）
_FILLER = (
    "该项目的路线图强调渐进式采用与向后兼容，社区讨论集中在迁移成本与旧插件生态的存续问题上。",
    "多位维护者在治理会议上重申，性能优化不应以牺牲可调试性为代价，观测钩子将保持一等公民地位。",
    "文档随后回顾了过去两个季度的发布节奏，并列出了尚未解决的已知问题与其临时规避方案。",
    "评审组指出，任何新增配置项都必须给出默认关闭的迁移路径，避免破坏既有部署的行为契约。",
    "作者用一个中型团队的落地案例说明了灰度策略：先影子运行两周，再按流量百分比逐步放开。",
    "附录整理了社区问答中出现频率最高的十个问题，多数与版本兼容矩阵和依赖锁定有关。",
    "报告提醒读者，跨版本升级前应完整备份持久化目录，并在隔离环境中演练回滚流程。",
    "与会者对治理提案的表决结果为多数赞成，少数反对意见集中在时间表过于激进这一点上。",
    "章节末尾给出了术语表与参考实现的仓库链接，便于读者对照源码理解设计取舍。",
    "编者按指出，本领域术语尚未统一，同一概念在不同社区的叫法差异较大，阅读时需注意语境。",
    "该章还比较了三种常见部署拓扑的运维成本，结论是没有普适最优解，选择取决于团队规模。",
    "文中多次强调：一切结论以官方文档的最新版本为准，转述内容可能滞后于上游变更。",
)


def _lookup_fact(doc_id: str) -> KeyFact | None:
    for f in KEY_FACTS:
        if f.doc_id == doc_id:
            return f
    return None


def _build_content(no: int, title: str, fact: KeyFact | None, token_target: int) -> str:
    """确定性组装一篇文档：标题行 + 句池填充；关键事实按 early/late 埋点。

    early：紧跟首句（起始位 <450 字符——硬截断到 500 字也砍不掉）；
    late：首次越过 62% 目标长度时插入（>600 字符——「只留开头」必丢）。
    """
    target_chars = token_target * 4
    parts: list[str] = [f"《{title}》调研全文（教学虚构语料）。"]
    parts.append(_FILLER[(no * 7) % len(_FILLER)])
    if fact is not None and fact.early:
        parts.append(fact.statement + "。")
    late_inserted = fact is None or fact.early
    i = 1
    while sum(len(p) for p in parts) < target_chars:
        if not late_inserted and sum(len(p) for p in parts) >= target_chars * 0.62:
            parts.append(fact.statement + "。")
            late_inserted = True
            continue
        parts.append(_FILLER[(no * 7 + i * 3) % len(_FILLER)])
        i += 1
    if not late_inserted:  # 目标太短没到 62%（防御，规格下不会发生）
        parts.append(fact.statement + "。")
    return "".join(parts)


def build_docs() -> dict[str, LongHaulDoc]:
    """构建 30 源语料（纯函数，确定性：双跑逐字节一致）。"""
    docs: dict[str, LongHaulDoc] = {}
    for idx, (doc_id, title, category, target) in enumerate(_DOC_SPECS, start=1):
        fact = _lookup_fact(doc_id)
        docs[doc_id] = LongHaulDoc(doc_id, title, category,
                                   _build_content(idx, title, fact, target))
    return docs


class LongHaulSource:
    """长途任务信源：目录页 + 按 doc_id 取全文 + fetch 计数器。

    fetch_counts 是「重复读取浪费」指标的数据源（L06 工作区 vs 重复 fetch）。
    """

    def __init__(self) -> None:
        self._docs = build_docs()
        self.fetch_counts: dict[str, int] = {}

    def catalog(self) -> list[tuple[str, str, str]]:
        """目录页（doc_id, title, category）——不含全文，窗口便宜。"""
        return [(d.doc_id, d.title, d.category) for d in self._docs.values()]

    def catalog_text(self) -> str:
        return "信源目录（30 源）：\n" + "\n".join(
            f"  {i} {t} [{c}]" for i, t, c in self.catalog())

    def doc(self, doc_id: str) -> LongHaulDoc:
        return self._docs[doc_id]

    def fetch(self, doc_id: str) -> str:
        """取全文（计数）。"""
        self.fetch_counts[doc_id] = self.fetch_counts.get(doc_id, 0) + 1
        return self._docs[doc_id].content

    @property
    def total_fetches(self) -> int:
        return sum(self.fetch_counts.values())


# ── 在场检测（机械层）─────────────────────────────────────────
def presence(window_text: str) -> tuple[int, list[str]]:
    """关键事实在场率：probe 子串出现在合成窗口文本里的事实数 + 缺席清单。"""
    missing = [f.fact_id for f in KEY_FACTS if f.probe not in window_text]
    return len(KEY_FACTS) - len(missing), missing


def contradiction_discoverable(window_text: str) -> bool:
    """跨源矛盾可发现 = 矛盾双方的 probe 同时在场。"""
    by_id = {f.fact_id: f for f in KEY_FACTS}
    return all(by_id[fid].probe in window_text for fid in CONTRADICTION_PAIR)


# ── 裸基线跑法（L00：现状没有 harness 时的三种结局）───────────
SYSTEM_PROMPT = (
    "你是深度研究员，任务是完成一份跨源研究报告：逐一研读信源目录中的全部文档，"
    "提取关键事实，识别不同信源之间的矛盾与演进，最终写出综合报告。\n"
    "研究规程：\n"
    "1. 按目录顺序研读；每篇提取可核查的具体结论（数字、版本、时间、承诺），"
    "而非泛泛印象；\n"
    "2. 注意同一主体在不同信源中的表述差异——前后矛盾必须在报告中显式指出，"
    "并注明两侧信源编号；\n"
    "3. 区分事实与营销话术：通稿类内容降权处理，但已研读的仍需登记；\n"
    "4. 报告需要引用具体信源的具体结论，研究过程中保持对已读内容的引用能力；\n"
    "5. 最终报告结构：概述、关键事实清单（带信源编号）、矛盾与演进分析、结论。\n"
    "约束：不得编造未在信源中出现的数字；无法核查的表述要标注不确定性。"
)
_STUDY_INSTR = "请研读下一篇文档并记录要点。"
_SYNTHESIS_INSTR = (
    "全部信源已研读完毕。现在基于以上全部材料撰写最终综合报告："
    "覆盖关键事实、指出信源间的矛盾（若有）、给出结论。"
)


def _tk(tokenizer: FakeTokenizer, text: str) -> int:
    return tokenizer.count(text)


def run_naive_longhaul(mode: str, *, window_limit: int = WINDOW_LIMIT_TOKENS,
                       truncate_chars: int = 500,
                       tokenizer: FakeTokenizer | None = None) -> dict:
    """长程单窗裸奔：一个不断增长的对话窗口装下全部过程。

    mode：
        measure       只测量不拦截（记录窗口曲线与首次越限点；「物理不可能」的
                      理想化跑法——真窗口 8k 早死了，测量数据用来解剖构成）
        enforce       强制 8k 物理约束：越限即死（ContextOverflowError 语义）
        hard_truncate 最粗暴自救：每篇全文只留前 truncate_chars 字，**无省略标记**
                      （静默截断——「活着但失忆」的对照组，L04 的反面教材）

    诚实标注：assistant 轮取小恒量（真实推理轮更长），token 计费为
    「每轮重付全窗」（无 KV 缓存减免）——两处都按对裸基线有利/不利的方向
    明写在返回值 notes 里，结构性结论不受影响。
    """
    assert mode in ("measure", "enforce", "hard_truncate")
    tk = tokenizer or FakeTokenizer()
    src = LongHaulSource()
    catalog = src.catalog_text()
    base = _tk(tk, SYSTEM_PROMPT) + _tk(tk, catalog)

    tool_texts: list[str] = []
    notes: list[str] = []
    curve: list[dict] = []          # 逐源窗口记录
    first_overflow: int | None = None
    overflow_composition: dict | None = None   # 首次越限那一刻的构成快照
    died_at: int | None = None
    tokens_billed = 0               # 每轮重付全窗（无缓存的保守口径）

    for no, doc_id in enumerate(DOC_IDS, start=1):
        full = src.fetch(doc_id)
        text = full[:truncate_chars] if mode == "hard_truncate" else full
        parts = {
            "system": _tk(tk, SYSTEM_PROMPT),
            "task_state": _tk(tk, catalog) + _tk(tk, _STUDY_INSTR),
            "tool_results": sum(_tk(tk, t) for t in tool_texts) + _tk(tk, text),
            "history": sum(_tk(tk, n) for n in notes) if notes else 0,
        }
        total = sum(parts.values())
        over = total > window_limit
        curve.append({"source": no, "window": total, "over_limit": over})
        if over and first_overflow is None:
            first_overflow = no
            overflow_composition = dict(parts)
        if mode == "enforce" and over:
            died_at = no
            break
        tokens_billed += total
        tool_texts.append(text)
        notes.append(f"已研读 {doc_id}《{src.doc(doc_id).title}》，要点已记。")

    completed = (died_at - 1) if died_at is not None else N_SOURCES

    # 最终合成（死了就没有合成——在场率 0）
    if died_at is None:
        syn_text = (SYSTEM_PROMPT + catalog + "".join(tool_texts)
                    + "".join(notes) + _SYNTHESIS_INSTR)
        syn_window = _tk(tk, syn_text)
        tokens_billed += syn_window
        hits, missing = presence(syn_text)
        contradiction = contradiction_discoverable(syn_text)
    else:
        syn_window = 0
        hits, missing = 0, [f.fact_id for f in KEY_FACTS]
        contradiction = False

    peak = max(c["window"] for c in curve) if died_at is None else curve[-1]["window"]
    if died_at is None and syn_window > peak:
        peak = syn_window

    return {
        "mode": mode,
        "completed_sources": completed,
        "died_at": died_at,
        "first_overflow_source": first_overflow,
        "peak_window_tokens": peak,
        "synthesis_window_tokens": syn_window,
        "presence": f"{hits}/{len(KEY_FACTS)}",
        "presence_hits": hits,
        "missing_facts": missing,
        "contradiction_discoverable": contradiction,
        "silent_omission": mode == "hard_truncate",   # 截断处无任何省略标记
        "tokens_billed": tokens_billed,
        "total_fetches": src.total_fetches,
        "window_curve": curve,
        "composition_at_overflow": overflow_composition,
        "cross_session": "不支持（会话断=窗口清零，PREF_HOOKS 偏好丢失）",
        "notes": [
            "assistant 轮取小恒量（真实更长）——对裸基线有利的保守估计",
            "token 计费为每轮重付全窗（无 KV 缓存减免）——绝对数字保守，结构结论一致",
        ],
    }


def run_pipeline_reference(*, window_limit: int = WINDOW_LIMIT_TOKENS,
                           keep_chars: int = 600,
                           tokenizer: FakeTokenizer | None = None) -> dict:
    """v4 流水线参照（map-reduce）：每源即时压缩，合成只见残片。

    忠实复刻现状架构的形态：researcher 逐源独立调用（窗口=指令+单篇全文，
    永不溢出），产出压缩后的 finding；summarize/writer 只见 findings 拼接。

    「未登记压缩」的机制演示（规则公开）：压缩取每篇前 keep_chars 字——
    没有 pinned 契约时，事实存活取决于它恰好埋在哪，这里演示的是一种坏运气。
    真实 LLM 的压缩去留同样无契约（L02 登记机制把运气变成契约）。
    """
    tk = tokenizer or FakeTokenizer()
    src = LongHaulSource()
    per_call_peak = 0
    tokens_billed = 0
    findings: list[str] = []
    for doc_id in DOC_IDS:
        full = src.fetch(doc_id)
        call = _tk(tk, _STUDY_INSTR) + _tk(tk, full)
        per_call_peak = max(per_call_peak, call)
        tokens_billed += call
        findings.append(f"[{doc_id}] " + full[:keep_chars])
    syn_text = _SYNTHESIS_INSTR + "\n".join(findings)
    syn_window = _tk(tk, syn_text)
    tokens_billed += syn_window
    peak = max(per_call_peak, syn_window)
    hits, missing = presence(syn_text)
    return {
        "mode": "pipeline_reference",
        "completed_sources": N_SOURCES,
        "died_at": None,
        "peak_window_tokens": peak,
        "synthesis_window_tokens": syn_window,
        "presence": f"{hits}/{len(KEY_FACTS)}（机制演示：无契约压缩，规则=只留每篇前 {keep_chars} 字）",
        "presence_hits": hits,
        "missing_facts": missing,
        "contradiction_discoverable": contradiction_discoverable(syn_text),
        "contradiction_note": "无保障——取决于矛盾两端各自在有损压缩中的存活运气",
        "silent_omission": True,     # 压缩丢弃同样无标记无审计
        "tokens_billed": tokens_billed,
        "total_fetches": src.total_fetches,
        "over_limit": peak > window_limit,
        "cross_session": "不支持（State 不跨会话，PREF_HOOKS 偏好丢失）",
    }
