"""5 日模拟时间线：Ambient 课程的贯穿硬任务信源（课程十 L00 定死）。

设计（任务书 1.7「盯梢任务」）：
    让 research-assistant 持续追踪一个主题（默认「Agent 框架生态动态」），
    信源是脚本化的 5 日时间线——内容按「模拟日」切换，全离线、确定性、可复现：

    Day 1  建仓：4 条基础条目，首次全量研究
    Day 2  无实质变化：条目与 Day1 相同，仅顺序打乱 + 空白符微调
           （规范化哈希后与 Day1 一致——期望：识别「没有新东西」）
    Day 3  小更新：新增 1 条次要条目（框架 Y 补丁版本）
    Day 4  重大进展 + 矛盾：新增 1 条重磅 + item-c 内容反转（撤回 AGUI 支持），
           与 Day1 的结论直接矛盾（期望：立即通知 + ✏️ 修正标注）
    Day 5  信源故障：fetch 抛 SourceUnavailableError
           （期望：诚实降级——区分「没有变化」和「没能看到」）

为什么用脚本化信源而不是真实搜索：
    - 课程硬约束：测试与演示零联网、零真实等待、确定性可复现
    - 「常驻 Agent 该怎么应对世界变化」是结构性问题，与信源真假无关
    - 真实信源适配器（ddgs 搜索）在 L02 作为可选路径提供并标注需联网

诚实标注：条目内容为教学虚构（结构对齐真实技术资讯），日期/事件请勿当真。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# 让本模块无论从仓库根/项目根/课程目录跑都能 import research_assistant
_PROJ = Path(__file__).resolve().parent.parent
if str(_PROJ / "src") not in sys.path:
    sys.path.insert(0, str(_PROJ / "src"))

from research_assistant.clock import Clock, day_index  # noqa: E402

# 盯梢主题（可配置，默认值全课程共用）
TOPIC = "Agent 框架生态动态"

TIMELINE_DAYS = 5


class SourceUnavailableError(Exception):
    """信源打不开（Day5 注入）。

    关键设计：这是**异常**而不是「错误字符串」——调用方必须显式处理，
    不能像现状 web_search 兜底那样把失败文本混进材料。
    「没能看到」必须与「没有变化」可区分（本课灵魂案例）。
    """


@dataclass(frozen=True)
class SourceItem:
    """信源的一个条目（不可变：新的一天构造新对象，不原地改）。"""
    item_id: str
    title: str
    content: str


# ── 基础条目（Day1 建仓的世界状态）─────────────────────────────
_ITEM_A = SourceItem(
    "item-a", "LangGraph 发布 1.2 稳定版",
    "LangGraph 1.2 稳定版发布，durable execution 与 interrupt/resume 进入稳定 API，"
    "官方建议生产部署使用 checkpointer 持久化。",
)
_ITEM_B = SourceItem(
    "item-b", "MCP 官方 registry 上线",
    "MCP 生态推出官方 server registry，收录逾千个社区 server，"
    "工具发现从口口相传进入目录检索时代。",
)
_ITEM_C_V1 = SourceItem(
    "item-c", "框架 X 宣布支持 AGUI 协议",
    "多智能体框架 X 宣布全面支持 AGUI 协议，并计划在下个大版本默认启用，"
    "称其为「Agent 与前端交互的标准答案」。",
)
_ITEM_D = SourceItem(
    "item-d", "Agent 评测基准 TrajBench 发布 v1",
    "TrajBench v1 发布：以轨迹级指标（步数效率/循环率/工具正确率）评测 Agent，"
    "补足只看最终答案的传统基准。",
)

# Day2：内容与 Day1 相同，仅顺序打乱 + 空白微调（规范化后哈希一致）
_ITEM_A_WS = SourceItem(_ITEM_A.item_id, _ITEM_A.title, _ITEM_A.content + "  ")
_ITEM_C_WS = SourceItem(_ITEM_C_V1.item_id, _ITEM_C_V1.title,
                        _ITEM_C_V1.content.replace("，并计划", "， 并计划"))

# Day3：新增次要条目（minor——值得记，不值得打扰）
_ITEM_E = SourceItem(
    "item-e", "框架 Y 发布 0.3.2 补丁",
    "框架 Y 发布 0.3.2 补丁版本，修复长会话内存泄漏与 Windows 路径兼容问题，"
    "无新特性。",
)

# Day4：重磅新增 + item-c 反转（与 Day1 结论矛盾）
_ITEM_F = SourceItem(
    "item-f", "重磅：框架 X 撤回 AGUI 支持转投 A2A",
    "框架 X 官方宣布撤回对 AGUI 协议的支持计划，全面转投 A2A 互操作路线，"
    "称「生态位重叠，二选一」。此前公布的默认启用计划取消。",
)
_ITEM_C_V2 = SourceItem(
    "item-c", "框架 X 宣布支持 AGUI 协议",
    "【更正】框架 X 此前的 AGUI 支持计划已中止，官方文档已移除相关章节，"
    "详见其 A2A 迁移公告。",
)

# 5 日剧本：day -> 条目列表（Day5 为 None = 信源故障）
_SCRIPT: dict[int, list[SourceItem] | None] = {
    1: [_ITEM_A, _ITEM_B, _ITEM_C_V1, _ITEM_D],
    2: [_ITEM_C_WS, _ITEM_A_WS, _ITEM_D, _ITEM_B],          # 打乱顺序 + 空白微调
    3: [_ITEM_C_WS, _ITEM_A_WS, _ITEM_D, _ITEM_B, _ITEM_E],  # +minor
    4: [_ITEM_A_WS, _ITEM_B, _ITEM_C_V2, _ITEM_D, _ITEM_E, _ITEM_F],  # +major+矛盾
    5: None,                                                  # 信源故障
}

# 每日「期望行为」注记（评估与 README 引用；基线做不到这些正是 L00 的结论）
DAY_EXPECTATIONS = {
    1: "建仓：全量研究，产出基线报告",
    2: "无实质变化：识别「没有新东西」，不研究、不打扰，浪费≈0",
    3: "小更新：只对 item-e 增量研究，进 digest，不立即打扰",
    4: "重大+矛盾：立即通知，简报带 ✏️ 修正标注（item-c 反转）",
    5: "信源故障：诚实报告「没能看到」，绝不冒充「没有变化」",
}


class AmbientTimeline:
    """脚本化 5 日信源。

    两种驱动方式：
        - 显式：fetch_items(day=N)（单测/逐日演示用）
        - 时钟：构造时传 clock + start_ts，fetch_items() 自动按 clock 推算「今天」
          （daemon/调度器集成用——快进时钟即翻日）
    """

    def __init__(self, clock: Clock | None = None, start_ts: float | None = None):
        self._clock = clock
        self._start_ts = start_ts if start_ts is not None else (
            clock.now() if clock is not None else 0.0
        )
        self.fetch_count = 0  # 诊断：被扫了几次

    def current_day(self) -> int:
        """按注入时钟推算当前模拟日（1..TIMELINE_DAYS，超出封顶）。"""
        if self._clock is None:
            return 1
        d = day_index(self._clock.now(), self._start_ts)
        return min(max(d, 1), TIMELINE_DAYS)

    def fetch_items(self, day: int | None = None) -> list[SourceItem]:
        """取某模拟日的信源条目。Day5 抛 SourceUnavailableError（结构化故障）。"""
        d = day if day is not None else self.current_day()
        d = min(max(d, 1), TIMELINE_DAYS)
        self.fetch_count += 1
        script = _SCRIPT[d]
        if script is None:
            raise SourceUnavailableError(f"信源不可用（HTTP 503，模拟日 Day{d}）")
        return list(script)  # 拷贝：不把内部剧本暴露给调用方改

    def as_search_text(self, query: str, day: int | None = None) -> str:
        """把当日条目格式化成「搜索结果」文本——mock 现状 web_search 的返回形态。

        Day5 会抛 SourceUnavailableError；复刻现状行为的调用方（L00 基线）
        自行 catch 并返回失败字符串——那正是要暴露的缺口。
        """
        items = self.fetch_items(day)
        lines = [f"[{it.title}] {it.content}" for it in items]
        return f"关于「{query}」的检索结果：\n" + "\n".join(lines)
