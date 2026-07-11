"""Skills 加载器测试（Frontier L03）。

测试原则：用临时 skills 目录，不依赖真实 skills/ 目录。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from research_assistant.skill_loader import SkillLoader, SkillMeta


@pytest.fixture
def skills_dir(tmp_path):
    """创建临时 skills 目录，含 2 个示例 skill。"""
    d = tmp_path / "skills"

    # skill 1: 研究简报格式
    s1 = d / "research-brief-format"
    s1.mkdir(parents=True)
    (s1 / "SKILL.md").write_text(
        "---\nname: research-brief-format\n"
        "description: 研究简报格式规范\n---\n# 研究简报格式\n要求结构化...",
        encoding="utf-8",
    )

    # skill 2: 对比表
    s2 = d / "comparison-table"
    s2.mkdir(parents=True)
    (s2 / "SKILL.md").write_text(
        "---\nname: comparison-table\n"
        "description: 对比表生成流程\n---\n# 对比表\n当涉及对比时...",
        encoding="utf-8",
    )

    return d


@pytest.fixture
def loader(skills_dir):
    return SkillLoader(skills_dir=skills_dir)


# ── 扫描 ──────────────────────────────────────────────────────
def test_scan_finds_skills(loader):
    """扫描应找到 2 个 skill。"""
    metas = loader.list_skills()
    assert len(metas) == 2
    names = [m.name for m in metas]
    assert "research-brief-format" in names
    assert "comparison-table" in names


def test_scan_nonexistent_dir(tmp_path):
    """不存在的目录应优雅返回空（不崩）。"""
    loader = SkillLoader(skills_dir=tmp_path / "nope")
    assert loader.list_skills() == []


def test_parse_frontmatter(loader):
    """frontmatter 的 name 和 description 应正确解析。"""
    metas = {m.name: m for m in loader.list_skills()}
    assert metas["research-brief-format"].description == "研究简报格式规范"
    assert metas["comparison-table"].description == "对比表生成流程"


# ── 渐进式加载 ────────────────────────────────────────────────
def test_format_descriptions_is_lightweight(loader):
    """format_skill_descriptions 应只含一行描述（不含全文）。"""
    text = loader.format_skill_descriptions()
    assert "可用技能" in text
    assert "research-brief-format" in text
    assert "研究简报格式规范" in text
    # 不应包含全文内容
    assert "要求结构化" not in text


def test_load_skill_returns_full_content(loader):
    """load_skill 应返回完整 SKILL.md 内容。"""
    content = loader.load_skill("research-brief-format")
    assert "研究简报格式" in content
    assert "要求结构化" in content  # 全文才有


def test_load_skill_caches(loader):
    """第二次 load 同一 skill 应走缓存（不重复 IO）。"""
    c1 = loader.load_skill("comparison-table")
    c2 = loader.load_skill("comparison-table")
    assert c1 == c2
    assert "comparison-table" in loader._cache


def test_load_nonexistent_skill(loader):
    """加载不存在的 skill 应返回空串（不崩）。"""
    assert loader.load_skill("no-such-skill") == ""


# ── 匹配 ──────────────────────────────────────────────────────
def test_match_by_name_in_query(loader):
    """query 含 skill name 时应匹配。"""
    matched = loader.match_skills("请按 research-brief-format 格式写")
    assert "research-brief-format" in matched


def test_match_by_description_keyword(loader):
    """query 含 description 关键词（3字以上片段）时应匹配。"""
    # "对比表" 是 comparison-table description 里的 3 字片段
    matched = loader.match_skills("这个研究需要对比表来展示差异")
    assert "comparison-table" in matched


def test_match_no_hit(loader):
    """不相关的 query 不应匹配任何 skill。"""
    matched = loader.match_skills("今天天气怎么样")
    assert matched == []


def test_load_matched_skills_returns_text(loader):
    """load_matched_skills 应返回匹配 skill 的全文。"""
    text = loader.load_matched_skills("需要对比表")
    assert "对比表" in text
    assert len(text) > 50  # 全文不止一行


def test_load_matched_skills_empty_when_no_match(loader):
    """无匹配时返回空串。"""
    assert loader.load_matched_skills("不相关的内容") == ""


# ── 无 frontmatter 降级 ───────────────────────────────────────
def test_skill_without_frontmatter(tmp_path):
    """无 frontmatter 的 SKILL.md 应降级用第一行做描述。"""
    d = tmp_path / "skills" / "simple"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("# 简单技能\n这是正文...", encoding="utf-8")
    loader = SkillLoader(skills_dir=tmp_path / "skills")
    metas = loader.list_skills()
    assert len(metas) == 1
    assert metas[0].name == "simple"
