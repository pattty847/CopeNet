"""Load system prompt presets from the package prompts directory."""

from __future__ import annotations

from pathlib import Path


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "presets"


def list_presets() -> list[dict[str, str]]:
    """List available preset ids and names. Name is first line of file or id."""
    root = _prompts_dir()
    if not root.is_dir():
        return []
    out: list[dict[str, str]] = []
    for path in sorted(root.glob("*.md")):
        preset_id = path.stem
        name = preset_id
        try:
            first = path.read_text(encoding="utf-8").strip().split("\n")[0].strip()
            if first.startswith("# "):
                name = first[2:].strip()
            elif first and len(first) < 80:
                name = first
        except OSError:
            pass
        out.append({"id": preset_id, "name": name})
    return out


def get_preset_text(preset_id: str) -> str | None:
    """Return raw text for a preset, or None if not found."""
    if not preset_id or not preset_id.strip():
        return None
    safe = "".join(c for c in preset_id.strip() if c.isalnum() or c in "-_.")
    if not safe:
        return None
    path = _prompts_dir() / f"{safe}.md"
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
