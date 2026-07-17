"""服务层：把 LangGraph 图的执行封装成可调用的服务。

提供两种入口：
    - invoke(topic, thread_id)：同步式（实际 async），返回最终 state（CLI / 简单调用用）
    - stream_research(topic, thread_id)：异步生成器，yield SSE 事件 dict（FastAPI 用）

SSE 事件协议（双层流，阶段 3 核心）：
    {event: "progress", data: {node, ...delta}}   —— 节点级进度（updates 模式）
    {event: "token",    data: {node, content}}    —— writer LLM 逐 token（messages 模式）
    {event: "done",     data: {report, findings, review}} —— 最终报告
    {event: "error",    data: {message}}          —— 异常

设计决策（写进 README）：
    - 双层流 = 进度事件（updates）+ token 流（messages），
      单次 astream 多模式同时产出，前端既能显示"研究子题中..."又能让报告逐字流出。
    - writer 在父图顶层（不在嵌套子图），token 流可靠（规避 langgraph#6105
      的嵌套子图事件传播问题）。
"""
from __future__ import annotations

import json
import time
from typing import AsyncIterator

from langchain_core.messages import AIMessage

from .config import settings
from .graph import build_research_subgraph, build_system
from .logging_config import get_logger
from .models import make_fast_llm, make_smart_llm
from .persist import get_async_saver_context

logger = get_logger("service")


def _trace_path() -> Path:
    """轨迹文件路径（Frontier L08）：每次运行产出 traces/run_<ts>.jsonl。"""
    from datetime import datetime
    from pathlib import Path
    here = Path(__file__).resolve().parent  # src/research_assistant/
    traces_dir = here.parent.parent / "traces"
    traces_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return traces_dir / f"run_{ts}.jsonl"


def _record_trace(trace_path: Path, step: int, node: str, inp: str, out: str):
    """记录一条轨迹到 jsonl 文件（Frontier L08）。"""
    from datetime import datetime, timezone
    try:
        rec = {
            "step": step,
            "node": node,
            "input": str(inp)[:500],
            "output": str(out)[:500],
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"轨迹记录失败（不阻塞）：{e}")


def _initial_state(topic: str) -> dict:
    """构造一次新研究的输入 State。"""
    return {
        "messages": [{"role": "user", "content": topic}],
        "findings": [],
        "research_summary": "",
        "report": "",
        "review_decision": "",
        "rewrite_count": 0,
        "feedback": "",
        # Frontier L05：双通道 reviewer 事实修正通道
        "conflicts": [],
        "re_research_count": 0,
        "re_research_queries": [],
        # AgentOps L01：全局步数预算 + 诚实收尾
        "step_count": 0,
        "truncated": False,
        "action_history": [],
        # AgentOps L02：轨迹级成本预算
        "token_usage": 0,
        "cost_mode": "normal",
        # AgentOps L03：诚实降级协议
        "failed_subtopics": [],
        # AgentOps L04：副作用发布结果
        "publish_result": {},
        # Ambient L03：增量研究焦点 + 旧结论上下文（默认空 = 现状全量行为）
        "incremental_focus": [],
        "prior_context": "",
    }


async def invoke(topic: str, thread_id: str, extra_state: dict | None = None) -> dict:
    """跑一次完整研究，返回最终 state（含 report/findings/review）。

    供不需要流式的场景用（如内部调用、测试）。

    Ambient L03：extra_state 允许调用方注入增量焦点/旧结论上下文
    （run_incremental 用；不传 = 现状全量行为，一字不差）。

    Frontier L02：研究结束后若 enable_memory，异步触发 reflect_and_store，
    把本次发现提炼成记忆条目存入 MemoryStore（第二次研究才能 recall 到）。
    """
    fast_llm = make_fast_llm()
    smart_llm = make_smart_llm()
    sub = build_research_subgraph(fast_llm, smart_llm)

    # Frontier L07：重置代码执行历史（每次新研究清空附录）
    if settings.enable_code_interpreter:
        try:
            from .code_interpreter import reset_executed_codes
            reset_executed_codes()
        except Exception:
            pass

    # AgentOps L02：重置本次运行的成本 tracker
    from .cost_budget import reset_tracker
    reset_tracker()

    async with get_async_saver_context() as saver:
        system = build_system(smart_llm, fast_llm, sub, checkpointer=saver)
        config = {"configurable": {"thread_id": thread_id}}
        t0 = time.time()
        initial = _initial_state(topic)
        if extra_state:
            initial = {**initial, **extra_state}  # 不可变合并（Ambient L03）
        result = await system.ainvoke(initial, config=config)
        serialized = _serialize_state(result)

        # AgentOps L07：输出 run summary 体检报告（enable_run_summary 时）
        if settings.enable_run_summary:
            from .run_summary import build_summary, emit_summary
            summary = build_summary(serialized, run_id=thread_id, thread_id=thread_id,
                                    topic=topic, elapsed=time.time() - t0)
            emit_summary(summary)

        # ── 反思式写入（Frontier L02）──────────────────────
        # 研究结束后把 findings 提炼成记忆条目。失败不阻塞主流程（降级）。
        if settings.enable_memory:
            try:
                from .nodes import get_memory_store
                from .memory import reflect_and_store
                mem_store = get_memory_store()
                if mem_store is not None:
                    findings = serialized.get("findings", [])
                    # 用 smart_llm 提炼（质量优先）；失败降级规则抽取
                    try:
                        reflect_and_store(findings, topic, mem_store, llm=smart_llm)
                    except Exception as e:
                        # LLM 提炼失败 → 规则降级（不丢记忆，只是质量低些）
                        logger.info(f"LLM 反思失败，降级规则抽取：{e}")
                        reflect_and_store(findings, topic, mem_store, llm=None)
                    # 定期巩固（每次研究后尝试，把情景记忆归纳成语义结论）
                    mem_store.consolidate(llm=smart_llm)
            except Exception as e:
                logger.warning(f"反思式写入整体失败（不阻塞主流程）：{e}")

        return serialized


async def submit_research(topic: str, thread_id: str | None = None) -> dict:
    """提交一个研究任务（长任务异步化，AgentOps L06）。

    与 invoke 的区别：
        - invoke：同步等结果（适合短任务 / 测试）
        - submit_research：立即返回 task_id，后台跑（适合长任务）

    enable_job_registry=False 时退化为直接 invoke + 不登记（现状行为）。
    enable_job_registry=True 时登记进 jobs 表，崩溃可恢复。
    """
    if not settings.enable_job_registry:
        # 现状行为：直接跑
        thread_id = thread_id or f"thread-{__import__('uuid').uuid4().hex[:8]}"
        result = await invoke(topic, thread_id)
        return {"task_id": None, "thread_id": thread_id, "status": "done", "result": result}

    from .jobs import submit_job, update_status, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED
    job = submit_job(topic, thread_id)
    task_id = job["task_id"]
    thread_id = job["thread_id"]

    update_status(task_id, STATUS_RUNNING)
    try:
        result = await invoke(topic, thread_id)
        update_status(task_id, STATUS_DONE, result=result)
        return {"task_id": task_id, "thread_id": thread_id, "status": "done", "result": result}
    except Exception as e:
        update_status(task_id, STATUS_FAILED, error=str(e))
        raise


async def resume_job(task_id: str) -> dict:
    """断点续跑：从 checkpoint 恢复一个崩溃/中断的任务（AgentOps L06 核心）。

    机制：同 thread_id 以 None 输入重新 ainvoke → langgraph 从最后 checkpoint 续跑。
    - 已完成的 researcher/writer 不重跑（checkpoint 记录了已完成节点）
    - 已执行的副作用靠 L04 幂等键不重放（同内容 no-op）
    - 重做量 = 从最后一个未完成节点到 END（而非全部重跑）

    Returns:
        恢复后的最终 state
    """
    from .jobs import get_job, update_status, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED, STATUS_INTERRUPTED

    job = get_job(task_id)
    if job is None:
        raise ValueError(f"任务 {task_id} 不存在")
    if job["status"] not in (STATUS_RUNNING, STATUS_INTERRUPTED, STATUS_FAILED):
        # 已完成的不恢复
        return job.get("result") or {"status": job["status"]}

    thread_id = job["thread_id"]
    topic = job["topic"]
    update_status(task_id, STATUS_RUNNING)

    fast_llm = make_fast_llm()
    smart_llm = make_smart_llm()
    sub = build_research_subgraph(fast_llm, smart_llm)
    from .cost_budget import reset_tracker
    reset_tracker()

    async with get_async_saver_context() as saver:
        system = build_system(smart_llm, fast_llm, sub, checkpointer=saver)
        config = {"configurable": {"thread_id": thread_id}}
        # ⭐ 关键：None 输入 → 从最后 checkpoint 续跑（不重做已完成节点）
        result = await system.ainvoke(None, config=config)
        serialized = _serialize_state(result)
        update_status(task_id, STATUS_DONE, result=serialized)
        return serialized


async def recover_orphans() -> list[dict]:
    """启动时扫描孤儿任务并尝试恢复（AgentOps L06）。

    孤儿任务 = 进程崩了没跑完的（running/interrupted 状态）。
    重启后调本函数，对每个孤儿调 resume_job。

    Returns:
        [{"task_id": ..., "status": "recovered"|"failed", ...}, ...]
    """
    from .jobs import find_orphans
    orphans = find_orphans()
    results = []
    for o in orphans:
        try:
            await resume_job(o["task_id"])
            results.append({"task_id": o["task_id"], "status": "recovered", "topic": o["topic"]})
        except Exception as e:
            results.append({"task_id": o["task_id"], "status": "failed", "error": str(e)})
    return results


async def submit_approval(thread_id: str, approved: bool, comment: str = "") -> dict:
    """提交审批结果，恢复被 interrupt 暂停的 publish（AgentOps L05）。

    用法（API/CLI）：
        1. stream_research 跑到 publish 节点时 interrupt 暂停，SSE 发 approval_required 事件
        2. 人审批后调本函数，带 Command(resume={"approved": ...}) 重新 invoke 同 thread
        3. publish 节点拿到 resume 值，批准则发布，否决则诚实收尾

    跨进程/跨重启恢复：checkpointer 存了中断状态，即使进程退出，
    重启后用同 thread_id 调本函数也能恢复（审批可以隔夜）。

    Returns:
        publish 节点的最终结果（published 或 rejected）
    """
    from langgraph.types import Command

    fast_llm = make_fast_llm()
    smart_llm = make_smart_llm()
    sub = build_research_subgraph(fast_llm, smart_llm)

    async with get_async_saver_context() as saver:
        system = build_system(smart_llm, fast_llm, sub, checkpointer=saver)
        config = {"configurable": {"thread_id": thread_id}}
        # Command(resume=...) 恢复 interrupt，resume 值传给 publish 节点的 interrupt() 返回
        result = await system.ainvoke(
            Command(resume={"approved": approved, "comment": comment}),
            config=config,
        )
        return _serialize_state(result)


def is_awaiting_approval(thread_id: str) -> dict | None:
    """检查某 thread 是否在等审批（AgentOps L05，给 API 轮询用）。

    Returns:
        None = 不在等审批；dict = interrupt 的 value（含 content_preview 等供前端展示）
    """
    import asyncio as _asyncio

    async def _check():
        fast_llm = make_fast_llm()
        smart_llm = make_smart_llm()
        sub = build_research_subgraph(fast_llm, smart_llm)
        async with get_async_saver_context() as saver:
            system = build_system(smart_llm, fast_llm, sub, checkpointer=saver)
            config = {"configurable": {"thread_id": thread_id}}
            state = await system.aget_state(config)
            if state and state.next and "publish" in state.next:
                # 有 publish 任务待执行 + 有 interrupt → 在等审批
                tasks = state.tasks or []
                for t in tasks:
                    if hasattr(t, "interrupts") and t.interrupts:
                        return t.interrupts[0].value
                return {"action": "publish_report", "thread_id": thread_id}
            return None

    try:
        loop = _asyncio.get_event_loop()
    except RuntimeError:
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
    return loop.run_until_complete(_check()) if not loop.is_running() else None


async def stream_research(topic: str, thread_id: str) -> AsyncIterator[dict]:
    """异步生成器：yield SSE 事件 dict。

    用法（FastAPI）：
        async def gen(): async for ev in stream_research(topic, tid): yield ev
        return EventSourceResponse(gen())

    事件类型见模块 docstring。
    """
    fast_llm = make_fast_llm()
    smart_llm = make_smart_llm()
    sub = build_research_subgraph(fast_llm, smart_llm)

    # AgentOps L02：重置本次运行的成本 tracker
    from .cost_budget import reset_tracker
    reset_tracker()

    try:
        async with get_async_saver_context() as saver:
            system = build_system(smart_llm, fast_llm, sub, checkpointer=saver)
            config = {"configurable": {"thread_id": thread_id}}

            final_state: dict = {}
            # Frontier L08：轨迹落盘（每次运行产出 traces/run_<ts>.jsonl）
            trace_file = _trace_path()
            trace_step = 0

            # ⭐ 双模式流：updates（节点进度）+ messages（token 流）
            async for mode, payload in system.astream(
                _initial_state(topic), config=config,
                stream_mode=["updates", "messages"],
            ):
                if mode == "updates":
                    # payload = {node_name: state_delta}
                    for node, delta in payload.items():
                        if not isinstance(delta, dict):
                            continue
                        # 进度事件：告诉前端哪个节点完成了什么
                        progress = _summarize_update(node, delta)
                        yield {"event": "progress", "data": json.dumps(progress, ensure_ascii=False)}
                        # 累积最终 state（最后一次 writer 的 report 就是最终报告）
                        final_state.update(delta)
                        # Frontier L08：记录轨迹
                        trace_step += 1
                        _record_trace(trace_file, trace_step, node,
                                      topic, str(delta)[:500])

                elif mode == "messages":
                    # payload = (message_chunk, metadata)
                    msg_chunk, meta = payload
                    content = msg_chunk.content if hasattr(msg_chunk, "content") else str(msg_chunk)
                    if content:  # 空 chunk 跳过
                        node = meta.get("langgraph_node", "?") if isinstance(meta, dict) else "?"
                        yield {
                            "event": "token",
                            "data": json.dumps({"node": node, "content": content}, ensure_ascii=False),
                        }

            # 最终报告事件
            yield {
                "event": "done",
                "data": json.dumps({
                    "report": final_state.get("report", ""),
                    "findings": final_state.get("findings", []),
                    "review_decision": final_state.get("review_decision", ""),
                    "rewrite_count": final_state.get("rewrite_count", 0),
                }, ensure_ascii=False),
            }

            # ── 反思式写入（Frontier L02）──────────────────────
            # done 事件之后异步触发记忆提炼，不阻塞前端已收到的结果。
            # 失败不抛异常（记忆是增强不是必需，降级保证主流程稳定）。
            if settings.enable_memory:
                try:
                    from .nodes import get_memory_store
                    from .memory import reflect_and_store
                    mem_store = get_memory_store()
                    if mem_store is not None:
                        findings = final_state.get("findings", [])
                        try:
                            reflect_and_store(findings, topic, mem_store, llm=smart_llm)
                        except Exception as e:
                            logger.info(f"LLM 反思失败，降级规则抽取：{e}")
                            reflect_and_store(findings, topic, mem_store, llm=None)
                        mem_store.consolidate(llm=smart_llm)
                        mem_store.forget()  # 遗忘策略：淘汰旧且不用的
                except Exception as e:
                    logger.warning(f"反思式写入整体失败（不阻塞主流程）：{e}")

    except Exception as e:
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": f"{type(e).__name__}: {e}"}, ensure_ascii=False
            ),
        }


# ── 辅助：把节点 delta 摘要成前端友好的进度信息 ──────────────
_NODE_LABELS = {
    "research_team": "并行研究",
    "writer": "撰写报告",
    "reviewer": "审稿",
    "split": "拆解子题",
    "researcher": "并行检索",
    "summarize": "汇总发现",
}


def _summarize_update(node: str, delta: dict) -> dict:
    """把节点 state delta 摘要成前端可读的进度事件。"""
    info = {"node": node, "label": _NODE_LABELS.get(node, node)}
    if node == "research_team" and "research_summary" in delta:
        info["status"] = "研究完成，开始撰写"
        info["findings_count"] = len(delta.get("findings", []))
    elif node == "writer" and "report" in delta:
        info["status"] = f"报告已生成（{len(delta.get('report', ''))} 字）"
    elif node == "reviewer":
        info["status"] = f"审稿：{delta.get('review_decision', '?')}"
        info["rewrite_count"] = delta.get("rewrite_count", 0)
    else:
        info["status"] = "完成"
        info["keys"] = list(delta.keys())
    return info


def _serialize_state(state: dict) -> dict:
    """把 state 里不可 JSON 序列化的对象（AIMessage 等）转成纯文本。"""
    out = {}
    for k, v in state.items():
        if k == "messages":
            out[k] = [
                {"role": "assistant" if isinstance(m, AIMessage) else "user",
                 "content": m.content if hasattr(m, "content") else str(m)}
                for m in v
            ]
        else:
            out[k] = v
    return out
