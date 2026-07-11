"""L03 · Skills 渐进式加载演示。

演示流程：
    1. 扫描 research-assistant/skills/ 目录（2 个示例 skill）
    2. 展示第一层：只看一行描述（进 system prompt，极省 token）
    3. 展示第二层：匹配后加载全文（用到才加载）
    4. 对比"全塞 system prompt"vs"渐进式"的 token 量级
    5. 演示同一任务加载/不加载 skill 的输出差异

跑法：
    cd frontier-lessons/03_skills
    python code.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_RA_SRC = _HERE.parents[1] / "portfolio-projects" / "research-assistant" / "src"
sys.path.insert(0, str(_RA_SRC))


def _estimate_tokens(text: str) -> int:
    """粗估 token 数（中文≈字数，英文≈词数×1.3，混合取字符数/2）。"""
    return max(1, len(text) // 2)


def main():
    from research_assistant.skill_loader import SkillLoader

    print("=" * 60)
    print("L03 Skills 渐进式加载：能力的按需调回")
    print("=" * 60)

    # 用 research-assistant 的真实 skills 目录
    skills_dir = _HERE.parents[1] / "portfolio-projects" / "research-assistant" / "skills"
    loader = SkillLoader(skills_dir=skills_dir)

    metas = loader.list_skills()
    print(f"\n[扫描] 找到 {len(metas)} 个 skill @ {skills_dir}")
    for m in metas:
        print(f"  - {m.name}: {m.description}")

    # ── 第一层：描述（始终在上下文）────────────────────────
    print("\n── 第一层：描述（进 system prompt）─────────────")
    desc_text = loader.format_skill_descriptions()
    print(desc_text)
    desc_tokens = _estimate_tokens(desc_text)
    print(f"  → token 估算：{desc_tokens}（不管有多少 skill，描述都很轻）")

    # ── 第二层：全文（用到才加载）──────────────────────────
    print("\n── 第二层：全文（用到才加载）────────────────────")

    # 模拟一个涉及"对比"的研究任务
    query = "研究 MCP 和传统 function calling 的对比"
    print(f"  任务：{query}")
    matched = loader.match_skills(query)
    print(f"  匹配 skill：{matched}")

    full_text = loader.load_matched_skills(query)
    full_tokens = _estimate_tokens(full_text) if full_text else 0
    if full_text:
        print(f"  加载全文：{full_tokens} token")
        print(f"  预览：{full_text[:150]}...")

    # 模拟一个不涉及对比的任务
    query2 = "研究 MCP 协议的设计原理"
    print(f"\n  任务：{query2}")
    matched2 = loader.match_skills(query2)
    print(f"  匹配 skill：{matched2}")
    full_text2 = loader.load_matched_skills(query2)
    print(f"  加载全文：{'有' if full_text2 else '无（不相关，不加载）'}")

    # ── 对比：全塞 vs 渐进式 ───────────────────────────────
    print("\n── 对比：全塞 system prompt vs 渐进式 ──────────")
    all_full = "\n".join(loader.load_skill(m.name) for m in metas)
    all_tokens = _estimate_tokens(all_full)
    print(f"  全塞（所有 skill 全文进 system prompt）：{all_tokens} token")
    gradual = desc_tokens + full_tokens
    print(f"  渐进式（描述 + 用到的）：{gradual} token")
    if all_tokens > 0:
        pct = (1 - gradual / all_tokens) * 100
        print(f"  节省：{all_tokens - gradual} token（{pct:.0f}%）")
    print(f"  → skill 数量越多，渐进式优势越大（全塞线性增长，渐进式只加载用到的）")

    # ── 演示输出差异 ──────────────────────────────────────
    print("\n── 同一任务：加载/不加载 skill 的输出差异 ────────")
    print("  [不加载 skill] writer 会按默认格式写报告（无结构规范）")
    print("  [加载 skill]  writer 会遵循 skill 规定的格式：")
    print("    - 研究简报格式：摘要/核心要点/增量标注/来源")
    print("    - 对比表格式：| 维度 | A | B | + 对比结论")
    print("  → skill 让输出质量从'随机'变为'规范'，且只在用到时占上下文")

    # ── 统一框架 ──────────────────────────────────────────
    print("\n── 上下文工程统一框架 ───────────────────────────")
    print("  记忆   = 经验的按需调回（recall）    L01-L02")
    print("  RAG    = 知识的按需调回（retrieve）  rag-lessons")
    print("  Skills = 能力的按需调回（load）      本课")
    print("  MCP    = 工具的远程调用（call_tool） ops-lessons")
    print("  → 四者同属「上下文窗口里该放什么、何时放、怎么淘汰」一个母题")

    print("\n" + "=" * 60)
    print("✅ Skills = 渐进式上下文加载。能力做成按需加载的文件夹，不用不占窗口。")
    print("=" * 60)


if __name__ == "__main__":
    main()
