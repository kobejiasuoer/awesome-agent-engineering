"""ingest：增量缓存三路径（新增/修改/删除）与幂等。"""
from __future__ import annotations

from pathlib import Path

import pytest

from kb_qa.ingest import ingest_directory


def _write(docs_dir: Path, name: str, body: str) -> None:
    (docs_dir / name).write_text(body, encoding="utf-8")


@pytest.mark.usefixtures("isolated_store")
def test_add_new_file(isolated_store: Path):
    _write(isolated_store, "a.md", "# A\n\n## 节\n\n内容甲。\n")
    report = ingest_directory()
    assert report.added_files == ("a.md",)
    assert report.added_chunks > 0
    assert report.total_chunks == report.added_chunks


@pytest.mark.usefixtures("isolated_store")
def test_rerun_is_idempotent(isolated_store: Path):
    _write(isolated_store, "a.md", "# A\n\n## 节\n\n内容甲。\n")
    first = ingest_directory()
    second = ingest_directory()
    assert second.skipped_files == ("a.md",)
    assert second.added_chunks == 0
    assert second.total_chunks == first.total_chunks


@pytest.mark.usefixtures("isolated_store")
def test_modify_replaces_old_chunks(isolated_store: Path):
    _write(isolated_store, "a.md", "# A\n\n## 节\n\n短。\n")
    ingest_directory()
    _write(isolated_store, "a.md", "# A\n\n## 节\n\n" + "扩充很多内容。" * 60 + "\n")
    report = ingest_directory()
    assert report.updated_files == ("a.md",)
    # 库里只有新版本的块，没有旧块残留
    assert report.total_chunks == report.added_chunks


@pytest.mark.usefixtures("isolated_store")
def test_delete_prunes_orphans(isolated_store: Path):
    _write(isolated_store, "a.md", "# A\n\n## 节\n\n内容甲。\n")
    _write(isolated_store, "b.md", "# B\n\n## 节\n\n内容乙。\n")
    ingest_directory()
    (isolated_store / "b.md").unlink()
    report = ingest_directory()
    assert report.pruned_files == ("b.md",)
