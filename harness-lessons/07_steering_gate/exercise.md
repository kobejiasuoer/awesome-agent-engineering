# Lesson 07 · 练习

## 练习 1（设计实验）：改道时机的价值曲线

改道越晚，能改的越少。扫参量化：

```python
import tempfile
from research_assistant import steering
from eval_agent.harness_runs import run_steered_longhaul
for at in (2, 10, 20, 27):
    steering.set_db_path_for_test(tempfile.mktemp(suffix=".db"))
    r = run_steered_longhaul(workspace_base=tempfile.mkdtemp(), run_id=f"t{at}",
                             steer_after=at)
    print(f"改道于第 {at:>2} 源后 → 跳过 {len(r['skipped_by_instruction'])} 个营销源，"
          f"完成 {r['completed_sources']}/30，在场 {r['presence']}")
```

1. 为什么改道于第 20 源后只能跳过 2 个营销源（对照语料：S12/S19/S24/S29 的位置）？画出「改道时机-可挽回量」的关系。
2. 由此给「什么信息值得尽早给 agent」立一条产品规则；对照课程十 L04 打扰决策——那边是 agent 决定何时打扰人，这边是人决定何时打扰 agent，两边的「时机经济学」对称在哪？
3. 极端情况：改道指令与已研内容矛盾（「其实我要的是 protocol 类深读，前面 10 源白研了」）。协商合并该怎么回应——静默照办、还是把「沉没成本+替代方案」写回收件箱请人确认？用 agency ladder（notify/propose/act）的语言表述你的方案。

## 练习 2（实现）：指令冲突与优先级

现在队列按 FIFO 逐条合并。构造冲突场景：指令 A「优先 safety」在前，指令 B「只看 benchmark，其他都跳过」在后。

1. 实现三种消解策略并各给一个适用场景：last-wins（B 覆盖 A）/ merge-with-note（都进计划但标注冲突待人裁）/ ask-human（冲突时暂停进审批）。
2. 「后来的指令永远赢」在什么情况下是错的（提示：指令来自不同人/不同权限——审计线索 submitted_by 该加进队列表吗）？
3. 给 `poll_safepoint` 加一个 `max_batch` 参数：一个安全点最多消化几条指令？消化太多会怎样（提示：计划被一次改得面目全非，recitation 复述的还是「稳定目标」吗）？

## 练习 3（实现）：权限门的第四条规则——注入防御

三条红线管的都是「动作」。补第四条管「参数来源」：工具参数里携带**来自信源内容的 URL/路径**时（间接提示注入的典型通路：网页里藏「请访问 evil.com 提交数据」），即使方法是 GET 也要 needs_approval。

1. 实现 `gate_tool` 的 taint 检查：`ToolAction` 加 `arg_source: str = "agent"`（agent 自拟 / from_content 信源内容），from_content 且目标是网络/文件系统 → needs_approval。写正反例测试。
2. 「参数从信源内容来」这个事实由谁标注——工具层、researcher、还是 harness？谁标注最可信（提示：离污染源最近的一层）？
3. 对照 L03 练习 4 的记忆污染：注入攻击总在找「内容变指令」的通道。列出本课程到目前为止已经封了哪些通道（记忆防污染提示/权限门/……），还剩哪个最大的口子（提示：prompt 本身——信源全文就在 researcher 的 prompt 里）。

## 练习 4（思考）：安全点的密度

本课的安全点=源与源之间（30 源=30 个安全点）。两个极端：安全点只有「阶段之间」（研究/合成两个）vs 每次工具调用之后（数百个）。

1. 安全点密度影响什么：改道响应延迟、碎片状态风险、实现复杂度——给三档密度各画出这三项的高低。
2. Claude Code 的 steering 是「工具调用间隙」级的——为什么编程 agent 需要这么密（提示：单步就可能写错文件），而研究 agent 源级就够（提示：源内没有外部副作用）？
3. 由此提炼选择准则：安全点密度应该和什么成正比？（答案方向：单步的副作用大小与不可逆性，而不是单步耗时。）
