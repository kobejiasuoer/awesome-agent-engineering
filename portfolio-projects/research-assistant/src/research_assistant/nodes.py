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
# AgentOps L01：全局步数预算（step_delta 给每个节点记账，不影响现状行为）
from .step_budget import step_delta as _step_delta
# AgentOps L02：轨迹级成本预算（token_delta 记 token，record_call 给子图节点用）
from .cost_budget import token_delta as _token_delta, record_call as _record_call

log = get_logger("nodes")

# 记忆系统单例（Frontier L01）：懒加载，无 enable_memory 时不创建
_memory_store = None


# 浏览器工具单例（GUI Agent L09）：懒加载，无 enable_browser 时不创建
def get_browser_tool():
    """获取全局 BrowserTool 单例。

    enable_browser=false 时返回 None（完全不介入，现有测试不受影响）。
    仿 get_memory_store 模式。实现在 browser_tool.py。
    """
    if not settings.enable_browser:
        return None
    from .browser_tool import get_browser_tool as _get
    return _get()


def _extract_urls_from_search(search_raw: str) -> list[str]:
    """从 web_search 的格式化文本里提取来源 URL。

    web_search 输出格式（tools.py）：
        [1] 标题\n    摘要\n    来源: https://...
    提取所有 https?:// 开头的 URL。
    """
    import re
    return re.findall(r'https?://[^\s）)]+', search_raw)


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


# Skills 加载器单例（Frontier L03）：懒加载，无 enable_skills 时不创建
_skill_loader = None


def get_skill_loader():
    """获取全局 SkillLoader 单例。

    enable_skills=false 时返回 None（完全不介入，现有测试不受影响）。
    """
    global _skill_loader
    if not settings.enable_skills:
        return None
    if _skill_loader is None:
        from .skill_loader import SkillLoader
        _skill_loader = SkillLoader()
    return _skill_loader


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
        _record_call("split", resp)  # AgentOps L02：记 token（子图无 state 字段，只记 tracker）
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

        # ── 浏览器取证（GUI Agent L09）──────────────────────────
        # 启用时，从 web_search 拿到的来源链接里挑 allowlist 内的详情页，
        # 真开浏览器进详情页提取结构化证据（带 URL+访问时间）。
        # 失败/未启用时降级为纯搜索摘要（不让研究流程断）。
        browser_evidence = ""
        browser_tool = get_browser_tool()
        if browser_tool is not None:
            try:
                urls = _extract_urls_from_search(web_raw)
                if urls:
                    evidences = await browser_tool.browse_for_evidence(subtopic, urls, max_pages=2)
                    browser_evidence = browser_tool.format_evidence_for_prompt(evidences)
                    if browser_evidence:
                        log.info(f"researcher 浏览器取证：{len(evidences)} 页证据")
            except Exception as e:
                log.warning(f"browser_tool 取证失败，降级到搜索摘要：{e}")
                browser_evidence = ""

        # 合并内部+外部素材（内部优先，外部补充）
        if kb_hit:
            search_raw = f"{kb_raw}\n\n--- 外部联网补充 ---\n{web_raw}"
            source_tag = "内部知识库 + 联网搜索"
        else:
            search_raw = web_raw
            source_tag = "真实联网搜索"

        # 浏览器证据附加（若有）
        if browser_evidence:
            search_raw = f"{search_raw}\n\n--- 浏览器详情页取证 ---\n{browser_evidence}"
            source_tag = f"{source_tag} + 浏览器取证"

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
            _record_call("researcher", resp)  # AgentOps L02
            finding = f"【{subtopic}】\n  发现：{resp.content.strip()}\n  来源：{source_tag}"
        else:
            # 搜索兜底：LLM 基于自身知识回答（标注无来源，诚实降级）
            resp = fast_llm.invoke(f"用 2-3 句话回答：{subtopic}")
            _record_call("researcher", resp)  # AgentOps L02
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
        _record_call("summarize", resp)  # AgentOps L02
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

        # Frontier L05：如果有定向补研问题（事实冲突触发），用它们做子题
        re_queries = state.get("re_research_queries", [])
        if re_queries:
            # 定向补研：用冲突生成的补研问题作为子问题
            sub_result = await research_subgraph.ainvoke({
                "topic": topic,
                "subtopics": re_queries,  # 直接用补研问题
                "findings": [],
                "research_summary": "",
            })
            # 补研结果追加到 findings（不清空旧 findings，reducer 会合并）
            return {
                "findings": sub_result["findings"],
                "research_summary": sub_result["research_summary"],
                "re_research_queries": [],  # 清空，避免重复补研
                **_step_delta("research_team", "re_research"),
            }

        # 正常研究：调用并行子图（fresh state，子图无 messages）—— 异步
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
            **_step_delta("research_team", topic[:50]),
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
        # AgentOps L01：若被步数预算/循环检测截断，在报告里诚实标注
        truncated = state.get("truncated", False)

        # ── Skills 加载（Frontier L03）──────────────────────────
        # 渐进式披露：先看描述（已进 system prompt），用到时加载全文注入。
        # enable_skills=false 或无匹配时 skill_text 为空，不影响现有逻辑。
        skill_text = ""
        skill_loader = get_skill_loader()
        if skill_loader is not None:
            # 用摘要 + 反馈匹配 skill（反馈可能要求特定格式）
            match_query = f"{summary} {feedback}"
            skill_text = skill_loader.load_matched_skills(match_query)
            if skill_text:
                log.info(f"writer 加载 skill：{skill_loader.match_skills(match_query)}")

        prompt = (
            f"你是专业研究报告撰写者。基于以下研究摘要，写一份结构化研究报告，"
            f"包含【概述】和【核心要点（3-5条）】，语言专业简洁：\n\n{summary}"
        )
        if skill_text:
            prompt += f"\n\n📋 参考技能规范（请遵循其格式要求）：\n{skill_text}"
        if feedback:
            prompt += f"\n\n⚠️ 审稿反馈（请据此改进）：{feedback}"

        # Frontier L05：如果有冲突修正，要求在报告中写修正说明
        conflicts = state.get("conflicts", [])
        if conflicts:
            conflict_text = "\n".join(f"  - {c}" for c in conflicts)
            prompt += (
                f"\n\n📝 修正说明（请在报告中附「修正说明」部分，"
                f"说明旧结论/新证据/为何采信新的）：\n{conflict_text}"
            )

        resp = smart_llm.invoke(prompt)
        report = resp.content.strip()
        # AgentOps L02：记本次 writer 的 token（含 cost_mode 判断）
        _tok = _token_delta("writer", resp)

        # ── 代码解释器（Frontier L07）──────────────────────────
        # 涉及数值对比/统计时，让 LLM 生成代码 → 沙箱执行 → 结果附报告附录
        # enable_code_interpreter=false 时不介入，不影响现有逻辑。
        if settings.enable_code_interpreter:
            try:
                from .code_interpreter import (
                    should_use_code, run_code_for_research, format_code_appendix,
                    reset_executed_codes,
                )
                # 判断是否需要走代码
                if should_use_code(summary):
                    # 让 LLM 生成分析代码
                    code_resp = smart_llm.invoke(
                        f"基于以下研究摘要，生成一段 Python 代码做数据分析"
                        f"（只允许 json/statistics/collections/math/re 标准库）。\n"
                        f"摘要：\n{summary}\n"
                        f"只输出代码，不要解释。"
                    )
                    generated_code = code_resp.content.strip()
                    # 去掉 markdown 代码块标记
                    if generated_code.startswith("```"):
                        generated_code = "\n".join(
                            l for l in generated_code.split("\n")
                            if not l.startswith("```")
                        )
                    cr = run_code_for_research(generated_code)
                    if cr.success:
                        log.info(f"writer 代码执行成功，结果附报告附录")
                        report += f"\n\n📊 **代码计算结果**：\n```\n{cr.output[:500]}\n```"
                    # 附代码附录（可复算性）
                    report += format_code_appendix()
            except Exception as e:
                log.warning(f"代码解释器失败（降级到 LLM 直出）：{e}")

        # AgentOps L01：诚实收尾标注——带着已有材料出部分结果，而非 raise 崩掉
        if truncated:
            report = (
                f"⚠️ **本次研究因步数预算/循环检测被截断，以下为基于已有材料的部分结果。**\n\n"
                + report
            )

        return {
            "report": report,
            "messages": [AIMessage(content=report)],
            **_step_delta("writer", summary[:50]),
            **_tok,
        }

    return writer


# ════════════════════════════════════════════════════════════
# 审稿节点（阶段 2 + Frontier L05 双通道升级）
# ════════════════════════════════════════════════════════════
def make_reviewer(smart_llm):
    """reviewer 节点工厂：双通道审稿（文字 + 事实）。

    阶段 2（文字通道）：评估报告质量，不合格带 feedback 回 writer 重写。
    Frontier L05（事实通道）：检测新 findings 与记忆旧结论的冲突，
      冲突时生成定向补研问题，回到 research_team 补研。

    review_decision 取值：
        - "pass"：文字合格且无事实冲突 → END
        - "rework"：文字不合格 → 回 writer（带 feedback）
        - "re_research"：事实冲突 → 回 research_team（带补研问题）

    防死循环：
        - 文字重写：rewrite_count >= max_rewrites 强制 pass
        - 事实补研：re_research_count >= max_re_research 强制 pass
    """
    @timed_node
    def reviewer(state: SystemState) -> dict:
        from .config import settings  # 延迟 import 避免循环
        from .step_budget import should_truncate, honest_truncation_delta

        report = state.get("report", "")
        rewrite_count = state.get("rewrite_count", 0)
        re_research_count = state.get("re_research_count", 0)
        findings = state.get("findings", [])

        # AgentOps L01：步数预算/循环检测超限 → 诚实收尾（强制 pass，标 truncated）
        # AgentOps L02：成本预算超限同样触发诚实收尾（两个「或」起来）
        # 关键：这里不 raise——带着已有材料直接通过，writer 已标注截断。
        # 这是「诚实收尾」与 recursion_limit「崩溃式收尾」的本质区别。
        from .cost_budget import should_truncate_for_cost
        truncate, reason = should_truncate(state)
        if not truncate:
            truncate, cost_reason = should_truncate_for_cost(state)
            if truncate:
                reason = cost_reason
        if truncate:
            return {
                "review_decision": "pass",
                "rewrite_count": rewrite_count,
                "feedback": f"诚实收尾：{reason}，带着已有材料出部分结果。",
                **honest_truncation_delta(reason),
                **_step_delta("reviewer", "truncate"),
            }

        # 防死循环：两个通道都达上限强制通过
        if rewrite_count >= settings.max_rewrites and re_research_count >= settings.max_re_research:
            return {
                "review_decision": "pass",
                "rewrite_count": rewrite_count,
                "feedback": f"已达重写{settings.max_rewrites}+补研{settings.max_re_research}上限，强制通过。",
                **_step_delta("reviewer", "max_limits"),
            }

        # ── 事实通道（Frontier L05）：检测冲突 ──────────────────
        # 只在 enable_memory 且补研次数未超限时检查
        conflicts: list[str] = []
        re_research_queries: list[str] = []
        if settings.enable_memory and re_research_count < settings.max_re_research:
            mem_store = get_memory_store()
            if mem_store is not None:
                conflict_result = check_conflicts(findings, mem_store, smart_llm)
                conflicts = conflict_result.get("conflicts", [])
                re_research_queries = conflict_result.get("queries", [])
                if conflicts:
                    log.info(f"reviewer 检测到 {len(conflicts)} 个事实冲突，触发定向补研")

        # 有冲突 → 事实通道优先（先修正认知，再修文字）
        if conflicts:
            return {
                "review_decision": "re_research",
                "conflicts": conflicts,
                "re_research_count": re_research_count + 1,
                "re_research_queries": re_research_queries,
                "feedback": "",  # 事实通道不走 writer
                **_step_delta("reviewer", "re_research"),
            }

        # ── 文字通道（阶段 2）：评估报告质量 ─────────────────────
        if rewrite_count >= settings.max_rewrites:
            return {
                "review_decision": "pass",
                "rewrite_count": rewrite_count,
                "feedback": f"已达最大重写次数 {settings.max_rewrites}，强制通过。",
                **_step_delta("reviewer", "rewrite_limit"),
            }

        resp = smart_llm.invoke(
            f"你是严格的研究报告审稿人。评估以下报告是否合格，"
            f"判断标准：结构完整（有概述+要点）、信息量充足、表述专业。\n\n"
            f"报告：\n{report}\n\n"
            f"只回复一个词：合格 或 不合格。若不合格，另起一行用一句话说明问题。"
        )
        _tok = _token_delta("reviewer", resp)  # AgentOps L02
        content = resp.content.strip()

        if "不合格" in content or "不合格" in content.split("\n")[0]:
            decision = "rework"
            feedback_lines = content.split("\n", 1)
            feedback = feedback_lines[1].strip() if len(feedback_lines) > 1 else "报告质量不达标，请改进。"
        else:
            decision = "pass"
            feedback = ""

        return {
            "review_decision": decision,
            "rewrite_count": rewrite_count + 1,
            "feedback": feedback,
            **_step_delta("reviewer", decision),
            **_tok,
        }

    return reviewer


def check_conflicts(findings: list[str], mem_store, llm) -> dict:
    """检测新 findings 与记忆旧结论的冲突（Frontier L05 事实通道核心）。

    流程：
        1. 对每条 finding，recall 记忆中的旧结论
        2. 让 LLM judge 判断「一致 / 冲突 / 无关」
        3. 冲突的，生成定向补研问题（"验证 X 到底对不对"）

    无 LLM 时降级为关键词重叠检测（粗糙但能跑）。
    """
    conflicts: list[str] = []
    queries: list[str] = []

    for finding in findings:
        if not finding or len(finding) < 10:
            continue
        # recall 相关旧记忆
        hits = mem_store.recall(finding[:50], k=2)
        old_conclusions = [m.conclusion for m in hits.get("semantic", [])]
        if not old_conclusions:
            continue  # 无旧结论，无冲突

        old_text = "; ".join(old_conclusions[:2])

        if llm is not None:
            try:
                resp = llm.invoke(
                    f"判断新发现与旧结论的关系，只回复一个词：一致 / 冲突 / 无关。\n"
                    f"新发现：{finding[:200]}\n旧结论：{old_text[:200]}"
                )
                verdict = resp.content.strip()
                if "冲突" in verdict:
                    conflicts.append(f"新发现「{finding[:60]}」与旧结论「{old_text[:60]}」冲突")
                    # 生成定向补研问题
                    q_resp = llm.invoke(
                        f"新发现与旧结论冲突，生成一个定向补研问题来验证真相：\n"
                        f"新：{finding[:100]}\n旧：{old_text[:100]}\n"
                        f"只输出问题本身，不要编号。"
                    )
                    queries.append(q_resp.content.strip())
            except Exception as e:
                log.warning(f"冲突检测 LLM 调用失败：{e}")
        else:
            # 降级：简单关键词检测（新发现含"不是""错误""修正"等冲突信号词）
            conflict_signals = ["不是", "错误", "修正", "实际上", "并非", "更正"]
            if any(sig in finding for sig in conflict_signals):
                conflicts.append(f"新发现可能修正旧结论：{finding[:60]}")
                queries.append(f"验证：{finding[:50]}")

    return {"conflicts": conflicts, "queries": queries}


def review_route(state: SystemState) -> str:
    """审稿条件边：双通道路由（Frontier L05 升级）。

    返回：
        - END：通过
        - "writer"：文字不合格，重写
        - "research_team"：事实冲突，定向补研
    """
    decision = state.get("review_decision", "pass")
    rewrite_count = state.get("rewrite_count", 0)
    re_research_count = state.get("re_research_count", 0)
    from .config import settings

    # 通过 → 结束
    if decision == "pass":
        return END

    # 事实冲突 → 补研（未超限时）
    if decision == "re_research" and re_research_count <= settings.max_re_research:
        return "research_team"

    # 文字不合格 → 重写（未超限时）
    if decision == "rework" and rewrite_count < settings.max_rewrites:
        return "writer"

    # 都超限 → 结束
    return END
