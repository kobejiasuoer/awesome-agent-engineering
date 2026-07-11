"""代码解释器测试（Frontier L07）。

测试沙箱安全 + 执行正确性，不依赖真实 LLM。
"""
from __future__ import annotations

import pytest

from research_assistant.code_interpreter import (
    check_imports,
    execute_code,
    should_use_code,
    run_code_for_research,
    format_code_appendix,
    reset_executed_codes,
    get_executed_codes,
    CodeResult,
    ALLOWED_IMPORTS,
)


# ── import 白名单 ─────────────────────────────────────────────
def test_check_imports_allows_safe():
    """安全 import 应通过。"""
    assert check_imports("import json") == []
    assert check_imports("from collections import Counter") == []
    assert check_imports("import statistics\nimport math") == []


def test_check_imports_blocks_dangerous():
    """危险 import 应被拦截。"""
    assert "os" in check_imports("import os")
    assert "socket" in check_imports("import socket")
    assert "subprocess" in check_imports("import subprocess")
    assert "os" in check_imports("from os.path import join")


def test_check_imports_blocks_dotted():
    """from os.path import join 应检测到 os。"""
    violations = check_imports("from os.path import join\nimport json")
    assert "os" in violations
    assert "json" not in violations


# ── 沙箱执行 ──────────────────────────────────────────────────
def test_execute_simple_code():
    """简单代码应正常执行。"""
    result = execute_code("print('hello world')")
    assert result.success
    assert "hello world" in result.output


def test_execute_statistics():
    """统计代码应正确执行。"""
    code = "import statistics\nprint(statistics.mean([1,2,3,4,5]))"
    result = execute_code(code)
    assert result.success
    assert "3" in result.output


def test_execute_blocks_dangerous_import():
    """越权 import 应被拒绝，不执行。"""
    result = execute_code("import os\nprint(os.listdir('.'))")
    assert not result.success
    assert "os" in result.error
    assert result.output == ""


def test_execute_timeout():
    """死循环应超时被杀。"""
    result = execute_code("while True:\n    pass", timeout=3)
    assert not result.success
    assert "超时" in result.error


def test_execute_error_handling():
    """代码错误应返回失败 + 错误信息。"""
    result = execute_code("print(undefined_var)")
    assert not result.success
    assert result.error  # 有错误信息


def test_execute_output_truncation():
    """超长输出应被截断。"""
    code = "for i in range(10000):\n    print('x' * 100)"
    result = execute_code(code)
    assert result.success
    assert len(result.output) <= 3000  # MAX_OUTPUT + 截断提示


# ── 路由判断 ──────────────────────────────────────────────────
def test_should_use_code_true():
    """含计算/统计信号的任务应走代码。"""
    assert should_use_code("对比 X 和 Y 的发布节奏")
    assert should_use_code("统计各年份的数量分布")
    assert should_use_code("计算占比")


def test_should_use_code_false():
    """不含计算信号的任务不应走代码。"""
    assert not should_use_code("概述 MCP 生态")
    assert not should_use_code("介绍协议设计")


# ── 代码历史 + 附录 ───────────────────────────────────────────
def test_run_code_records_history():
    """run_code_for_research 应记录执行历史。"""
    reset_executed_codes()
    run_code_for_research("print('test')")
    codes = get_executed_codes()
    assert len(codes) == 1
    assert codes[0].success


def test_format_appendix_empty():
    """无执行记录时附录为空。"""
    reset_executed_codes()
    assert format_code_appendix() == ""


def test_format_appendix_has_content():
    """有执行记录时附录含代码。"""
    reset_executed_codes()
    run_code_for_research("print('result: 42')")
    appendix = format_code_appendix()
    assert "附录" in appendix
    assert "print('result: 42')" in appendix
    assert "result: 42" in appendix


def test_reset_clears_history():
    """reset 应清空历史。"""
    run_code_for_research("print('test')")
    reset_executed_codes()
    assert get_executed_codes() == []
