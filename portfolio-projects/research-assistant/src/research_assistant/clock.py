"""可注入时钟：Ambient 课程的测试地基（课程十 L00）。

为什么「时间」必须是依赖注入：
    常驻 Agent 的一切行为都由时间驱动——调度到点、间隔退避、心跳过期、
    缺勤判定。如果代码里直接写 time.time() / time.sleep()：
        - 测试「5 天的调度行为」就要真等 5 天（不可接受）
        - 演示 code.py 要真 sleep（违反课程「零真实等待」硬约束）
    把 now()/sleep() 做成可替换对象后，FakeClock 一行 advance() 就能快进——
    这与 agent-ops 课程「故障注入器」同一地位：没有它，整门课不可测试。

用法：
    生产：Clock()（真实时间）
    测试/演示：FakeClock(start)，用 advance()/advance_days() 快进，
              sleep() 不真等待而是把时钟拨快（daemon 循环因此可秒级跑完 5 天）
"""
from __future__ import annotations

import time

# 一「天」的秒数（模拟时间线/时段预算共用）
DAY_SECONDS = 86400.0


class Clock:
    """真实时钟（生产默认）。"""

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))


class FakeClock(Clock):
    """假时钟：now() 返回内部值，sleep() 不等待而是快进。

    start 默认取一个固定值（而非 time.time()）——保证测试/演示**确定性**：
    同样的脚本每次跑出同样的「日期」，档案可复现、可对照。
    """

    def __init__(self, start: float = 1_700_000_000.0):
        self._now = float(start)

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        # sleep = 快进（这是 FakeClock 的灵魂：等待变成拨表）
        self._now += max(0.0, float(seconds))

    def advance(self, seconds: float) -> None:
        """手动快进 N 秒。"""
        self._now += float(seconds)

    def advance_days(self, days: float) -> None:
        """手动快进 N 天。"""
        self._now += float(days) * DAY_SECONDS


def day_index(now_ts: float, start_ts: float) -> int:
    """从时间戳算「第几天」（1 起）。时段预算/时间线共用。"""
    if now_ts < start_ts:
        return 1
    return int((now_ts - start_ts) // DAY_SECONDS) + 1
