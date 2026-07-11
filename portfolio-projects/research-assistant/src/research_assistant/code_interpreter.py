"""代码解释器：研究助手的 CodeAct 工具（Frontier L07）。

复用 L06 的进程级沙箱（subprocess + 超时 + import 白名单 + 输出截断），
给 research-assistant 加一个 code interpreter 工具：
    - researcher/writer 可按需调用，让"需要对比数据时能写代码算"
    - 执行过的代码附在报告附录（可复算性——研究报告的可信度升级）

设计取舍（L06 的流派对比延续）：
    - 什么走代码：数值对比、去重统计、表格生成（组合/循环需求）
    - 什么走 LLM 直出：观点综述、语言组织（不需要精确计算）
    - 路由判断：简化版用关键词（"对比""统计""计算"→ 走代码）
    - 生产可换 LLM 判断（"这个任务需要写代码吗"）

安全：白名单比 L06 更窄（研究场景只需 json/statistics/collections/re）。
降级：enable_code_interpreter=false 或执行失败时，回退到 LLM 直出（不阻塞）。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import settings
from .logging_config import get_logger

log = get_logger("code_interpreter")

# ── 沙箱安全配置（比 L06 更窄：研究场景只需计算库）─────────
ALLOWED_IMPORTS = {
    "json", "statistics", "collections", "math", "re",
    "datetime", "itertools", "functools", "string",
}

SANDBOX_TIMEOUT = 10
MAX_OUTPUT = 2000


@dataclass
class CodeResult:
    """代码执行结果。"""
    success: bool
    output: str
    code: str        # 执行的代码（附报告附录用）
    error: str = ""  # 错误信息（失败时）


def check_imports(code: str) -> list[str]:
    """检查 import 是否在白名单内。返回违规模块列表。"""
    violations = []
    for line in code.split("\n"):
        line = line.strip()
        if line.startswith("import "):
            mod = line.split()[1].split(".")[0].split(",")[0].strip()
            if mod not in ALLOWED_IMPORTS:
                violations.append(mod)
        elif line.startswith("from "):
            mod = line.split()[1].split(".")[0]
            if mod not in ALLOWED_IMPORTS:
                violations.append(mod)
    return violations


def execute_code(code: str, timeout: int = None) -> CodeResult:
    """沙箱执行 Python 代码，返回 CodeResult。

    安全四防线：import 白名单 + 超时 + 输出截断 + 无网络文件库。
    """
    timeout = timeout or SANDBOX_TIMEOUT

    # ① import 白名单检查
    violations = check_imports(code)
    if violations:
        msg = f"import {violations} 不在白名单{sorted(ALLOWED_IMPORTS)}内"
        log.warning(f"代码被拒：{msg}")
        return CodeResult(success=False, output="", code=code, error=msg)

    # ② 写临时文件执行
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        output = result.stdout
        if result.returncode != 0:
            output += f"\n[执行错误] {result.stderr[:500]}"
            return CodeResult(success=False, output=output, code=code,
                              error=result.stderr[:200])
    except subprocess.TimeoutExpired:
        return CodeResult(success=False, output="", code=code,
                          error=f"超时（{timeout}s）")
    except Exception as e:
        return CodeResult(success=False, output="", code=code,
                          error=f"{type(e).__name__}: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # ③ 输出截断
    if len(output) > MAX_OUTPUT:
        output = output[:MAX_OUTPUT] + f"\n... [截断，共 {len(output)} 字符]"

    log.info(f"代码执行成功：{len(output)} 字符输出")
    return CodeResult(success=True, output=output.strip(), code=code)


# ── 路由判断：什么任务该走代码 ──────────────────────────────
_CODE_SIGNALS = ["对比", "统计", "计算", "分组", "排序", "数量", "占比", "分布"]


def should_use_code(task_or_summary: str) -> bool:
    """判断任务是否应该走代码执行（而非 LLM 直出）。

    简化版：关键词匹配。生产可换 LLM 判断。
    """
    return any(sig in task_or_summary for sig in _CODE_SIGNALS)


# ── 全局代码执行历史（附报告附录用）─────────────────────────
_executed_codes: list[CodeResult] = []


def get_executed_codes() -> list[CodeResult]:
    """获取本次运行执行过的代码（writer 附报告附录用）。"""
    return list(_executed_codes)


def reset_executed_codes():
    """重置代码执行历史（每次新研究前调）。"""
    _executed_codes.clear()


def run_code_for_research(code: str) -> CodeResult:
    """研究场景的代码执行入口：执行 + 记录历史。

    researcher/writer 调这个：执行代码 + 存入历史（后续附报告附录）。
    """
    result = execute_code(code)
    _executed_codes.append(result)
    return result


def format_code_appendix() -> str:
    """把执行过的代码格式化成报告附录。

    可复算性：报告里的数字"由代码计算"，附脚本让读者可验证。
    """
    codes = get_executed_codes()
    if not codes:
        return ""
    lines = ["\n\n## 附录：代码执行记录（可复算）"]
    for i, cr in enumerate(codes, 1):
        lines.append(f"\n### 脚本 {i}")
        lines.append(f"```python\n{cr.code}\n```")
        if cr.success:
            lines.append(f"**输出**：\n```\n{cr.output[:300]}\n```")
        else:
            lines.append(f"**执行失败**：{cr.error}")
    return "\n".join(lines)
