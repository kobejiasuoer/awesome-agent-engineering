"""Skills 加载器：能力的渐进式加载（Frontier L03）。

2025-2026 年兴起的 Agent Skills 范式（Anthropic 提出）：
    能力 = 一个文件夹（SKILL.md 说明 + 脚本 + 资源）。
    Agent 先只看到每个 skill 的一行描述（不占窗口），
    用到时才加载全文注入 prompt——渐进式披露（progressive disclosure）。

与上下文工程母题的关系：
    记忆 = 经验的按需调回（L01-L02）
    skills = 能力的按需调回（本课）
    RAG = 知识的按需调回（rag-lessons）
    MCP = 工具的远程调用（ops-lessons）
    四者同属「上下文窗口里该放什么、何时放、怎么淘汰」这一个母题。

设计：
    - 扫描 skills/ 目录，每个子文件夹是一个 skill
    - 每个 skill 的 SKILL.md 顶部 frontmatter 有 name + description（一行）
    - list_skills() 只返回 name+description（进 system prompt，极省 token）
    - load_skill(name) 返回完整内容（用到时才加载全文）
    - match_skills(query) 简单关键词匹配，决定加载哪些（可替换为 LLM 判断）

降级：无 skills 目录或 enable_skills=false 时返回空，不影响现有功能。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import settings
from .logging_config import get_logger

log = get_logger("skills")


@dataclass
class SkillMeta:
    """Skill 的元信息（轻量，进 system prompt 用）。"""
    name: str
    description: str  # 一行描述
    path: Path        # skill 文件夹路径


class SkillLoader:
    """Skills 加载器：扫描目录 + 渐进式加载。

    核心机制——渐进式披露：
        1. 启动时扫描 skills/ 目录，只读每个 SKILL.md 的 frontmatter（name+description）
        2. 把所有 skill 的一行描述拼进 system prompt（几十 token，不管有多少 skill）
        3. Agent 判断"需要 skill X"时，调 load_skill(X) 加载全文注入（可能几千 token）
        4. 不用的 skill 永远不进上下文

    对比全塞 system prompt：10 个 skill 各 1000 token = 10000 token 爆炸；
    渐进式：10 个 skill 的描述 = 200 token，只加载用到的 1-2 个 = 2000 token。
    """

    def __init__(self, skills_dir: str | Path | None = None):
        self._skills_dir = Path(skills_dir) if skills_dir else self._default_dir()
        self._cache: dict[str, str] = {}  # name → 全文（加载后缓存）
        self._metas: list[SkillMeta] = []
        self._scan()

    def _default_dir(self) -> Path:
        """默认 skills 目录：research-assistant/skills/"""
        here = Path(__file__).resolve().parent  # src/research_assistant/
        return here.parent.parent / "skills"  # research-assistant/skills/

    def _scan(self):
        """扫描 skills 目录，读取每个 skill 的元信息。"""
        if not self._skills_dir.exists():
            log.info(f"skills 目录不存在：{self._skills_dir}（enable_skills=false 时正常）")
            return

        for skill_dir in sorted(self._skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            meta = self._parse_frontmatter(skill_md, skill_dir)
            if meta:
                self._metas.append(meta)

        log.info(f"skills 扫描完成：{len(self._metas)} 个 skill @ {self._skills_dir}")

    def _parse_frontmatter(self, skill_md: Path, skill_dir: Path) -> SkillMeta | None:
        """解析 SKILL.md 的 YAML frontmatter（name + description）。"""
        try:
            text = skill_md.read_text(encoding="utf-8")
        except Exception as e:
            log.warning(f"读取 {skill_md} 失败：{e}")
            return None

        # 简单解析 frontmatter（不引入 pyyaml 依赖，手写够用）
        if not text.startswith("---"):
            # 无 frontmatter，用第一行非空行做描述
            first_line = next((l.strip() for l in text.split("\n") if l.strip()), "")
            return SkillMeta(
                name=skill_dir.name,
                description=first_line[:100],
                path=skill_dir,
            )

        # 提取 --- 之间的内容
        parts = text.split("---", 2)
        if len(parts) < 3:
            return None
        frontmatter = parts[1]

        name = skill_dir.name
        description = ""
        for line in frontmatter.split("\n"):
            line = line.strip()
            if line.startswith("name:"):
                name = line[5:].strip().strip('"').strip("'")
            elif line.startswith("description:"):
                description = line[12:].strip().strip('"').strip("'")

        return SkillMeta(name=name, description=description, path=skill_dir)

    def list_skills(self) -> list[SkillMeta]:
        """返回所有 skill 的元信息（轻量，进 system prompt 用）。"""
        return list(self._metas)

    def format_skill_descriptions(self) -> str:
        """把所有 skill 的一行描述格式化成 system prompt 片段。

        这是渐进式披露的第一层：Agent 只看到描述，不看全文。
        """
        if not self._metas:
            return ""
        lines = ["【可用技能 Skills】需要时在输出中注明「使用技能：<名称>」："]
        for m in self._metas:
            lines.append(f"  - {m.name}: {m.description}")
        return "\n".join(lines)

    def load_skill(self, name: str) -> str:
        """加载某个 skill 的全文（渐进式披露的第二层：用到才加载）。

        缓存：首次加载后缓存，避免重复 IO。
        """
        if name in self._cache:
            return self._cache[name]

        meta = next((m for m in self._metas if m.name == name), None)
        if meta is None:
            log.warning(f"skill '{name}' 不存在")
            return ""

        skill_md = meta.path / "SKILL.md"
        try:
            text = skill_md.read_text(encoding="utf-8")
            self._cache[name] = text
            log.info(f"加载 skill 全文：{name}（{len(text)} 字符）")
            return text
        except Exception as e:
            log.warning(f"加载 skill {name} 失败：{e}")
            return ""

    # 中文停用词片段：这些 2 字片段太常见，匹配它们会误命中大量 skill
    _STOP_SEGS = {"研究", "生成", "流程", "规范", "结构", "层级", "方式",
                  "多个", "呈现", "差异", "规定", "标题", "标注"}

    def match_skills(self, query: str) -> list[str]:
        """根据 query 匹配需要加载的 skill（简单关键词匹配）。

        生产可换成 LLM 判断（"这个任务需要哪些 skill"）。
        本课用关键词匹配：query 含 skill name 或 description 关键词 → 命中。

        中文处理：2-4 字片段匹配，但排除停用词（如"研究""流程"等泛化词）。
        """
        matched = []
        query_lower = query.lower()
        for m in self._metas:
            # name 出现在 query 里 → 命中
            if m.name.lower() in query_lower:
                matched.append(m.name)
                continue
            # description 的片段出现在 query 里 → 命中
            desc = m.description.lower()
            segments = set()
            for length in (2, 3, 4):
                for i in range(len(desc) - length + 1):
                    seg = desc[i:i + length]
                    if seg.strip() and seg not in self._STOP_SEGS:
                        segments.add(seg)
            # 英文：按空格分词
            for w in desc.split():
                if len(w) > 2:
                    segments.add(w.lower())
            if any(seg in query_lower for seg in segments):
                matched.append(m.name)
        return matched

    def load_matched_skills(self, query: str) -> str:
        """一步到位：匹配 + 加载全文，返回拼好的 skill 内容。

        writer 节点用这个：传入研究主题/摘要 → 返回匹配 skill 的全文。
        """
        matched = self.match_skills(query)
        if not matched:
            return ""
        parts = []
        for name in matched:
            content = self.load_skill(name)
            if content:
                parts.append(f"── 技能 {name} ──\n{content}")
        return "\n\n".join(parts)


# ── 全局单例 ──────────────────────────────────────────────
_skill_loader: SkillLoader | None = None


def get_skill_loader() -> SkillLoader | None:
    """获取全局 SkillLoader 单例。

    enable_skills=false 时返回 None（完全不介入，现有测试不受影响）。
    """
    global _skill_loader
    if not settings.enable_skills:
        return None
    if _skill_loader is None:
        _skill_loader = SkillLoader()
    return _skill_loader
