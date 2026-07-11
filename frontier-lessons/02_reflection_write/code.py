"""L02 · 反思式写入与巩固演示：记忆不是录像是提炼。

演示流程：
    1. 对比"存原文 vs 存提炼"：同样 findings，两种存法，看 recall 质量
    2. 反思式写入：LLM（或降级规则）从 findings 提炼结构化记忆条目
    3. 巩固：多条情景记忆 → 一条语义结论
    4. 遗忘：超过上限/过旧的情景记忆被淘汰

不依赖真实 LLM（用 mock LLM 演示提炼效果）。

跑法：
    cd frontier-lessons/02_reflection_write
    python code.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_RA_SRC = _HERE.parents[1] / "portfolio-projects" / "research-assistant" / "src"
sys.path.insert(0, str(_RA_SRC))


# Mock LLM：模拟 glm-4 的反思提炼能力
class MockReflectLLM:
    """模拟反思 LLM：按预设回复返回结构化记忆条目。"""
    def __init__(self):
        self.call_count = 0

    def invoke(self, prompt):
        self.call_count += 1
        # 如果是 consolidate 的 prompt（含"归纳"）
        if "归纳" in prompt:
            class R:
                content = "MCP 是 Anthropic 提出的标准化工具协议，基于 JSON-RPC，生态覆盖多语言多场景 | 多条记录一致 | 0.85"
            return R()
        # 否则是 reflect_and_store 的 prompt
        class R:
            content = (
                "MCP 协议基于 JSON-RPC 2.0 | 0.9 | 事实\n"
                "MCP SDK 支持 Python/TypeScript/Java | 0.8 | 事实\n"
                "MCP 生态在快速扩展，覆盖文件/数据库/搜索 | 0.7 | 结论"
            )
        return R()


def main():
    from research_assistant.memory import MemoryStore, reflect_and_store

    print("=" * 60)
    print("L02 反思式写入与巩固：记忆不是录像是提炼")
    print("=" * 60)

    # 原始 findings（模拟 researcher 产出）
    findings = [
        "【MCP 协议设计】\n  发现：MCP 协议基于 JSON-RPC 2.0，由 Anthropic 于 2024 年发布，"
        "采用 client-server 架构，支持工具/资源/prompts 三类能力。\n  来源：真实联网搜索",
        "【MCP SDK】\n  发现：MCP SDK 支持 Python/TypeScript/Java 三种语言，"
        "社区有 Go/Rust 等第三方实现。\n  来源：真实联网搜索",
        "【MCP 生态】\n  发现：主流 MCP server 已覆盖文件系统、数据库、搜索引擎等场景，"
        "生态在快速扩展中。\n  来源：真实联网搜索",
    ]

    llm = MockReflectLLM()

    # ── 对比 1：存原文 vs 存提炼 ────────────────────────────
    print("\n── 对比：存原文 vs 存提炼 ─────────────────────")

    # 方案 A：存原文
    dir_a = _HERE / "mem_raw"
    if dir_a.exists():
        shutil.rmtree(dir_a, ignore_errors=True)
    store_a = MemoryStore(persist_path=str(dir_a))
    store_a._chroma = None  # 强制内存模式便于演示
    for f in findings:
        store_a.remember(f, topic="MCP", source="raw")
    print(f"  方案A（存原文）：写入 {len(findings)} 条原始 finding（含格式/来源/噪声）")

    # 方案 B：存提炼
    dir_b = _HERE / "mem_refined"
    if dir_b.exists():
        shutil.rmtree(dir_b, ignore_errors=True)
    store_b = MemoryStore(persist_path=str(dir_b))
    store_b._chroma = None
    reflect_and_store(findings, "MCP", store_b, llm=llm)
    print(f"  方案B（存提炼）：LLM 提炼出 {llm.call_count} 次调用 → 结构化记忆条目")

    # 对比 recall 质量
    print("\n  recall('MCP 协议') 对比：")
    hits_a = store_a.recall("MCP 协议", k=2)
    hits_b = store_b.recall("MCP 协议", k=2)
    print(f"    方案A 命中 {len(hits_a['episodic'])} 条，样例：{hits_a['episodic'][0].content[:60] if hits_a['episodic'] else '无'}...")
    print(f"    方案B 命中 {len(hits_b['episodic'])} 条，样例：{hits_b['episodic'][0].content[:60] if hits_b['episodic'] else '无'}...")
    print(f"  → 方案B 的条目更短、密度更高（去掉了格式符号和来源标记）")

    # ── 对比 2：规则降级 vs LLM 提炼 ────────────────────────
    print("\n── 对比：规则降级 vs LLM 提炼 ──────────────────")
    dir_c = _HERE / "mem_rule"
    if dir_c.exists():
        shutil.rmtree(dir_c, ignore_errors=True)
    store_c = MemoryStore(persist_path=str(dir_c))
    store_c._chroma = None
    reflect_and_store(findings, "MCP", store_c, llm=None)  # 无 LLM
    hits_c = store_c.recall("MCP 协议", k=3)
    print(f"  规则降级：抽取 {len(store_c._episodic)} 条（含'发现'关键词的行）")
    print(f"    样例：{store_c._episodic[0].content[:60] if store_c._episodic else '无'}...")
    print(f"  LLM 提炼：{len(store_b._episodic)} 条结构化条目（带置信度/类型）")
    print(f"  → LLM 提炼质量更高（结构化、去噪）；规则降级是保底（不崩但粗糙）")

    # ── 巩固：多条情景 → 一条语义 ──────────────────────────
    print("\n── 巩固（consolidate）：多条情景 → 一条语义结论 ─")
    print(f"  巩固前：store_b 有 {len(store_b._episodic)} 条情景记忆，0 条语义记忆")
    sem_results = store_b.consolidate(llm=llm)
    print(f"  巩固后：{len(sem_results)} 条语义结论")
    for s in sem_results:
        print(f"    [语义] {s.conclusion[:70]}")
        print(f"           置信度={s.confidence}")

    # ── 遗忘策略 ──────────────────────────────────────────
    print("\n── 遗忘策略 ────────────────────────────────────")
    # 往 store_a 塞很多记忆演示遗忘
    for i in range(15):
        store_a.remember(f"多余记忆 {i}", topic="noise")
    print(f"  塞入 15 条噪音后：store_a 有 {len(store_a._episodic)} 条情景记忆")
    store_a.forget(max_episodic=5, decay_days=0)
    print(f"  forget(max=5) 后：{len(store_a._episodic)} 条（淘汰到上限）")
    print(f"  → 语义记忆不遗忘（{len(store_b._semantic)} 条保留）")

    # 清理
    for d in [dir_a, dir_b, dir_c]:
        shutil.rmtree(d, ignore_errors=True)

    print("\n" + "=" * 60)
    print("✅ 演示完成。反思式写入 = 记忆不是录像，是 LLM 提炼的高密度条目。")
    print("   巩固 = 多条情景 → 一条语义结论（类比人脑记忆巩固）。")
    print("   遗忘 = 时间衰减 + 频次保留，防膨胀防噪音。")
    print("=" * 60)


if __name__ == "__main__":
    main()
