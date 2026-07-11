"""L01 · 记忆分层演示：MemoryStore 让第二次研究记得第一次。

演示流程：
    1. 创建 MemoryStore（Chroma 持久化，无 key 时降级假 embedding）
    2. 模拟第 1 次研究：写入几条情景记忆（remember）
    3. 模拟第 2 次研究：研究前 recall，看是否命中第 1 次的记忆
    4. 对比 L00 基线（recall 命中=0）vs 本课（recall 命中>0）
    5. 演示 consolidate（把多条情景记忆归纳成语义结论）

不依赖真实 LLM API（consolidate 用降级模式）。
embedding 无 key 时自动降级假向量（字符频次），保证零网络可跑。

跑法：
    cd frontier-lessons/01_memory
    python code.py
    # 有 ZHIPUAI_API_KEY 时用真 embedding（recall 质量更高）：
    ZHIPUAI_API_KEY=xxx python code.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 把 research-assistant 的 src 加到 path
_HERE = Path(__file__).resolve().parent
_RA_SRC = _HERE.parents[1] / "portfolio-projects" / "research-assistant" / "src"
sys.path.insert(0, str(_RA_SRC))


def main():
    from research_assistant.memory import MemoryStore

    print("=" * 60)
    print("L01 记忆分层演示：第二次研究记得第一次")
    print("=" * 60)

    # 用固定目录做持久化（Windows 下 Chroma 文件锁，临时目录清理会失败）
    demo_dir = _HERE / "demo_mem"
    if demo_dir.exists():
        shutil.rmtree(demo_dir, ignore_errors=True)
    demo_dir.mkdir(exist_ok=True)
    store = MemoryStore(persist_path=str(demo_dir))

    print(f"\n[embedding] {'真实(智谱embedding-3)' if store._embedder.is_real else '假(字符频次降级)'}")
    print(f"[存储] {'Chroma向量库' if store._chroma is not None else '内存降级模式'}")

    # ── 第 1 次研究：写入情景记忆 ──────────────────────────
    print("\n── 第 1 次研究：写入记忆 ─────────────────────")
    # (发现内容, 主题) —— 模拟 researcher 产出的 findings
    run1_findings = [
        ("MCP 协议基于 JSON-RPC 2.0，由 Anthropic 于 2024 年发布", "MCP"),
        ("主流 MCP server 已覆盖文件系统、数据库、搜索引擎等场景", "MCP"),
        ("MCP SDK 支持 Python/TypeScript/Java 三种语言", "MCP"),
    ]
    for content, topic in run1_findings:
        store.remember(content, topic=topic, source="run1")
        print(f"  remember: [{topic}] {content[:50]}")

    # ── 第 2 次研究：recall 看是否记得 ─────────────────────
    print("\n── 第 2 次研究：研究前 recall ─────────────────")
    queries = [
        "MCP 协议设计",
        "MCP 支持哪些语言",
        "MCP 有哪些工具",
    ]
    total_hits = 0
    for q in queries:
        hits = store.recall(q, k=3)
        epi = hits["episodic"]
        sem = hits["semantic"]
        total_hits += len(epi) + len(sem)
        print(f"  recall('{q}'): episodic={len(epi)}, semantic={len(sem)}")
        for h in epi[:2]:
            print(f"    [情景] {h.content[:60]}")

    print(f"\n  → 第 2 次共命中 {total_hits} 条记忆")

    # ── 对比 L00 基线 ─────────────────────────────────────
    print("\n── 对比 L00 基线 ──────────────────────────────")
    print(f"  L00 基线：第 2 次 recall 命中 = 0（完全失忆）")
    print(f"  L01 现在：第 2 次 recall 命中 = {total_hits}（记得第 1 次）")
    verdict = "记忆机制成立 ✅" if total_hits > 0 else "记忆机制未生效 ❌"
    print(f"  结论：{verdict}")

    # ── 演示 consolidate（巩固）──────────────────────────
    print("\n── consolidate：多条情景 → 一条语义结论 ────────")
    # 无 LLM 降级模式（L02 接入真实反思式提炼）
    sem_results = store.consolidate(llm=None)
    for s in sem_results:
        print(f"  [语义] topic={s.topic}")
        print(f"          conclusion={s.conclusion[:60]}")
        print(f"          confidence={s.confidence}")
    print("\n  （有 LLM 时会提炼成更精炼的结论，L02 接入真实反思式写入）")

    # ── 演示 format_recall_for_prompt ────────────────────
    print("\n── format_recall_for_prompt：注入 prompt 的样子 ─")
    hits = store.recall("MCP 协议", k=2)
    prompt_text = store.format_recall_for_prompt(hits)
    print(prompt_text[:400] if prompt_text else "  （无命中）")

    print("\n" + "=" * 60)
    print("✅ 演示完成。记忆机制：remember → recall → 注入 prompt → 第二次记得第一次")
    print("⚠️  recall 精度取决于 embedding 质量：真 embedding(智谱) > 假 embedding(字符)")
    print("=" * 60)


if __name__ == "__main__":
    main()
