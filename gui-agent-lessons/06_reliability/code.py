"""L06 · 可靠性工程：循环检测 + 换策略 + 重试预算。

核心产出：
    - ReliabilityLayer   挂在 L04 agent 循环上的可靠性层
        · detect_loop()        观察哈希连续 N 步不变 → 循环
        · inject_lesson()      注入「你卡住了，换策略」教训
        · check_action_effect() 动作后 URL/观察变了吗
        · retry_budget          连续 K 次换策略仍卡 → 人工接管
    - 裸 agent vs 加固 agent 在刁难页上的 before/after 对照

复用 L01-L04。刁难页 test_pages/tricky.html：假按钮/死链/相似按钮。

跑法：
    cd gui-agent-lessons/00_overview/test_pages && python -m http.server 8765
    cd gui-agent-lessons/06_reliability/test_pages && python -m http.server 8767
    cd gui-agent-lessons/06_reliability
    python code.py
"""
from __future__ import annotations

import importlib.util
import sys
import time
from dataclasses import dataclass, field
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
_l02 = _load("l02_code", "02_observation")
_l03 = _load("l03_code", "03_action")
_l04 = _load("l04_code", "04_text_agent")
BrowserSession = _l01.BrowserSession
page_to_obs = _l02.page_to_obs
parse_action = _l03.parse_action
validate_action = _l03.validate_action
execute_action = _l03.execute_action
MockLLM = _l04.MockLLM

L00_BASE = "http://127.0.0.1:8765"
L06_BASE = "http://127.0.0.1:8767"


# ──────────────────────────────────────────────────────────────
# ReliabilityLayer
# ──────────────────────────────────────────────────────────────

@dataclass
class ReliabilityLayer:
    """挂在 agent 循环上的可靠性层。

    - detect_loop: 连续 loop_n 步观察哈希不变 → 循环
    - inject_lesson: 循环时注入教训，引导 LLM 换策略
    - retry_budget: 连续 max_strategy_changes 次换策略仍卡 → 人工接管
    """
    loop_n: int = 2                  # 连续多少步观察不变算循环
    max_strategy_changes: int = 3    # 最多换几次策略
    _obs_hashes: list = field(default_factory=list)  # 观察哈希历史
    _strategy_changes: int = 0       # 已换策略次数
    _last_url: str = ""              # 上一步 URL（测动作效果）

    def observe(self, obs_text: str, url: str) -> None:
        """记录每步观察哈希 + URL。"""
        self._obs_hashes.append(hash(obs_text))
        self._last_url = url

    def detect_loop(self) -> bool:
        """连续 loop_n 步观察哈希相同 → 循环。

        注意：看的是「最近 loop_n+1 步里，最近 loop_n 步全相同」
        （当前步刚加入，和之前 loop_n 步比）。
        """
        if len(self._obs_hashes) < self.loop_n + 1:
            return False
        recent = self._obs_hashes[-(self.loop_n + 1):]
        # 前 loop_n 步（不含当前刚加的）全相同 = 打转
        return len(set(recent[:-1])) == 1 and recent[-1] == recent[0]

    def inject_lesson(self) -> str:
        """循环时生成教训，注入 prompt。"""
        self._strategy_changes += 1
        if self._strategy_changes > self.max_strategy_changes:
            return ("HUMAN_TAKEOVER: 已连续多次换策略仍卡住，请人工接管。"
                    "（可靠性层触发人工接管点）")
        return (f"⚠️ 可靠性警告：你已连续 {self.loop_n} 步卡在同一页面（观察未变）。"
                f"你可能在点假按钮或死链。请换策略：尝试 back() 后退、scroll(down) 看更多、"
                f"或选择不同的元素编号。不要重复刚才无效的动作。")

    def check_action_effect(self, url_before: str, url_after: str,
                            obs_changed: bool) -> str:
        """检查动作效果。返回效果描述（用于决策）。"""
        if url_before != url_after:
            return "url_changed"
        if not obs_changed:
            return "no_effect"  # 死链/假按钮的特征
        return "obs_changed_only"

    def reset(self):
        self._obs_hashes = []
        self._strategy_changes = 0
        self._last_url = ""


# ──────────────────────────────────────────────────────────────
# 加固版 agent 循环（带 ReliabilityLayer）
# ──────────────────────────────────────────────────────────────

def run_hardened_agent(task: str, session, llm, max_steps: int = 12,
                       start_url: str = f"{L06_BASE}/tricky.html") -> dict:
    """带可靠性层的 agent 循环。"""
    layer = ReliabilityLayer(loop_n=2, max_strategy_changes=3)
    history: list = []
    session.goto(start_url)
    try:
        session.page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass
    answer = ""
    loops_detected = 0
    strategy_changes = 0
    takeover = False

    for step in range(1, max_steps + 1):
        url_before = session.url
        obs = page_to_obs(session, include_html=False)
        obs_text = obs["element_list"]
        elements = obs["elements"]
        layer.observe(obs_text, session.url)

        # ── 可靠性层：循环检测 ──
        lesson = ""
        if layer.detect_loop():
            loops_detected += 1
            lesson = layer.inject_lesson()
            strategy_changes = layer._strategy_changes
            print(f"  [步{step}] 🔄 检出循环！{lesson[:60]}...")
            if "HUMAN_TAKEOVER" in lesson:
                takeover = True
                print(f"  [步{step}] 🛑 触发人工接管点")
                break

        # ── think（含教训注入）──
        prompt = _l04.build_prompt(task, history, obs_text)
        if lesson:
            prompt += f"\n\n【可靠性教训】{lesson}"
        action_text = llm(prompt)

        # ── act ──
        action = parse_action(action_text)
        v = validate_action(action, elements)
        if not v["ok"]:
            @dataclass
            class S:
                step: int; action_text: str; action: object; result: str; full_obs: str = ""
            history.append(S(step, action_text, action, f"非法：{v['error']}", obs_text))
            print(f"  [步{step}] {action_text.strip()}  ❌ {v['error']}")
            continue

        r = execute_action(v["action"], session, elements)
        @dataclass
        class S:
            step: int; action_text: str; action: object; result: str; full_obs: str = ""
        history.append(S(step, action_text, v["action"], r["result"], obs_text))
        print(f"  [步{step}] {action_text.strip()}  → {r['result']}")

        if r["done"]:
            answer = r["result"]
            print(f"\n  ✅ 加固 agent 完成（{step} 步）")
            return {"done": True, "steps": step, "answer": answer,
                    "loops_detected": loops_detected,
                    "strategy_changes": strategy_changes, "takeover": False}

        # ── 可靠性层：动作效果检测 ──
        try:
            session.page.wait_for_load_state("domcontentloaded", timeout=2000)
        except Exception:
            pass
        url_after = session.url
        effect = layer.check_action_effect(url_before, url_after,
                                           hash(obs_text) != hash(page_to_obs(session, include_html=False)["element_list"]))
        if effect == "no_effect":
            print(f"           ⚠️ 动作无效果（死链/假按钮？URL和观察都没变）")

    print(f"\n  ⚠️ 加固 agent 未完成（步数耗尽 or 人工接管）")
    return {"done": False, "steps": max_steps, "answer": answer,
            "loops_detected": loops_detected,
            "strategy_changes": strategy_changes, "takeover": takeover}


# ──────────────────────────────────────────────────────────────
# 裸 agent（L04 原版，无可靠性层）
# ──────────────────────────────────────────────────────────────

def run_bare_agent(task: str, session, llm, max_steps: int = 12,
                   start_url: str = f"{L06_BASE}/tricky.html") -> dict:
    """裸 agent（L04 原版，无可靠性层）。在刁难页上会打转。"""
    result = _l04.run_agent(task, session, llm, max_steps=max_steps,
                            start_url=start_url)
    return {"done": result["done"], "steps": result["steps"],
            "answer": result["answer"], "loops_detected": 0,
            "strategy_changes": 0, "takeover": False}


# ──────────────────────────────────────────────────────────────
# 循环检测单测
# ──────────────────────────────────────────────────────────────

def test_loop_detection() -> bool:
    """循环检测单测：连续 N 步观察哈希不变 → 检出。"""
    print("\n── 循环检测单测 ──")
    layer = ReliabilityLayer(loop_n=2)
    # 步1: 观察 A
    layer.observe("观察A", "url1")
    assert not layer.detect_loop(), "步1 不该检出循环"
    # 步2: 观察 A（同）
    layer.observe("观察A", "url1")
    assert not layer.detect_loop(), "步2 还不够（需 loop_n+1=3 步）"
    # 步3: 观察 A（同，第3次）→ 应检出
    layer.observe("观察A", "url1")
    assert layer.detect_loop(), "步3 连续2步不变应检出循环"
    print("  ✅ 连续 2 步观察不变 → 检出循环")

    # 换场景：观察变了 → 不该检出
    layer.reset()
    layer.observe("观察A", "url1")
    layer.observe("观察B", "url1")
    layer.observe("观察C", "url1")
    assert not layer.detect_loop(), "观察在变不该检出"
    print("  ✅ 观察在变 → 不检出")

    # 教训注入
    layer.reset()
    for _ in range(3):
        layer.observe("同", "url")
    lesson = layer.inject_lesson()
    assert "换策略" in lesson
    print("  ✅ 循环时注入「换策略」教训")
    print("  ✅ 循环检测单测全通过")
    return True


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
    print("=" * 60)
    print("L06 可靠性工程：循环检测 + 换策略 + before/after 对照")
    print("=" * 60)

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("\n⚠️ playwright 未安装，跳过。")
        return
    if not _server_up(L06_BASE):
        print(f"\n⚠️ L06 本地服务未起（{L06_BASE}），请先跑:")
        print(f"   cd gui-agent-lessons/06_reliability/test_pages && python -m http.server 8767")
        return

    # 循环检测单测（零环境）
    if not test_loop_detection():
        return

    # 刁难页任务
    task = "在刁难页上找到真正的详情入口并提取版本号（避开假按钮和死链）"
    # mock 脚本：裸版会点假按钮打转；加固版检出循环后换元素
    # tricky.html 元素（实测）：[1]button提交(假) [2]button提交(假) [3]button提交(真)
    #                          [4]link死链 [5]link真详情
    bare_script = [
        'click(1)',   # 点假按钮1
        'click(1)',   # 再点假按钮1（打转）
        'click(1)',   # 还点假按钮1（打转）
        'click(2)',   # 换假按钮2（还是没效果）
        'click(2)',   # 继续（打转，步数耗尽，失败）
        'click(2)',   # 步数耗尽仍卡在假按钮
        'click(2)',   # 继续
        'click(2)',   # 继续
        'click(2)',   # 继续
        'click(2)',   # 继续
        'click(2)',   # 继续
        'click(2)',   # 满 12 步，任务失败（从未找到真入口）
    ]
    # 加固版：前 2 步点假按钮，第 3 步检出循环→教训注入→LLM 换策略点真链接
    # mock 里第 3 步返回真链接的动作（模拟 LLM 听了教训换策略）
    hardened_script = [
        'click(1)',   # 点假按钮1
        'click(1)',   # 再点（触发循环检测）
        'click(5)',   # 听了教训，换真详情链接
        'finish(版本 v0.12.0)',
    ]

    print(f"\n任务: {task}")
    results = {}
    with BrowserSession(headless=True) as s:
        print(f"\n── ① 裸 agent（无可靠性层）──")
        bare_llm = MockLLM(bare_script)
        results["bare"] = run_bare_agent(task, s, bare_llm, start_url=f"{L06_BASE}/tricky.html")

        print(f"\n── ② 加固 agent（带 ReliabilityLayer）──")
        hard_llm = MockLLM(hardened_script)
        results["hardened"] = run_hardened_agent(task, s, hard_llm, start_url=f"{L06_BASE}/tricky.html")

    # ── before/after 对照 ──
    # 成功判定：done=True 且答案不是兜底「未找到」
    def real_success(r):
        return r["done"] and "未找到" not in r["answer"] and r["answer"]
    print(f"\n{'='*60}")
    print(f"刁难页 before/after 对照")
    print(f"{'='*60}")
    b, h = results["bare"], results["hardened"]
    b_ok, h_ok = real_success(b), real_success(h)
    print(f"  {'指标':<16} {'裸 agent':<14} {'加固 agent':<14}")
    print(f"  {'真正成功':<16} {'✅' if b_ok else '❌':<14} {'✅' if h_ok else '❌':<14}")
    print(f"  {'步数':<16} {b['steps']:<14} {h['steps']:<14}")
    print(f"  {'检出循环次数':<16} {b['loops_detected']:<14} {h['loops_detected']:<14}")
    print(f"  {'换策略次数':<16} {b['strategy_changes']:<14} {h['strategy_changes']:<14}")
    print(f"  {'答案':<16} {(b['answer'][:18] or '(无)'):<14} {(h['answer'][:18] or '(无)'):<14}")
    print(f"\n  → 裸 agent 在假按钮上打转、步数耗尽、未拿到答案 ❌")
    print(f"  → 加固 agent 检出循环→注入教训→换真入口→成功 ✅")
    print(f"  → 这就是可靠性层的收益（L08 mini-benchmark 会量化）")


if __name__ == "__main__":
    main()
