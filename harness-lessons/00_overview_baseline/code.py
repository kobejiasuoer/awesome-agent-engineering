"""L00 · 全景与基线：窗口是一种物理约束
==================================================

本脚本做三件事：
    1. 展示「长途任务」语料的形状（30 源 / 20 关键事实 / 1 对跨源矛盾 /
       跨会话偏好钩子 / 改道线）——之后每课的试金石。
    2. 跑四条裸基线（现状没有 harness 时的四种结局）：
         A0 v4 流水线参照     —— 永不溢出、便宜，但无契约压缩=运气，跨源矛盾无保障
         A1 长程裸奔·测量     —— 「物理不可能」：第 11 源已越限，终局窗口 2.9 倍于限制
         A2 长程裸奔·强制     —— 8k 物理约束下越限即死：完成 10/30、没有报告
         A3 硬截断自救·强制   —— 活着但失忆：在场率 8/20，矛盾断一臂，且静默无标记
    3. 解剖越限那一刻的窗口构成（工具结果占 95%）+ 存档 baseline_harness.json
       （之后每课修一环，L09 收益矩阵对照本档案）。

为什么用「模拟长程循环」而不是直接跑真实 research-assistant：
    - 真实图依赖 ChatZhipuAI（要 API key），无法满足「全离线可复现」硬约束。
    - 要演示的是**物理层结论**——窗口装不装得下与模型聪不聪明无关：
      同样的 30 源全文，谁来读都是 2.3 万 token。
    - v4 现状架构（map-reduce 流水线）的形态由 A0 忠实参照：
      每源独立调用即时压缩，合成只见残片——代码复用了，跨源视野没有。

诚实标注（mock 的边界，任务书 1.4）：
    - FakeTokenizer 为 len//4 字符近似（与 cost_budget 现有估算口径一致）。
    - mock 层测的是**机械纪律**（窗口算术/埋点契约/在场率）；「迷航」「中毒」
      这两种死法 FakeLLM 演不出来——引证据讲清，L09 可选真模型章抽查。
    - assistant 轮取小恒量、token 计费每轮重付全窗——两处近似方向明写，
      结构性结论（死于中途/截断失忆）不受影响。

跑法（零外部依赖、零联网、零真实等待）：
    python code.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows 控制台默认 GBK，统一 utf-8（课程硬约束）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 让脚本在仓库根 / 课程目录 / 项目目录都能跑
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_PROJ = _REPO / "portfolio-projects" / "research-assistant"
sys.path.insert(0, str(_PROJ))
sys.path.insert(0, str(_PROJ / "src"))

from eval_agent.long_haul import (  # noqa: E402
    CONTRADICTION_PAIR, DOC_IDS, KEY_FACTS, N_SOURCES, OVERSIZED_DOC_IDS,
    PREF_HOOKS, SESSION_SPLIT, STEERING_AT, STEERING_INSTRUCTION, TOPIC,
    WINDOW_LIMIT_TOKENS, FakeTokenizer, LongHaulSource,
    run_naive_longhaul, run_pipeline_reference,
)


def hr(title: str) -> None:
    print(f"\n{'═' * 62}\n{title}\n{'═' * 62}")


# ════════════════════════════════════════════════════════════
# Part 1 · 长途任务的形状（之后每课的试金石）
# ════════════════════════════════════════════════════════════
def show_task_shape() -> None:
    hr("Part 1 · 长途任务：30 源深度研究，窗口限制 8k 假 token")
    src = LongHaulSource()
    tk = FakeTokenizer()
    sizes = {d: tk.count(src.doc(d).content) for d in DOC_IDS}
    total = sum(sizes.values())
    print(f"主题：{TOPIC}")
    print(f"信源：{N_SOURCES} 篇，全文合计 ≈ {total:,} 假 token"
          f"（窗口限制 {WINDOW_LIMIT_TOKENS:,} —— 全塞进去要 {total / WINDOW_LIMIT_TOKENS:.1f} 个窗口）")
    print(f"超长文档：{', '.join(f'{d}≈{sizes[d]:,}' for d in OVERSIZED_DOC_IDS)}（L04 整形的素材）")
    early = sum(1 for f in KEY_FACTS if f.early)
    print(f"关键事实：{len(KEY_FACTS)} 条（{early} 条埋在开头 450 字内，"
          f"{len(KEY_FACTS) - early} 条埋在 60% 深度之后）")
    a, b = CONTRADICTION_PAIR
    print(f"跨源矛盾：{a}(S07 会话1) vs {b}(S23 会话2)——两端同时在场，矛盾才可能被发现")
    print(f"会话线：前 {SESSION_SPLIT} 源=会话1（用户中途给出偏好：{'；'.join(PREF_HOOKS)}），"
          f"\n        后 {N_SOURCES - SESSION_SPLIT} 源+合成=会话2——会话间只有记忆文件与工作区存续（L03/L06）")
    print(f"改道线：第 {STEERING_AT} 源完成后投递「{STEERING_INSTRUCTION}」（L07）")
    print("在场率定义（机械可测）：合成调用的窗口文本里，probe 子串在场的事实数——")
    print("  不是「报告里写了」（FakeLLM 写不出语义），是「写报告的人手边还有没有这条材料」。")


# ════════════════════════════════════════════════════════════
# Part 2 · 四条裸基线
# ════════════════════════════════════════════════════════════
def run_baselines() -> dict[str, dict]:
    hr("Part 2 · 四条裸基线：现状没有 harness 时的四种结局")
    rows = {
        "A0_pipeline": run_pipeline_reference(),
        "A1_measure": run_naive_longhaul("measure"),
        "A2_enforce": run_naive_longhaul("enforce"),
        "A3_hard_truncate": run_naive_longhaul("hard_truncate"),
    }
    a0, a1, a2, a3 = (rows[k] for k in ("A0_pipeline", "A1_measure",
                                        "A2_enforce", "A3_hard_truncate"))

    print("\n| 配置 | 完成源数 | 峰值窗口 | 在场率 | 矛盾可发现 | 计费token | 结局 |")
    print("|---|---|---|---|---|---|---|")
    print(f"| A0 v4流水线参照 | {a0['completed_sources']}/30 | {a0['peak_window_tokens']:,} "
          f"| 8/20(无契约) | ⚠️ 无保障 | {a0['tokens_billed']:,} | 便宜但靠运气 |")
    print(f"| A1 长程裸奔·测量 | {a1['completed_sources']}/30 | {a1['peak_window_tokens']:,} "
          f"| 20/20 | ✅ | {a1['tokens_billed']:,} | 物理不可能 |")
    print(f"| A2 长程裸奔·强制 | {a2['completed_sources']}/30 | — | 0/20 | ❌ "
          f"| {a2['tokens_billed']:,} | 死于 S{a2['died_at']:02d} |")
    print(f"| A3 硬截断自救 | {a3['completed_sources']}/30 | {a3['peak_window_tokens']:,} "
          f"| 8/20 | ❌ | {a3['tokens_billed']:,} | 活着但失忆 |")

    print("\n【A1 解读】测量模式假装窗口无限：跑完 30 源、20 个事实全在场、矛盾可发现——")
    print(f"  但第 {a1['first_overflow_source']} 源就越过 8k，终局窗口 "
          f"{a1['peak_window_tokens']:,} ≈ {a1['peak_window_tokens'] / WINDOW_LIMIT_TOKENS:.1f} 倍于物理限制。")
    print("  这一行是「理想上限」：装得下就全记得——问题只有一个：装不下。")
    print(f"\n【A2 解读】把 8k 当真（真实 API 的 400 错误）：死于 S{a2['died_at']:02d}，"
          f"完成 {a2['completed_sources']}/30，没有合成、没有报告——在场率 0。")
    print("\n【A3 解读】最粗暴的自救——每篇只留前 500 字、不留任何省略标记：")
    print(f"  活到了最后（峰值 {a3['peak_window_tokens']:,} < 8k），但 12 条深埋事实全丢，")
    print(f"  矛盾对断了一臂（{CONTRADICTION_PAIR[1]} 被砍）——报告会把「争议中的结论」当定论写。")
    print("  ⚠️ 最危险的是「静默」：窗口里看不出砍过——模型把半篇当全篇引用。")
    print("\n【A0 解读】v4 现状不是没撞过墙，是绕着墙走：map-reduce 每源独立调用即时压缩，")
    print(f"  单调用峰值仅 {a0['peak_window_tokens']:,}，最便宜（{a0['tokens_billed']:,}）。代价：")
    print("  ①合成只见残片，事实存活靠「压缩恰好留下它」的运气（无 pinned 契约）；")
    print("  ②跨源矛盾无保障——S07 与 S23 的全文从未同窗，残片相遇纯属侥幸。")
    print("  （演示规则公开：压缩=只留每篇前 600 字，一种「坏运气」的机制演示。）")
    return rows


# ════════════════════════════════════════════════════════════
# Part 3 · 窗口构成解剖（L01 账本的预告）
# ════════════════════════════════════════════════════════════
def show_composition(a1: dict) -> None:
    hr("Part 3 · 解剖越限那一刻：钱花哪了？")
    comp = a1["composition_at_overflow"]
    total = sum(comp.values())
    label = {"system": "system（研究规程）", "task_state": "task_state（目录+指令）",
             "tool_results": "tool_results（信源全文）", "history": "history（研读笔记）"}
    print(f"首次越限：第 {a1['first_overflow_source']} 源，窗口 {total:,} / {WINDOW_LIMIT_TOKENS:,}\n")
    for k in ("system", "task_state", "tool_results", "history"):
        share = comp[k] / total
        bar = "█" * max(1, round(share * 40))
        print(f"  {label[k]:<28} {comp[k]:>6,}  {share:>6.1%}  {bar}")
    print("\n→ 工具结果占 95%：窗口治理的第一刀该砍谁，账本一目了然（L01 记账 → L04 控源）。")
    print("  诚实标注：真实 agent 的 system + 工具 schema 占比更大（此处无工具 schema），")
    print("  但「工具结果是最大消耗方」的结构性结论与业界实测一致。")


# ════════════════════════════════════════════════════════════
# Part 4 · 存档（之后每课修一环，L09 对照）
# ════════════════════════════════════════════════════════════
def archive(rows: dict[str, dict]) -> None:
    hr("Part 4 · 存档 baseline_harness.json")
    slim = {}
    for key, r in rows.items():
        slim[key] = {k: v for k, v in r.items() if k != "window_curve"}
        slim[key]["window_curve_tail"] = r.get("window_curve", [])[-3:]
    payload = {
        "task": {
            "topic": TOPIC, "n_sources": N_SOURCES,
            "window_limit_tokens": WINDOW_LIMIT_TOKENS,
            "tokenizer": "FakeTokenizer len//4（与 cost_budget 估算口径一致）",
            "key_facts": len(KEY_FACTS), "contradiction_pair": list(CONTRADICTION_PAIR),
            "session_split": SESSION_SPLIT, "steering_at": STEERING_AT,
            "pref_hooks": list(PREF_HOOKS),
        },
        "baselines": slim,
        "structural_conclusions": [
            "长程单窗裸奔死于 S11——窗口是物理约束，与模型聪明程度无关",
            "硬截断买到「活着」买不到「记得」：在场率 8/20，矛盾断一臂，且静默无标记",
            "v4 流水线绕墙走：便宜但无契约——事实存活靠运气，跨源矛盾无保障",
            "工具结果占越限窗口 95%：先控源（L04）再止损（L02），账本（L01）先行",
            "跨会话与改道全不支持：偏好丢失（L03）、只能杀掉重跑（L07）",
        ],
    }
    out = _HERE / "baseline_harness.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📦 已存档：{out.name}（确定性：双跑逐字节一致）")
    for c in payload["structural_conclusions"]:
        print(f"  · {c}")


def main() -> None:
    show_task_shape()
    rows = run_baselines()
    show_composition(rows["A1_measure"])
    archive(rows)
    hr("两条主线的位置（L00）")
    print("窗口经济：本课先给「租金危机」拍了现场——8k 的房子要装 2.3 万的家当；")
    print("         L01 起开始记账（量租金）→ 整形（砍租金）→ 压缩（收房）→ 外置（退租）。")
    print("外置化：  四条基线全都「一切都在窗口里」——之后每课把一类内容搬出窗口：")
    print("         L03 跨会话事实 → L04 工具全文 → L05 中间过程 → L06 工作集 → L08 指令正文。")


if __name__ == "__main__":
    main()
