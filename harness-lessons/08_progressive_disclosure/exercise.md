# Lesson 08 · 练习

## 练习 1（设计实验）：技能库规模的临界点

三层架构的优势随技能库变大而放大，但索引层本身也在长。做规模实验：

```python
import tempfile
from pathlib import Path
from research_assistant.skill_loader import SkillLoader, build_layered_system, monolithic_system

CORE = "你是研究员。"
for n in (4, 20, 50, 200):
    d = Path(tempfile.mkdtemp()) / "skills"
    for i in range(n):
        s = d / f"skill-{i:03d}"
        s.mkdir(parents=True)
        (s / "SKILL.md").write_text(
            f"---\nname: skill-{i:03d}\ndescription: 场景{i}的处理规程要点\n---\n\n"
            + "规程正文。" * 200, encoding="utf-8")
    ld = SkillLoader(d)
    text, bd = build_layered_system(CORE, query="场景7的任务", loader=ld)
    _, mono = monolithic_system(CORE, ld)
    print(f"{n:>3} 技能 | 索引 {bd['index_tokens']:>5} | 三层 {len(text)//4:>6} | 单体 {mono:>7}")
```

1. 200 技能时索引层多大？它自己会不会成为新的膨胀源？给出「索引也要分层」的方案（提示：按类目二级索引——先给类目一行，命中类目再展开技能行；Claude Code 的 plugin 命名空间就是这个思路）。
2. 匹配质量随规模怎么变（「场景7」会不会误命中「场景70/71…」）？由此论证：规模大到什么程度，机械匹配必须让位给 LLM 判断（或向量检索）？
3. 把这条曲线和 L03 的记忆索引对照：记忆几十条、技能可能几百个——同一机制在两种规模下的实现选型该差在哪？

## 练习 2（实现）：漏加载的监控哨

漏加载是静默失败（任务照常跑，只是没按规程跑）。设计监控哨：

1. 实现 `audit_skill_usage(query, output_text, loader)`：任务结束后反查——输出里出现了某 skill 正文特有的标记（如深研究规程要求的 `[S07]` 编号引用），但该 skill 当初**没被加载** → 说明模型「碰巧做对」；反之加载了却一个标记都没出现 → 说明「加载了没遵循」。两种都告警。
2. 「加载了没遵循」还能怎么解释（提示：任务确实用不上/正文写得没有可操作性）？告警该分几级？
3. 把这个哨挂进哪里最合适：writer 之后、reviewer 里、还是 run_summary（课程九资产）？说明选择理由。

## 练习 3（设计）：skill 的写作规范

给团队定《SKILL.md 写作规范》。基于本课与反例，写出五条硬性条款，至少覆盖：

1. description 必须含具体触发词（正例/反例各举一个——「输出规范」为什么是反例）；
2. 正文开头必须有「触发条件」节（让 LLM 判断加载时有据可依）；
3. 正文体积上限（结合你的窗口预算给出数字，并说明超了怎么办——拆技能还是引用外部文件）；
4. 可操作性要求（规程要能被 audit——练习 2 的标记从哪来）；
5. 与记忆文件的分工（什么内容该进 skill、什么该进 memory_files——「人写的配置」vs「agent 学到的事实」边界举例）。

## 练习 4（思考）：三层架构与 KV 缓存的合谋

L02 练习 4 说压缩改写前缀会毁缓存。三层架构恰好相反——它是**缓存友好**的：

1. 分析三层的稳定性排序：常驻核心（永不变）> 索引层（技能库变更才变）> 按需层（随任务变）。把最稳的放最前面，对 prompt cache 命中率意味着什么？
2. 由此给出 system 组装的排序铁律，并检查 `build_layered_system` 的拼接顺序是否已经遵守。
3. 综合整门课：哪些机制是缓存友好的（追加型：工作区指针、结论累积），哪些是缓存敌对的（改写型：压缩、计划合并）？给一条「先友好后敌对」的调度原则——什么时候值得为省窗口而牺牲缓存？
