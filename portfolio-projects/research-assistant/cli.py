"""CLI 入口：命令行运行完整研究流程（调试 + 不依赖 Web 也能跑）。

用法：
    python cli.py "研究主题"                    # 单次研究（持久化）
    python cli.py "研究主题" --followup "追问"  # 研究 + 追问（验证持久化）
    python cli.py                               # 用默认主题

阶段 2 新增：
    - SqliteSaver 持久化（杀进程重启后追问仍记得上一轮）
    - 审稿回路（writer → reviewer → 通过/重写）
    - --followup 演示跨轮记忆
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

# 让 `python cli.py` 在项目根目录直接跑也能 import src
sys.path.insert(0, "src")

from research_assistant.config import settings
from research_assistant.graph import build_research_subgraph, build_system
from research_assistant.models import make_fast_llm, make_smart_llm
from research_assistant.persist import get_async_saver_context, is_persistent

DEFAULT_TOPIC = "2024 年 AI Agent 技术的重要进展"


def _initial_state(topic: str) -> dict:
    """构造一次新研究的输入 State（与 service.py 保持一致）。"""
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
    }


async def _run_once(system, topic: str, thread_id: str, label: str) -> dict:
    """跑一次研究并打印结果。返回最终 state。"""
    config = {"configurable": {"thread_id": thread_id}}
    print(f"\n⏳ [{label}] 研究中...\n")
    result = await system.ainvoke(_initial_state(topic), config=config)

    # 输出报告
    print("━" * 64)
    print(f"✅ [{label}] 研究报告：\n")
    print(result["report"])

    print("\n" + "─" * 64)
    print(f"📊 并行研究发现（{len(result['findings'])} 个，含真实来源）：\n")
    for f in result["findings"]:
        for line in f.split("\n"):
            print(f"  {line}")
        print()

    # 审稿信息（阶段 2）
    print("─" * 64)
    print(f"🔍 审稿：决策={result.get('review_decision', '?')}  "
          f"重写次数={result.get('rewrite_count', 0)}/{settings.max_rewrites}")
    print("━" * 64)
    return result


async def run(topic: str, thread_id: str | None, followup: str | None) -> None:
    """运行研究流程（可选追问，验证持久化）。"""
    if not settings.zhipuai_api_key or settings.zhipuai_api_key.startswith("xxxx"):
        raise RuntimeError("请先在 .env（仓库根或项目目录）里配置 ZHIPUAI_API_KEY")

    thread_id = thread_id or f"cli-{uuid.uuid4().hex[:8]}"

    print("═" * 64)
    print("🔬 AI 研究分析助手（生产级 · 阶段 2：审稿回路 + SqliteSaver 持久化）")
    print("═" * 64)
    print(f"📋 研究主题：{topic}")
    print(f"🧠 smart: {settings.smart_model}（汇总/写作/审稿）  "
          f"⚡ fast: {settings.fast_model}（拆题/并行检索）")
    print(f"🧵 thread_id: {thread_id}")
    print(f"💾 持久化：{'SqliteSaver (' + settings.sqlite_db_path + ')' if is_persistent() else 'InMemory（测试模式）'}")

    # 构建图 + saver（saver 用 contextmanager 管理）
    print(f"\n🔧 构建图（research_team → writer → reviewer → 条件回环/结束）...")
    fast_llm = make_fast_llm()
    smart_llm = make_smart_llm()
    research_subgraph = build_research_subgraph(fast_llm, smart_llm)
    print("✅ 图已编译\n")

    async with get_async_saver_context() as checkpointer:
        system = build_system(smart_llm, fast_llm, research_subgraph, checkpointer=checkpointer)

        # 主研究
        await _run_once(system, topic, thread_id, "主研究")

        # 追问（验证持久化）
        if followup:
            print("\n\n" + "═" * 64)
            print(f"💬 追问（同 thread_id={thread_id}，验证记忆）：{followup}")
            print("═" * 64)
            config = {"configurable": {"thread_id": thread_id}}
            # 追问只传 messages，研究字段留空（由 checkpointer 恢复 + 路径自然处理）
            result = await system.ainvoke(
                {"messages": [{"role": "user", "content": followup}]},
                config=config,
            )
            print(f"\n➡️ 追问回答：\n{result['messages'][-1].content[:400]}")
            print("\n💡 若上面回答引用了主研究内容，说明 SqliteSaver 跨轮记忆生效。")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 研究分析助手 CLI")
    parser.add_argument("topic", nargs="?", default=DEFAULT_TOPIC, help="研究主题")
    parser.add_argument("--thread-id", default=None, help="会话 ID（用于记忆/隔离）")
    parser.add_argument("--followup", default=None, help="追问内容（验证跨轮记忆）")
    args = parser.parse_args()
    asyncio.run(run(args.topic, args.thread_id, args.followup))


if __name__ == "__main__":
    main()
