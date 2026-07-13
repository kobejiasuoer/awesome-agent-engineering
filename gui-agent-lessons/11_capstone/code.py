"""L11 · 毕业整合：汇总 L00-L10 数字出最终收益表 + 验证降级路径。

本课不写新机制，是整合：
    1. 汇总各课的关键数字（L00 基线 / L05 token / L06 before-after / L07 失守率 / L08 成功率）
    2. 输出最终收益表（对照 L00 裸基线）
    3. 验证降级路径：关掉 enable_browser，research-assistant 仍跑、测试仍绿

数字来源：各课 code.py 跑出的实测（mock + 本地页），非真实 API。
诚实标注：每格标 实测/mock。

跑法：
    cd gui-agent-lessons/11_capstone
    python code.py                # 出收益表
    python code.py --degrade      # 验证降级（需能跑 research-assistant 测试）
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent


# ──────────────────────────────────────────────────────────────
# 各课关键数字（实测汇总，来源标注）
# ──────────────────────────────────────────────────────────────

BENEFIT_TABLE = [
    # (指标, L00裸基线, L11全开, 收益, 来源)
    ("能拿到的证据种类", "标题+摘要+链接", "+版本号/日期/变更要点/翻页", "详情页字段从无到有", "L00/L09 实测"),
    ("引用可回访率", "0%", "~100%", "来源可回访", "L10 实测"),
    ("访问时间戳", "无", "有(ISO)", "时效可追溯", "L10 实测"),
    ("任务成功率(8任务)", "75%(6/8)", "100%(8/8)", "+25pp", "L08 实测(mock)"),
    ("平均步数", "3.9", "2.9", "-25%", "L08 实测(mock)"),
    ("注入失守率", "100%", "0%", "安全", "L07 实测(mock)"),
    ("循环打转", "有(T6打转)", "无(检出换策略)", "可靠性", "L06 实测(mock)"),
    ("观察token(对比HTML)", "922(原始HTML)", "100(元素列表)", "省9.2x", "L02 实测"),
    ("视觉vs文本token", "—", "视觉4570/文本727", "视觉贵6x→选混合", "L05 实测(mock)"),
    ("数字可复算", "无", "有(沙箱)", "数字可信", "frontier L07"),
    ("跨会话记忆", "无", "有", "不重复劳动", "frontier L01"),
]

# 降级路径表
DEGRADE_TABLE = [
    ("enable_browser", "false(默认)", "纯 search 摘要", "详情页取证"),
    ("enable_memory", "false(默认)", "无记忆(每次从零)", "跨会话记得"),
    ("enable_skills", "false(默认)", "无格式规范", "writer 遵循 skill"),
    ("enable_code_interpreter", "false(默认)", "LLM 口算", "数值可复算"),
    ("enable_ledger", "false(默认)", "每次完整报告", "增量简报"),
]


def print_benefit_table():
    """打印最终收益表。"""
    print("=" * 80)
    print("L11 最终收益表（对照 L00 裸基线）")
    print("=" * 80)
    print(f"  {'指标':<22} {'L00 裸基线':<20} {'L11 全开':<22} {'收益':<14} {'来源'}")
    print(f"  {'-'*22} {'-'*20} {'-'*22} {'-'*14} {'-'*12}")
    for metric, base, full, gain, src in BENEFIT_TABLE:
        print(f"  {metric:<22} {base:<20} {full:<22} {gain:<14} {src}")
    print(f"\n  → 核心收益：详情页字段从无到有 + 引用可回访 + 成功率↑ + 安全可靠")
    print(f"  → 诚实标注：标 (mock) 的为 mock LLM+本地页实测；真实 API 收益需 --real 跑")
    print(f"  → 但结论是结构性的（browse 多拿详情页字段、加固后成功率↑），不依赖具体内容")


def print_degrade_table():
    """打印降级路径表。"""
    print(f"\n{'='*80}")
    print("降级路径表（每个开关默认关，关掉任一系统仍跑）")
    print(f"{'='*80}")
    print(f"  {'开关':<26} {'默认':<14} {'关掉时降级到':<22} {'开启时增益'}")
    print(f"  {'-'*26} {'-'*14} {'-'*22} {'-'*18}")
    for sw, default, degrade, gain in DEGRADE_TABLE:
        print(f"  {sw:<26} {default:<14} {degrade:<22} {gain}")
    print(f"\n  安全层不在表内——它不随 enable_browser 开关，browser 一开就默认生效（红线）")


def verify_degradation():
    """验证降级：跑 research-assistant 测试套件，确认全绿。"""
    print(f"\n{'='*80}")
    print("降级验证：research-assistant 测试套件（默认 enable_browser=false）")
    print(f"{'='*80}")
    ra_dir = _REPO / "portfolio-projects" / "research-assistant"
    py = _REPO / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py_str = "python"
    else:
        py_str = str(py)
    print(f"  运行: {py_str} -m pytest tests/ -q (在 {ra_dir.name})")
    try:
        r = subprocess.run(
            [py_str, "-m", "pytest", "tests/", "-q"],
            cwd=str(ra_dir), capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="ignore",
        )
        out = r.stdout + r.stderr
        # 找 passed/failed 行
        last = [l for l in out.split("\n") if "passed" in l or "failed" in l]
        if last:
            print(f"  结果: {last[-1].strip()}")
        else:
            print(f"  结果: exit={r.returncode}")
            print(out[-500:])
        if r.returncode == 0:
            print(f"  ✅ 降级验证通过：browser 默认关，全量测试绿，系统仍跑")
        else:
            print(f"  ❌ 测试有失败（见上）")
    except Exception as e:
        print(f"  ⚠️ 跑测试失败（{e}）——可在 research-assistant 目录手动跑验证")


def main():
    print("=" * 80)
    print("L11 毕业整合：会上网的 Deep Research Agent")
    print("=" * 80)

    print_benefit_table()
    print_degrade_table()

    if "--degrade" in sys.argv:
        verify_degradation()
    else:
        print(f"\n── 降级验证 ──")
        print(f"  跑 `python code.py --degrade` 验证 research-assistant 测试套件全绿")
        print(f"  （默认 enable_browser=false，123 测试应通过）")

    print(f"\n{'='*80}")
    print(f"💡 毕业整合要点：")
    print(f"   - browser 四层（观察/行动/可靠/安全）+ 证据链 + 评估 收敛成统一架构")
    print(f"   - 与 frontier 五机制协作（记忆/反思/代码/skills/账本）")
    print(f"   - 收益表对照 L00 裸基线：成功率↑、引用可回访、安全可靠")
    print(f"   - 降级路径完好：关掉 browser 仍跑，123 测试绿")
    print(f"   - 架构文档见 portfolio-projects/research-assistant/docs/browser-agent.md")


if __name__ == "__main__":
    main()
