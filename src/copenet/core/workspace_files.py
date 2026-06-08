"""Read-only workspace file browsing for the operator file viewer.

Powers the UI's "open a file and see it rendered" surface. Strictly scoped to a
session's workspace root — path traversal is rejected, hidden/heavy directories
are skipped, and reads are size-capped. Read-only: there is no write path here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_MARKDOWN_EXTS = {".md", ".markdown"}
_CODE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".html", ".css", ".scss",
    ".yaml", ".yml", ".toml", ".sh", ".bash", ".rs", ".go", ".rb", ".java", ".sql",
}
_TEXT_EXTS = {".txt", ".env", ".cfg", ".ini", ".log", ".csv", ""}
_VIEWABLE_EXTS = _MARKDOWN_EXTS | _CODE_EXTS | _TEXT_EXTS
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".mypy_cache", ".pytest_cache", ".idea"}
_MAX_FILES = 500
_MAX_READ_BYTES = 200_000


def _kind_for(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _MARKDOWN_EXTS:
        return "markdown"
    if ext in _CODE_EXTS:
        return "code"
    return "text"


def list_workspace_files(root: Path) -> list[dict[str, Any]]:
    """Return viewable files under `root`, relative-pathed, capped and sorted."""
    root = root.resolve()
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in _VIEWABLE_EXTS:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        rows.append({
            "path": str(path.relative_to(root)),
            "name": path.name,
            "ext": path.suffix.lower().lstrip("."),
            "kind": _kind_for(path),
            "size": size,
        })
        if len(rows) >= _MAX_FILES:
            break
    return rows


def read_workspace_file(root: Path, rel_path: str) -> dict[str, Any]:
    """Return the content of one file under `root`, scoped and size-capped."""
    root = root.resolve()
    target = (root / (rel_path or "").strip()).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes the workspace root") from exc
    if not target.is_file():
        raise FileNotFoundError(rel_path)
    raw = target.read_bytes()
    truncated = len(raw) > _MAX_READ_BYTES
    content = raw[:_MAX_READ_BYTES].decode("utf-8", errors="replace")
    return {
        "path": str(target.relative_to(root)),
        "name": target.name,
        "ext": target.suffix.lower().lstrip("."),
        "kind": _kind_for(target),
        "content": content,
        "truncated": truncated,
        "size": len(raw),
    }
