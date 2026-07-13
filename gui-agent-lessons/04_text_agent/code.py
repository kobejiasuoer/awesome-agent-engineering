"""L04 · 最小 GUI Agent：文本路线跑通 observe→think→act 循环。

把 L02 观察 + L03 动作装进循环：
    while not done and step < max_steps:
        obs = page_to_obs(session)           # 观察（L02）
        prompt = build_prompt(task, history, obs)  # 含滑动窗口裁剪
        action_text = llm(prompt)            # 思考（LLM 或 mock）
        result = parse→validate→execute      # 行动（L03）
        history.append(...)                  # 记录（滑动窗口用）

两条 LLM 路径：
    - MockLLM：预录动作序列，零 API 可跑（CI/离线）
    - 真实 LLM：ChatZhipuAI(glm-4)，--real + API key

复用 L01 BrowserSession / L02 page_to_obs / L03 动作三件套（importlib 按路径加载）。

跑法：
    cd gui-agent-lessons/00_overview/test_pages && python -m http.server 8765
    cd gui-agent-lessons/04_text_agent
    python code.py            # mock 路径
    python code.py --real     # 真实 glm-4（需 ZHIPUAI_API_KEY）
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve().parent
_LESSONS = _HERE.parent


def _load(name: str, rel: str):
    """按路径加载同仓库其他课的 code.py，避免同名模块冲突。

    必须注册进 sys.modules：否则被加载模块里的 @dataclass 会因
    cls.__module__ 查不到模块而报 NoneType 错（dataclass 已知坑）。
    """
    spec = importlib.util.spec_from_file_location(name, _LESSONS / rel / "code.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # 注册，让 dataclass 等能按 __module__ 查到
    spec.loader.exec_module(mod)
    return mod


# L01 BrowserSession / L02 page_to_obs / L03 动作三件套
_l01 = _load("l01_code", "01_playwright")
_l02 = _load("l02_code", "02_observation")
# L03 的 code.py 顶部会 import playwright？不会，单测部分纯解析。但执行器引用 INTERACTIVE_SELECTOR（本地副本）
_l03 = _load("l03_code", "03_action")
BrowserSession = _l01.BrowserSession
page_to_obs = _l02.page_to_obs
parse_action = _l03.parse_action
validate_action = _l03.validate_action
execute_action = _l03.execute_action

L00_BASE = "http://127.0.0.1:8765"

# ──────────────────────────────────────────────────────────────
# 历史记录 + 滑动窗口
# ──────────────────────────────────────────────────────────────

@dataclass
class Step:
    """一步的记录。full_obs 用于滑动窗口：最近 N 步保留全量，更早的压缩为摘要。"""
    step: int
    action_text: str           # LLM 输出的原始动作文本
    action: object             # 解析后的 Action
    result: str                # 执行结果摘要
    full_obs: str = ""         # 当步的完整观察（元素列表+摘要）


def build_prompt(task: str, history: list[Step], current_obs: str,
                 recent_n: int = 3) -> str:
    """构造 prompt，含滑动窗口裁剪。

    - 任务 + 可用动作表：始终全量（头部）
    - 历史：最近 recent_n 步保留完整动作+结果；更早的只留动作摘要
    - 当前观察：全量（最近一步）
    """
    lines = [f"【任务】{task}", "",
             "【可用动作】",
             "  click(n)      点击编号 n 的元素",
             "  type(n, text) 在编号 n 输入 text",
             "  scroll(dir)   滚动（up/down）",
             "  back()        后退",
             "  finish(答案)  完成任务，提交答案", ""]

    # 历史：滑动窗口
    if history:
        lines.append("【动作历史】")
        n = len(history)
        for i, s in enumerate(history):
            # 最近 recent_n 步：留动作+结果；更早：只留动作摘要
            is_recent = (n - 1 - i) < recent_n
            if is_recent:
                lines.append(f"  步{s.step}: {s.action_text.strip()} → {s.result}")
            else:
                lines.append(f"  步{s.step}: {s.action_text.strip()}（早期，观察已压缩）")
        lines.append("")

    lines.append("【当前观察】")
    lines.append(current_obs)
    lines.append("")
    lines.append("【你的动作】（输出一个动作，如 click(3) 或 finish(答案)）")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# MockLLM：预录动作序列，零 API
# ──────────────────────────────────────────────────────────────

class MockLLM:
    """预录动作序列的假 LLM。

    按步数返回对应的 DSL。模拟「一个会做翻页取证任务的 LLM」。
    保证零 API、CI 可跑、动作序列确定性可复现。
    """

    # 针对「对比 LangGraph release 版本号和日期」本地任务的预录序列
    # 元素编号对应 page_to_obs 在各页的实际输出（见 exercise/单测可复现）
    SCRIPT = [
        'type(1, "LangGraph")',      # 步1: index 页元素1=搜索框，输入
        'click(2)',                  # 步2: index 页元素2=搜索按钮，提交
        'click(7)',                  # 步3: search 页元素7=页码"2"链接，翻第2页
        'click(3)',                  # 步4: 第2页元素3=第1条结果(LangGraph-v0.8.0)，进详情
        'finish(版本 v0.8.0，发布于 2024-08-15，变更：断点续跑+死锁修复+序列化优化)',
    ]

    def __init__(self, script: list[str] | None = None):
        self.script = script or self.SCRIPT
        self._i = 0

    def __call__(self, prompt: str) -> str:
        """返回下一步动作文本。超出脚本返回 finish（兜底）。"""
        if self._i < len(self.script):
            a = self.script[self._i]
            self._i += 1
            return a
        return "finish(未找到完整答案)"


# ──────────────────────────────────────────────────────────────
# 真实 LLM（可选）
# ──────────────────────────────────────────────────────────────

def make_real_llm():
    """构造真实 glm-4 LLM。失败返回 None。"""
    try:
        from langchain_community.chat_models import ChatZhipuAI
        import os
        key = os.getenv("ZHIPUAI_API_KEY", "")
        if not key:
            return None
        return ChatZhipuAI(model="glm-4", temperature=0.1, zhipuai_api_key=key)
    except Exception as e:
        print(f"⚠️ 真实 LLM 初始化失败：{e}")
        return None


class RealLLM:
    """封装真实 LLM 为可调用对象（接口与 MockLLM 一致）。"""

    def __init__(self, llm):
        self._llm = llm

    def __call__(self, prompt: str) -> str:
        try:
            resp = self._llm.invoke(prompt)
            return resp.content.strip()
        except Exception as e:
            return f"finish(LLM 调用失败：{e})"


# ──────────────────────────────────────────────────────────────
# Agent 循环
# ──────────────────────────────────────────────────────────────

def run_agent(task: str, session, llm, max_steps: int = 12,
              start_url: str = f"{L00_BASE}/index.html") -> dict:
    """跑 GUI agent 循环。

    Returns: {"done": bool, "steps": int, "answer": str, "history": [Step]}
    """
    history: list[Step] = []
    session.goto(start_url)
    # 等 DOM 就绪（用 domcontentloaded，不用 wait_for_selector("body")——
    # 弹窗页的遮罩盖住 body 会让 body 可见性判定失败而超时）
    try:
        session.page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass
    answer = ""

    for step in range(1, max_steps + 1):
        # ── observe ──
        obs = page_to_obs(session, include_html=False)
        current_obs = obs["element_list"]
        elements = obs["elements"]

        # ── think（构造 prompt + 调 LLM）──
        prompt = build_prompt(task, history, current_obs)
        action_text = llm(prompt)

        # ── act（parse → validate → execute）──
        action = parse_action(action_text)
        v = validate_action(action, elements)
        if not v["ok"]:
            # 非法动作：结构化错误回注（这里记录，下一轮 LLM 会看到历史里的失败）
            s = Step(step=step, action_text=action_text.strip(), action=action,
                     result=f"非法：{v['error']}", full_obs=current_obs)
            history.append(s)
            print(f"  [步{step}] {action_text.strip()}  ❌ {v['error']}")
            continue

        r = execute_action(v["action"], session, elements)
        s = Step(step=step, action_text=action_text.strip(), action=v["action"],
                 result=r["result"], full_obs=current_obs)
        history.append(s)
        print(f"  [步{step}] {action_text.strip()}  → {r['result']}")

        if r["done"]:
            answer = r["result"]
            print(f"\n  ✅ 任务完成（{step} 步）")
            print(f"  答案: {answer}")
            return {"done": True, "steps": step, "answer": answer, "history": history}

        # 动作后等页面稳定（导航/渲染）
        try:
            session.page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass

    print(f"\n  ⚠️ 达步数上限 {max_steps}，未完成")
    return {"done": False, "steps": max_steps, "answer": answer, "history": history}


# ──────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────

def _server_up() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(L00_BASE + "/index.html", timeout=1).read()
        return True
    except Exception:
        return False


def main():
    print("=" * 60)
    print("L04 最小 GUI Agent：文本路线 observe→think→act 循环")
    print("=" * 60)

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("\n⚠️ playwright 未安装，跳过。")
        return
    if not _server_up():
        print(f"\n⚠️ L00 本地服务未起（{L00_BASE}），请先跑:")
        print(f"   cd gui-agent-lessons/00_overview/test_pages && python -m http.server 8765")
        return

    use_real = "--real" in sys.argv
    task = "对比 LangGraph 最近 release 的版本号和发布日期（翻页进详情页提取）"

    # 选 LLM
    if use_real:
        llm = make_real_llm()
        if llm is None:
            print("⚠️ 真实 LLM 不可用（缺 ZHIPUAI_API_KEY 或 langchain），回退 mock。")
            llm = MockLLM()
        else:
            llm = RealLLM(llm)
            print("🤖 使用真实 glm-4")
    else:
        llm = MockLLM()
        print("🤖 使用 MockLLM（预录动作序列，零 API）")

    print(f"\n任务: {task}")
    print(f"循环开始（max_steps=12, 滑动窗口 recent_n=3）\n")

    with BrowserSession(headless=True) as s:
        result = run_agent(task, s, llm)

    # ── 滑动窗口效果展示 ──
    print(f"\n── 滑动窗口裁剪效果（步5 的 prompt 历史段，recent_n=3）──")
    # 步5 的 prompt 历史含步1-4：recent_n=3 → 步1 被压缩，步2-4 全量
    if len(result["history"]) >= 4:
        h = result["history"][:4]           # 步1-4 的历史
        obs5 = result["history"][3].full_obs  # 用步4的观察当当前观察（演示用）
        prompt = build_prompt(task, h, obs5)
        hist_section = [l for l in prompt.split("\n") if l.strip().startswith("步")]
        for line in hist_section:
            print(f"  {line}")
        print(f"  → 步1 标注「早期，观察已压缩」，步2-4 全量 = 滑动窗口生效")

    print(f"\n💡 循环跑通。L05 加视觉路线对照，L06 加可靠性层，L08 用 mini-benchmark 量化。")


if __name__ == "__main__":
    main()
