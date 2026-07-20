"""L03 · 跨会话记忆文件：Agent 的操作记忆
==================================================

本脚本用三个「会话」演示操作记忆的完整生命周期（会话间只有文件存续）：
    会话 1  用户纠正「报告用中文、≤500 字」→ 剧本代演 LLM 提名两条候选
            → 写入纪律 gate：偏好收下、临时参数拒收 → 落盘 + 索引
    会话 2  新会话从零开始——writer 召回：trigger 命中读正文注入 prompt，
            偏好跨会话生效；账本量证「索引常驻、正文按需」的经济性
    会话 3  用户改主意「改成 800 字」→ 同名 upsert（不重复）；
            记错了 delete（可反悔）；无关查询零注入

诚实标注：
    - 「哪些值得记」真实系统里是 LLM 的判断（判断交给模型）；本演示用
      剧本提名候选，gate 的拒收规则才是本课交付的纪律（纪律交给代码）。
    - trigger 匹配是机械层（子串命中）；「要不要读这条记忆」同样可以
      交给模型判——机制与 L08 skill 加载同构，质量问题在那课展开。

跑法（零外部依赖、零联网、零真实等待）：
    python code.py
"""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_PROJ = _REPO / "portfolio-projects" / "research-assistant"
sys.path.insert(0, str(_PROJ))
sys.path.insert(0, str(_PROJ / "src"))

logging.disable(logging.INFO)

from research_assistant import memory_files as mf  # noqa: E402
from research_assistant.config import settings  # noqa: E402
from research_assistant.context_ledger import FakeTokenizer  # noqa: E402


def hr(title: str) -> None:
    print(f"\n{'═' * 62}\n{title}\n{'═' * 62}")


class CaptureLLM:
    def __init__(self):
        self.last_prompt = ""

    def invoke(self, prompt, **kw):
        self.last_prompt = prompt

        class _M:
            content = "（mock 报告正文）"
        return _M()


def main() -> None:
    mem_dir = Path(tempfile.mkdtemp(prefix="memfiles_demo_")) / "mem"
    settings.__dict__["memory_files_dir"] = str(mem_dir)

    # ════════════════════════════════════════════════════════
    hr("Part 0 · 三种记忆分家（谁都不取代谁）")
    print("  任务经验  memory.py（frontier）  研究结论与教训，向量召回，量大")
    print("  任务进度  task_ledger.py         TODO 树与增量简报，结构化")
    print("  操作记忆  memory_files.py（本课）「报告要 ≤500 字」——量小、")
    print("           价值密度高、人可直读直改；此前无处安放，每次会话从零开始")

    # ════════════════════════════════════════════════════════
    hr("会话 1 · 用户纠正 → 提名 → 写入纪律 gate → 落盘")
    print("用户：「以后报告必须用中文，正文控制在 500 字以内。另外这次先查 3 个来源就行。」")
    print("\n（剧本代演 LLM 提名两条候选——判断交给模型：）")
    candidates = [
        mf.MemoryCandidate(
            name="report-style", description="报告语言与长度偏好（用户纠正）",
            body="报告必须用中文撰写；正文控制在 500 字以内。",
            mtype=mf.MTYPE_PREFERENCE, scope="durable", triggers="报告,写作,格式"),
        mf.MemoryCandidate(
            name="source-count", description="本轮来源数量",
            body="先查 3 个来源。", mtype=mf.MTYPE_PREFERENCE, scope="session"),
    ]
    for c in candidates:
        path, verb = mf.write_memory(c)
        mark = f"✅ {verb} → {Path(path).name}" if path else f"🚫 {verb}"
        print(f"  候选 [{c.name}]（scope={c.scope}）：{mark}")
    print("\n落盘后的索引（MEMORY.md，常驻成本=每条一行）：")
    for line in mf.load_index().strip().splitlines():
        print(f"  {line}")

    # ════════════════════════════════════════════════════════
    hr("会话 2 · 新会话：writer 召回，偏好跨会话生效")
    # 先模拟「用了一段时间」：记忆库里已攒下若干长正文的项目状态记忆
    for i, (name, desc, trig) in enumerate([
        ("kb-ingest-pitfalls", "知识库入库的历史坑位记录", "入库,知识库"),
        ("eval-baseline-notes", "评估基线的口径与阈值决定", "评估,基线"),
        ("deploy-constraints", "部署环境的长期约束", "部署,上线"),
        ("stakeholder-glossary", "干系人术语表与叫法习惯", "术语,汇报"),
    ]):
        mf.write_memory(mf.MemoryCandidate(
            name=name, description=desc, mtype=mf.MTYPE_PROJECT, triggers=trig,
            body=f"（长正文示意）{desc}——历史决定、原因与例外情况的完整记录。" * 40))
    settings.__dict__["enable_memory_files"] = True
    from research_assistant import nodes
    llm = CaptureLLM()
    nodes.make_writer(llm)({"research_summary": "关于 Agent 运行时生态的研究报告摘要",
                            "feedback": "", "truncated": False})
    hit = "500 字" in llm.last_prompt
    print(f"writer 的 prompt 含用户偏好：{'✅' if hit else '❌'}"
          f"（trigger「报告」命中 → 正文注入）")
    guard = "以当前对话为准" in llm.last_prompt
    print(f"注入块自带防污染提示「过时以当前对话为准」：{'✅' if guard else '❌'}")

    tk = FakeTokenizer()
    idx_cost = tk.count(mf.load_index())
    body_cost = sum(tk.count(mf.read_memory(m["name"])) for m in mf.list_memories())
    print(f"\n账本量证（记忆库共 {len(mf.list_memories())} 条）：索引 {idx_cost} token 常驻，"
          f"正文合计 {body_cost:,} token 住磁盘——")
    print(f"  本次任务只命中 1 条（report-style），另外 4 条长记忆只付了「一行索引」的钱；")
    print("  记忆越攒越多，常驻成本只随「条数×一行」线性长，不随正文长。")

    print("\n对照：关掉开关重跑——")
    settings.__dict__["enable_memory_files"] = False
    llm2 = CaptureLLM()
    nodes.make_writer(llm2)({"research_summary": "关于 Agent 运行时生态的研究报告摘要",
                             "feedback": "", "truncated": False})
    print(f"  prompt 含偏好：{'❌ 有' if '500 字' in llm2.last_prompt else '✅ 无'}"
          f"（默认关=行为零差异）")

    # ════════════════════════════════════════════════════════
    hr("会话 3 · 改主意=更新；记错了=删除；未命中=零注入")
    settings.__dict__["enable_memory_files"] = True
    print("用户：「500 字太紧了，改成 800 字以内吧。」")
    _, verb = mf.write_memory(mf.MemoryCandidate(
        name="report-style", description="报告语言与长度偏好（用户纠正）",
        body="报告必须用中文撰写；正文控制在 800 字以内。",
        mtype=mf.MTYPE_PREFERENCE, triggers="报告,写作,格式"))
    print(f"  同名候选 → {verb}（文件数 {len(mf.list_memories())}，索引仍一行）")
    print(f"  正文现为：「{mf.read_memory('report-style')}」")

    llm3 = CaptureLLM()
    nodes.make_writer(llm3)({"research_summary": "关于财务数据的图表分析",
                             "feedback": "", "truncated": False})
    print(f"\n无关任务（财务图表）召回：{'零注入 ✅' if '操作记忆' not in llm3.last_prompt else '误注入 ❌'}"
          f"——按需不是常注入")

    mf.delete_memory("report-style")
    print(f"delete 后：文件数 {len(mf.list_memories())}，索引 "
          f"{'已消行 ✅' if 'report-style' not in mf.load_index() else '残留 ❌'}（记忆可反悔）")

    # ════════════════════════════════════════════════════════
    hr("两条主线的位置（L03）")
    print("窗口经济：操作记忆的常驻成本被压到「每条一行」——索引进窗口，")
    print("         正文住磁盘按需换入；这是第一次把「可能有用」和「此刻在场」分开计价。")
    print("外置化：  本课把「跨会话事实」搬出窗口（会话断了文件还在）——")
    print("         虚拟内存图上第一块真正落盘的内容；L06 把工作集也搬出去。")
    settings.__dict__["enable_memory_files"] = False


if __name__ == "__main__":
    main()
