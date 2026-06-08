"""workspace_files — read-only viewer service (list + scoped read)."""

from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.workspace_files import list_workspace_files, read_workspace_file


def _seed(tmp_path: Path) -> None:
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "01-offer.md").write_text("# Offer\n\n**Salary** $128k\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("a note", encoding="utf-8")
    (tmp_path / "secret.env").write_text("TOKEN=abc", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n")  # non-viewable
    (tmp_path / ".hidden").write_text("nope", encoding="utf-8")
    skip = tmp_path / "node_modules"
    skip.mkdir()
    (skip / "lib.js").write_text("x", encoding="utf-8")


def test_list_returns_viewable_files_only(tmp_path: Path) -> None:
    _seed(tmp_path)
    rows = list_workspace_files(tmp_path)
    paths = {r["path"] for r in rows}
    assert "inbox/01-offer.md" in paths
    assert "notes.md" in paths and "secret.env" in paths and "app.py" in paths
    assert "image.png" not in paths           # non-viewable extension skipped
    assert ".hidden" not in paths             # dotfiles skipped
    assert not any("node_modules" in p for p in paths)  # skip dirs pruned


def test_list_classifies_kind(tmp_path: Path) -> None:
    _seed(tmp_path)
    by_path = {r["path"]: r["kind"] for r in list_workspace_files(tmp_path)}
    assert by_path["inbox/01-offer.md"] == "markdown"
    assert by_path["app.py"] == "code"
    assert by_path["secret.env"] == "text"


def test_read_returns_content_and_kind(tmp_path: Path) -> None:
    _seed(tmp_path)
    doc = read_workspace_file(tmp_path, "inbox/01-offer.md")
    assert doc["kind"] == "markdown"
    assert "Salary" in doc["content"]
    assert doc["name"] == "01-offer.md"
    assert doc["truncated"] is False


def test_read_blocks_path_traversal(tmp_path: Path) -> None:
    _seed(tmp_path)
    with pytest.raises(ValueError):
        read_workspace_file(tmp_path, "../../../etc/passwd")


def test_read_missing_file_raises(tmp_path: Path) -> None:
    _seed(tmp_path)
    with pytest.raises(FileNotFoundError):
        read_workspace_file(tmp_path, "inbox/nope.md")
