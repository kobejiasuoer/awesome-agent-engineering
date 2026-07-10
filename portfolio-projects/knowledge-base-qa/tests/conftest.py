"""pytest 共享 fixture：临时目录 + fake embedding，全程不打真实 API。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from langchain_core.embeddings import DeterministicFakeEmbedding  # noqa: E402

from kb_qa.config import settings  # noqa: E402


@pytest.fixture
def sample_md(tmp_path: Path) -> Path:
    """带三级标题结构的样例文档。"""
    doc = tmp_path / "docs" / "sample.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# 测试手册\n\n## 考勤\n\n### 打卡时间\n\n工作时间为 9:30-18:30。\n\n"
        "### 迟到处理\n\n迟到 30 分钟以上记旷工半日。\n\n## 假期\n\n年假 5 天起。\n",
        encoding="utf-8",
    )
    return doc


@pytest.fixture
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """把 Chroma/docs 路径指到临时目录，并用确定性 fake embedding 替换智谱。"""
    monkeypatch.setattr(settings, "chroma_path", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "docs_dir", str(tmp_path / "docs"))
    (tmp_path / "docs").mkdir(exist_ok=True)

    import kb_qa.ingest as ingest_mod

    monkeypatch.setattr(
        ingest_mod, "get_embeddings", lambda: DeterministicFakeEmbedding(size=64)
    )
    return tmp_path / "docs"
