"""loader：结构感知分块与溯源 metadata。"""
from __future__ import annotations

from pathlib import Path

from kb_qa.loader import file_md5, list_documents, load_and_split


def test_split_carries_section_breadcrumb(sample_md: Path):
    chunks = load_and_split(sample_md)
    assert chunks, "至少切出一个块"
    sections = {c.metadata["section"] for c in chunks}
    # 三级标题被拼成面包屑
    assert any("测试手册 > 考勤 > 打卡时间" == s for s in sections)
    assert any("测试手册 > 假期" == s for s in sections)


def test_chunk_metadata_complete(sample_md: Path):
    for chunk in load_and_split(sample_md):
        assert chunk.metadata["source"] == "sample.md"
        assert len(chunk.metadata["src_hash"]) == 32
        assert isinstance(chunk.metadata["chunk_idx"], int)


def test_file_md5_changes_with_content(sample_md: Path):
    before = file_md5(sample_md)
    sample_md.write_text(sample_md.read_text(encoding="utf-8") + "\n新增行\n", encoding="utf-8")
    assert file_md5(sample_md) != before


def test_list_documents_filters_and_sorts(sample_md: Path):
    docs_dir = sample_md.parent
    (docs_dir / "b.txt").write_text("文本", encoding="utf-8")
    (docs_dir / "ignore.pdf").write_bytes(b"%PDF")
    names = [p.name for p in list_documents(docs_dir)]
    assert names == ["b.txt", "sample.md"]
