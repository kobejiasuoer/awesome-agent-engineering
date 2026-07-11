"""L06 · CodeAct 手写：代码是最通用的工具 + 进程级沙箱。

手写最小 CodeAct loop：
    任务 → LLM 生成代码 → 沙箱检查(import白名单) → 执行(subprocess+超时) → 结果回注 → 迭代

安全四道防线：
    ① import 白名单（只放安全标准库）
    ② 超时杀进程
    ③ 输出截断
    ④ 无网络无文件库

用 Mock LLM 演示（不依赖真实 API），但沙箱是真实的 subprocess 执行。

跑法：
    cd frontier-lessons/06_codeact
    python code.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ════════════════════════════════════════════════════════════
# 沙箱安全配置
# ════════════════════════════════════════════════════════════

# import 白名单：只允许安全的纯计算标准库
# 🚫 不含：os/sys/subprocess/socket/urllib/open/ctypes/pathlib（文件/网络/系统）
ALLOWED_IMPORTS = {
    "json", "statistics", "collections", "math", "re",
    "datetime", "itertools", "functools", "string", "random",
    "decimal", "fractions", "heapq", "bisect",
}

# 执行超时（秒）
SANDBOX_TIMEOUT = 10

# 输出截断（字符）
MAX_OUTPUT = 2000


def check_imports(code: str) -> list[str]:
    """检查代码里的 import，返回不在白名单里的模块名。

    白名单策略：默认拒绝，只有明确安全的才放行。
    """
    violations = []
    for line in code.split("\n"):
        line = line.strip()
        if line.startswith("import "):
            # import os / import os.path
            mod = line.split()[1].split(".")[0].split(",")[0].strip()
            if mod not in ALLOWED_IMPORTS:
                violations.append(mod)
        elif line.startswith("from "):
            # from os import path / from os.path import join
            mod = line.split()[1].split(".")[0]
            if mod not in ALLOWED_IMPORTS:
                violations.append(mod)
    return violations


def sandbox_exec(code: str, timeout: int = SANDBOX_TIMEOUT) -> str:
    """沙箱执行 Python 代码：subprocess + 超时 + 输出截断。

    安全特性：
        - 独立子进程执行（不影响主进程）
        - 超时杀进程（防死循环）
        - 输出截断（防内存爆炸）
        - 无网络无文件（靠 import 白名单保证）
    """
    # 写入临时文件执行（比 -c 更可靠，支持多行）
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout
        if result.returncode != 0:
            output += f"\n[执行错误] {result.stderr[:500]}"
    except subprocess.TimeoutExpired:
        output = f"[超时] 代码执行超过 {timeout} 秒，已终止。"
    except Exception as e:
        output = f"[执行异常] {type(e).__name__}: {e}"
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # 输出截断
    if len(output) > MAX_OUTPUT:
        output = output[:MAX_OUTPUT] + f"\n... [输出截断，共 {len(output)} 字符]"
    return output.strip() or "[无输出]"


# ════════════════════════════════════════════════════════════
# CodeAct loop
# ════════════════════════════════════════════════════════════

class MockCodeLLM:
    """模拟 CodeAct 的 LLM：根据任务生成代码。

    真实场景用 ChatZhipuAI 生成代码；这里用预设演示机制。
    """

    def generate_code(self, task: str, history: str) -> str:
        """根据任务生成 Python 代码。"""
        if "分组统计" in task or "柱状图" in task:
            return (
                "from collections import Counter\n"
                "data = [\n"
                "    '2024-MCP发布', '2024-SDK发布', '2023-草案',\n"
                "    '2024-工具扩展', '2023-讨论', '2024-Java支持',\n"
                "    '2025-生态扩展', '2024-Python支持', '2025-v2草案',\n"
                "    '2024-社区增长',\n"
                "]\n"
                "years = [d.split('-')[0] for d in data]\n"
                "stats = Counter(years)\n"
                "print('年份分布统计：')\n"
                "for y, c in sorted(stats.items()):\n"
                "    print(f'  {y}: {\"█\"*c} ({c})')\n"
                "print(f'总计: {len(data)} 条')\n"
            )
        if "越权" in task:
            return "import os\nprint(os.listdir('.'))\n"
        if "网络" in task:
            return "import socket\nprint(socket.gethostname())\n"
        if "死循环" in task:
            return "while True:\n    pass\n"
        if "排序去重" in task:
            return (
                "data = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5]\n"
                "unique_sorted = sorted(set(data))\n"
                "print(f'原始: {data}')\n"
                "print(f'去重排序: {unique_sorted}')\n"
                "print(f'均值: {sum(data)/len(data):.2f}')\n"
            )
        return "print('hello from codeact')\n"

    def is_done(self, result: str, task: str) -> bool:
        """判断任务是否完成（简化：有非错误输出即完成）。"""
        return bool(result) and not result.startswith("[超时]") and not result.startswith("[执行错误]")


def codeact_loop(task: str, llm: MockCodeLLM, max_rounds: int = 3) -> str:
    """最小 CodeAct 循环：生成代码 → 检查 → 执行 → 回注 → 迭代。"""
    history = ""
    for round_idx in range(1, max_rounds + 1):
        # 1. LLM 生成代码
        code = llm.generate_code(task, history)

        # 2. import 白名单检查
        violations = check_imports(code)
        if violations:
            history += f"[轮{round_idx}] 代码被拒：import {violations} 不在白名单\n"
            print(f"  🚫 import {violations} 被拒（不在白名单）")
            continue

        # 3. 沙箱执行
        print(f"  📝 生成代码（{len(code)} 字符），沙箱执行中...")
        result = sandbox_exec(code)

        # 4. 结果回注
        history += f"[轮{round_idx}] 代码:\n{code}\n结果:\n{result}\n"
        print(f"  📤 执行结果：")
        for line in result.split("\n"):
            print(f"     {line}")

        # 5. 判断完成
        if llm.is_done(result, task):
            return result

    return history


# ════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("L06 CodeAct 手写：代码是最通用的工具")
    print("=" * 60)

    llm = MockCodeLLM()

    # ── 安全测试：白名单拦截 ────────────────────────────────
    print("\n── 安全测试：import 白名单拦截 ──────────────────")
    print(f"  白名单：{sorted(ALLOWED_IMPORTS)}")

    test_codes = [
        ("import os", "os（系统操作）"),
        ("import socket", "socket（网络）"),
        ("from os.path import join", "os.path（文件路径）"),
        ("import subprocess", "subprocess（子进程）"),
        ("from collections import Counter", "collections（安全）"),
        ("import json", "json（安全）"),
    ]
    for code, desc in test_codes:
        violations = check_imports(code)
        status = "🚫 拒绝" if violations else "✅ 允许"
        print(f"  {status} {code:<35} {desc}")

    # ── 安全测试：超时杀进程 ────────────────────────────────
    print("\n── 安全测试：超时杀进程 ──────────────────────────")
    print("  代码：while True: pass（死循环）")
    result = sandbox_exec("while True:\n    pass\n", timeout=3)
    print(f"  结果：{result}")

    # ── CodeAct loop：分组统计任务 ──────────────────────────
    print("\n── CodeAct 任务：分组统计 + ASCII 柱状图 ────────")
    print("  这个任务用预定义工具做不动（需要循环+分组+统计）")
    print("  用代码一次搞定：\n")
    codeact_loop("对搜索结果按年份分组统计并画柱状图", llm)

    # ── 对比：工具调用 vs CodeAct ───────────────────────────
    print("\n── 对比：工具调用 vs CodeAct ────────────────────")
    print("  任务：对 20 条数据按年份分组统计")
    print("  工具调用：calculate(数据) → 🚫 只能算一个表达式，不能分组循环")
    print("  CodeAct：  Counter + 循环 → ✅ 一次搞定（组合+循环免费获得）")

    # ── 安全测试：越权 import 在 loop 中被拒 ─────────────────
    print("\n── CodeAct loop：越权 import 被拒 ────────────────")
    codeact_loop("越权测试", llm, max_rounds=1)

    # ── 另一个任务：排序去重 ────────────────────────────────
    print("\n── CodeAct 任务：排序去重 + 统计 ─────────────────")
    codeact_loop("排序去重", llm, max_rounds=1)

    print("\n" + "=" * 60)
    print("✅ CodeAct = 代码是行动空间，组合/循环免费获得")
    print("🛡️ 沙箱四防线：import白名单 + 超时 + 截断 + 无网络文件")
    print("⚠️  进程级沙箱教学够用，生产需容器隔离")
    print("=" * 60)


if __name__ == "__main__":
    main()
