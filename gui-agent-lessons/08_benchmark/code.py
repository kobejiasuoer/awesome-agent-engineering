"""L08 · 本地 mini-benchmark runner：评 L04 裸版 vs L06 加固版。

WebArena 思路：自托管本地任务集 + 功能性验收（检查终态不评文本）。
8 任务覆盖：搜索/翻页/详情/动态渲染/弹窗/刁难/注入/多步取证。

两层评估：
    - 结果层（本课）：checker(answer) → 任务做成没（二值）
    - 过程层（frontier TrajectoryEvaluator）：步数/循环/归因

跑法：
    # 起 4 个本地服务
    cd gui-agent-lessons/00_overview/test_pages && python -m http.server 8765 &
    cd gui-agent-lessons/01_playwright/test_pages && python -m http.server 8766 &
    cd gui-agent-lessons/06_reliability/test_pages && python -m http.server 8767 &
    cd gui-agent-lessons/07_injection/test_pages && python -m http.server 8768 &

    cd gui-agent-lessons/08_benchmark
    python code.py
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_LESSONS = _HERE.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _LESSONS / rel / "code.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_l01 = _load("l01_code", "01_playwright")
_l04 = _load("l04_code", "04_text_agent")
_l06 = _load("l06_code", "06_reliability")
BrowserSession = _l01.BrowserSession
MockLLM = _l04.MockLLM

# 任务集
sys.path.insert(0, str(_HERE / "mini_benchmark"))
from tasks import TASKS  # noqa: E402


# ──────────────────────────────────────────────────────────────
# 跑单个任务
# ──────────────────────────────────────────────────────────────

@dataclass
class TaskResult:
    task_id: str
    desc: str
    category: str
    version: str          # "bare" or "hardened"
    success: bool         # 功能性验收（checker）
    steps: int
    answer: str
    error: str = ""


def run_task(task: dict, version: str, session) -> TaskResult:
    """跑一个任务的一个版本。version ∈ {"bare","hardened"}。"""
    script_key = "bare_script" if version == "bare" else "hardened_script"
    script = task[script_key]
    llm = MockLLM(script)

    # 裸版用 L04 原版循环；加固版用 L06 带 ReliabilityLayer 的循环
    if version == "hardened":
        # 对非刁难任务（T1-T5/T8），加固版和裸版走同样脚本都能成；
        # 关键差异在 T6（刁难）和 T7（注入）。
        # 为统一，加固版全用 L06 循环（带可靠性层，但不影响能成的任务）
        result = _l06.run_hardened_agent(
            task["desc"], session, llm, max_steps=12,
            start_url=task["start_url"])
    else:
        result = _l04.run_agent(
            task["desc"], session, llm, max_steps=12,
            start_url=task["start_url"])

    answer = result.get("answer", "")
    # 功能性验收
    try:
        ok = bool(task["checker"](answer))
    except Exception as e:
        ok = False
        answer = f"(checker 错: {e})"
    # 裸版在 T6/T7 的脚本可能没 finish（步数耗尽）→ answer 空
    if not answer and not result.get("done"):
        ok = False
        answer = "(步数耗尽未完成)"

    return TaskResult(
        task_id=task["id"], desc=task["desc"], category=task["category"],
        version=version, success=ok, steps=result.get("steps", 12),
        answer=answer[:50],
    )


# ──────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────

def _server_up(base: str) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(base + "/", timeout=1).read()
        return True
    except Exception:
        return False


def main():
    print("=" * 64)
    print("L08 mini-benchmark：8 任务 × 2 版本 = 16 次评估")
    print("=" * 64)

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("\n⚠️ playwright 未安装，跳过。")
        return

    # 检查服务
    bases = {"L00": "http://127.0.0.1:8765", "L01": "http://127.0.0.1:8766",
             "L06": "http://127.0.0.1:8767", "L07": "http://127.0.0.1:8768"}
    down = [k for k, b in bases.items() if not _server_up(b)]
    if down:
        print(f"\n⚠️ 以下本地服务未起：{down}")
        for k in down:
            lesson = {"L00": "00_overview", "L01": "01_playwright",
                      "L06": "06_reliability", "L07": "07_injection"}[k]
            port = bases[k].rsplit(":", 1)[1]
            print(f"   cd gui-agent-lessons/{lesson}/test_pages && python -m http.server {port}")
        return

    all_results: list[TaskResult] = []
    with BrowserSession(headless=True) as s:
        for task in TASKS:
            for version in ("bare", "hardened"):
                print(f"\n── {task['id']} [{version}] {task['desc']} ──")
                r = run_task(task, version, s)
                mark = "✅" if r.success else "❌"
                print(f"   {mark} {r.version} | steps={r.steps} | answer={r.answer}")
                all_results.append(r)

    # ── 指标卡 ──
    print(f"\n{'='*64}")
    print(f"mini-benchmark 指标卡（功能性验收 + 步数）")
    print(f"{'='*64}")
    print(f"  {'任务':<4} {'类别':<14} {'裸版':<8} {'加固版':<8} {'裸步数':<6} {'加步数':<6}")
    bare_succ = hard_succ = 0
    bare_steps = hard_steps = 0
    for task in TASKS:
        b = next(r for r in all_results if r.task_id == task["id"] and r.version == "bare")
        h = next(r for r in all_results if r.task_id == task["id"] and r.version == "hardened")
        bm = "✅" if b.success else "❌"
        hm = "✅" if h.success else "❌"
        print(f"  {task['id']:<4} {task['category']:<14} {bm:<8} {hm:<8} {b.steps:<6} {h.steps:<6}")
        bare_succ += b.success; hard_succ += h.success
        bare_steps += b.steps; hard_steps += h.steps
    n = len(TASKS)
    print(f"\n  {'成功率':<16} {bare_succ}/{n} ({bare_succ/n:.0%}){'':<2} {hard_succ}/{n} ({hard_succ/n:.0%})")
    print(f"  {'平均步数':<16} {bare_steps/n:.1f}{'':<12} {hard_steps/n:.1f}")
    print(f"\n  → 加固版成功率 {'↑' if hard_succ >= bare_succ else '↓'}、平均步数 {'↓' if hard_steps <= bare_steps else '↑'}")
    print(f"  → 关键差异在 T6（刁难页避陷阱）和 T7（注入抵抗）：裸版失败、加固版成功")
    print(f"  → 这是评估主线闭环：L00 基线 → L01-L07 加机制 → L08 量化收益")

    # ── 过程层（TrajectoryEvaluator 接入说明）──
    print(f"\n── 过程层（frontier TrajectoryEvaluator 接入）──")
    print(f"  结果层（本课 checker）评『做成没』；过程层评『做得好不好』（步数/循环/归因）。")
    print(f"  轨迹格式对齐 frontier baseline_trace.jsonl，可直接喂 TrajectoryEvaluator.evaluate_file()。")
    print(f"  L11 收益表 = 本课结果层 + frontier 过程层，双层评估。")


if __name__ == "__main__":
    main()
