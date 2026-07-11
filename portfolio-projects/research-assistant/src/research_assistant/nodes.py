"""图节点：所有节点的业务逻辑集中在这里。

延续 L09 的组织方式（节点函数集中定义），随复杂度增长可拆 nodes/ 目录。

每个节点是纯函数：输入 State 切片 → 返回 State 增量。
LangGraph 自动 merge 返回值到全局 State（受 reducer 约束）。
"""
from __future__ import annotations

from langchain_core.messages import AIMessage
from langgraph.graph import END

from .logging_config import get_logger, timed_node
from .state import ResearchState, SystemState
from .tools import web_search
from .kb_mcp_client import kb_search
from .config import settings

log = get_logger("nodes")

# 记忆系统单例（Frontier L01）：懒加载，无 enable_memory 时不创建
_memory_store = None


def get_memory_store():
    """获取/创建全局 MemoryStore 单例。

    懒加载 + 单例：多次 recall/remember 共享同一库，跨会话记忆才成立。
    enable_memory=false 时返回 None（完全不介入，现有测试不受影响）。
    """
    global _memory_store
    if not settings.enable_memory:
        return None
    if _memory_store is None:
        from .memory import MemoryStore
        _memory_store = MemoryStore()
    return _memory_store


# ════════════════════════════════════════════════════════════
# 并行研究子图节点
# ════════════════════════════════════════════════════════════
def make_split(fast_llm):
    """split 节点工厂：用 fast_llm 把主题拆成 N 个子问题。

    闭包捕获 LLM，避免全局可变状态。返回的是节点函数。
    """
    @timed_node
    def split(state: ResearchState) -> dict:
        topic = state["topic"]
        from .config import settings  # 延迟 import 避免循环
        n = settings.num_subtopics
        resp = fast_llm.invoke(
            f"你是研究规划师。把「{topic}」拆成 {n} 个具体、可独立检索的研究子问题，"
            f"每行一个，只要问题本身，不要编号。"
        )
        # 清理编号/空白，取前 n 个
        subs = [
            s.strip().lstrip("0123456789.、）) ")
            for s in resp.content.strip().split("\n")
            if s.strip()
        ][:n]
        return {"subtopics": subs}

    return split


def route_to_researchers(state: ResearchState) -> list:
    """条件边：返回 Send 列表触发并行 fan-out（L04 核心 API）。

    每个子问题 → 一个 Send(researcher, {subtopic})，LangGraph 并行执行。
    """
    from langgraph.types import Send
    return [Send("researcher", {"subtopic": s}) for s in state["subtopics"]]


def make_researcher(fast_llm):
    """researcher 节点工厂：并行查单个子问题。

    生产化关键（对比 L09 的 LLM 幻觉）：
        L09:  fast_llm.invoke("用2句话回答...")  → 凭模型记忆"编"，无来源
        本项目: web_search() 拿真实素材 + fast_llm 综合成结构化 finding

    健壮性：search 失败/为空时，LLM 仍基于自身知识产出 finding（标注无来源），
    保证并行批次不会因单个子问题检索失败而整体崩。
    """
    @timed_node
    async def researcher(state: dict) -> dict:
        subtopic = state["subtopic"]

        # ── 记忆召回（Frontier L01）──────────────────────────────
        # 研究前先 recall 相关旧记忆，注入 prompt。这是「第2次运行记得第1次」的关键。
        # enable_memory=false 或无记忆时，memory_hint 为空，不影响现有逻辑。
        memory_hint = ""
        mem_store = get_memory_store()
        if mem_store is not None:
            hits = mem_store.recall(subtopic, k=3)
            memory_hint = mem_store.format_recall_for_prompt(hits)
            if memory_hint:
                log.info(f"researcher 记忆命中：episodic={len(hits['episodic'])}, semantic={len(hits['semantic'])}")

        # 内部知识库检索（LLMOps L09）：启用时先查企业知识库（经 MCP 协议）。
        # kb_search 失败时返回降级提示（不抛异常），不影响后续联网。
        kb_raw = await kb_search(subtopic) if settings.enable_kb_search else ""
        kb_hit = bool(kb_raw) and "未找到" not in kb_raw and "不可用" not in kb_raw \
            and "失败" not in kb_raw and "未启用" not in kb_raw and "没有相关材料" not in kb_raw

        # 真实联网搜索（tools.py，带限流/超时/兜底）
        web_raw = await web_search(subtopic)

        # 合并内部+外部素材（内部优先，外部补充）
        if kb_hit:
            search_raw = f"{kb_raw}\n\n--- 外部联网补充 ---\n{web_raw}"
            source_tag = "内部知识库 + 联网搜索"
        else:
            search_raw = web_raw
            source_tag = "真实联网搜索"

        # 判断是否拿到有效素材
        has_source = "没有返回结果" not in search_raw and "失败" not in search_raw and "超时" not in search_raw

        if has_source:
            # 有真实素材：让 LLM 基于搜索结果综合（更准确、可溯源）
            # 有记忆命中时，提示 Agent「在旧记忆基础上深化而非重复」
            memory_instr = f"\n\n{memory_hint}\n请在上述记忆基础上深化，不要简单重复旧结论。" if memory_hint else ""
            resp = fast_llm.invoke(
                f"你是研究员。针对子问题「{subtopic}」，基于以下搜索资料，"
                f"提炼 2-3 句核心发现（不要照抄，要提炼）：\n\n{search_raw}{memory_instr}"
            )
            finding = f"【{subtopic}】\n  发现：{resp.content.strip()}\n  来源：{source_tag}"
        else:
            # 搜索兜底：LLM 基于自身知识回答（标注无来源，诚实降级）
            resp = fast_llm.invoke(f"用 2-3 句话回答：{subtopic}")
            finding = f"【{subtopic}】\n  发现：{resp.content.strip()}\n  来源：模型知识（联网搜索暂不可用）"

        return {"findings": [finding]}  # ⭐ reducer 自动拼接并行结果

    return researcher


def make_summarize(smart_llm):
    """summarize 节点工厂：用 smart_llm 汇总所有并行发现（质量优先）。"""
    @timed_node
    def summarize(state: ResearchState) -> dict:
        all_findings = "\n\n".join(state["findings"])
        resp = smart_llm.invoke(
            f"你是研究综合分析师。把以下 {len(state['findings'])} 个研究发现，"
            f"整理成一段连贯、有逻辑的研究摘要（300字以内）：\n\n{all_findings}"
        )
        return {"research_summary": resp.content.strip()}

    return summarize


# ════════════════════════════════════════════════════════════
# 父图节点
# ════════════════════════════════════════════════════════════
def make_research_team(research_subgraph):
    """research_team 节点工厂：把并行子图当节点（L03 子图作为节点）。

    从父图 messages 提取研究主题 → 调用子图 → 结果回流父图 State。

    异步设计：researcher 节点是 async（真实 web_search 异步 + Semaphore 限流），
    所以本节点也用 ainvoke 调子图，整条链路走 asyncio。
    （LangGraph 规则：图里有 async 节点 → 调用必须走 async API。）
    """
    @timed_node
    async def research_team(state: SystemState) -> dict:
        topic = state["messages"][-1].content

        # 调用并行子图（fresh state，子图无 messages）—— 异步
        sub_result = await research_subgraph.ainvoke({
            "topic": topic,
            "subtopics": [],
            "findings": [],
            "research_summary": "",
        })

        # 子图结果回流父图（共享字段 findings + research_summary）
        return {
            "findings": sub_result["findings"],
            "research_summary": sub_result["research_summary"],
        }

    return research_team


def make_writer(smart_llm):
    """writer 节点工厂：用 smart_llm 基于研究摘要生成结构化报告。

    report 写入两个地方：
        - state["report"]：供审稿/前端读取
        - messages（AIMessage）：供 Checkpointer 跨轮记忆（L08 模式）
    若有 reviewer 反馈，则带上 feedback 改进（阶段 2）。
    """
    @timed_node
    def writer(state: SystemState) -> dict:
        summary = state["research_summary"]
        feedback = state.get("feedback", "")

        prompt = (
            f"你是专业研究报告撰写者。基于以下研究摘要，写一份结构化研究报告，"
            f"包含【概述】和【核心要点（3-5条）】，语言专业简洁：\n\n{summary}"
        )
        if feedback:
            prompt += f"\n\n⚠️ 审稿反馈（请据此改进）：{feedback}"

        resp = smart_llm.invoke(prompt)
        report = resp.content.strip()

        return {
            "report": report,
            "messages": [AIMessage(content=report)],
        }

    return writer


# ════════════════════════════════════════════════════════════
# 审稿节点（阶段 2 新增）
# ════════════════════════════════════════════════════════════
def make_reviewer(smart_llm):
    """reviewer 节点工厂：用 smart_llm 评估报告质量（阶段 2 审稿回路）。

    这是 L09 承诺但未实现的 supervisor 逻辑——补齐「自我审视 + 迭代改进」。

    流程：writer 出报告 → reviewer 审 → 通过则结束；不通过带 feedback 回 writer。
    防死循环：rewrite_count 达到 MAX_REWRITES 强制通过。

    返回 State 增量：
        - review_decision: "pass" / "rework"
        - rewrite_count: 累计重写次数
        - feedback: 审稿意见（rework 时传给 writer）
    """
    @timed_node
    def reviewer(state: SystemState) -> dict:
        from .config import settings  # 延迟 import 避免循环

        report = state.get("report", "")
        rewrite_count = state.get("rewrite_count", 0)

        # 防死循环：达到上限强制通过
        if rewrite_count >= settings.max_rewrites:
            return {
                "review_decision": "pass",
                "rewrite_count": rewrite_count,
                "feedback": f"已达最大重写次数 {settings.max_rewrites}，强制通过。",
            }

        # 让 LLM 评估报告质量
        resp = smart_llm.invoke(
            f"你是严格的研究报告审稿人。评估以下报告是否合格，"
            f"判断标准：结构完整（有概述+要点）、信息量充足、表述专业。\n\n"
            f"报告：\n{report}\n\n"
            f"只回复一个词：合格 或 不合格。若不合格，另起一行用一句话说明问题。"
        )
        content = resp.content.strip()

        # 解析决策
        if "不合格" in content or "不合格" in content.split("\n")[0]:
            decision = "rework"
            # 提取反馈（第一行之后的内容）
            feedback_lines = content.split("\n", 1)
            feedback = feedback_lines[1].strip() if len(feedback_lines) > 1 else "报告质量不达标，请改进。"
        else:
            decision = "pass"
            feedback = ""

        return {
            "review_decision": decision,
            "rewrite_count": rewrite_count + 1,
            "feedback": feedback,
        }

    return reviewer


def review_route(state: SystemState) -> str:
    """审稿条件边：决定 writer → END 还是 writer → reviewer → writer。

    返回节点名 "writer"（重写）或 END（通过）。

    ⚠️ 注意：条件边接在 reviewer 之后。reviewer 已经设好 review_decision，
    这里只读 decision + rewrite_count 做最终路由。
    """
    decision = state.get("review_decision", "pass")
    rewrite_count = state.get("rewrite_count", 0)
    from .config import settings

    # 通过 或 达到上限 → 结束
    if decision == "pass" or rewrite_count >= settings.max_rewrites:
        return END
    # 不通过且未达上限 → 回 writer 重写
    return "writer"
