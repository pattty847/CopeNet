"""Load bundled prompt profiles and task overlays."""

from __future__ import annotations

from pathlib import Path


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "presets"


def _category_dir(category: str) -> Path:
    return _prompts_dir() / category


def _read_name(path: Path) -> str:
    name = path.stem
    try:
        first = path.read_text(encoding="utf-8").strip().split("\n")[0].strip()
        if first.startswith("# "):
            name = first[2:].strip()
        elif first and len(first) < 80:
            name = first
    except OSError:
        pass
    return name


def _read_prompt(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _safe_id(prompt_id: str) -> str:
    return "".join(c for c in prompt_id.strip() if c.isalnum() or c in "-_.")


def _list_category(category: str) -> list[dict[str, str]]:
    root = _category_dir(category)
    if not root.is_dir():
        return []
    out: list[dict[str, str]] = []
    for path in sorted(root.glob("*.md")):
        out.append({"id": path.stem, "name": _read_name(path)})
    return out


def list_profiles() -> list[dict[str, str]]:
    """List available base behavior profiles."""
    return _list_category("profiles")


def list_task_modes() -> list[dict[str, str]]:
    """List available task overlays."""
    return _list_category("task-modes")


def list_presets() -> list[dict[str, str]]:
    """Backward-compatible flat preset listing."""
    return list_profiles()


def get_prompt_text(category: str, prompt_id: str) -> str | None:
    """Return raw text for a prompt category/id pair."""
    if not prompt_id or not prompt_id.strip():
        return None
    safe = _safe_id(prompt_id)
    if not safe:
        return None
    return _read_prompt(_category_dir(category) / f"{safe}.md")


def get_profile_text(profile_id: str) -> str | None:
    """Return the base profile text."""
    text = get_prompt_text("profiles", profile_id)
    if text is not None:
        return text
    return _read_prompt(_prompts_dir() / f"{_safe_id(profile_id)}.md")


def get_task_mode_text(task_mode_id: str) -> str | None:
    """Return the task overlay text."""
    text = get_prompt_text("task-modes", task_mode_id)
    if text is not None:
        return text
    return _read_prompt(_prompts_dir() / f"{_safe_id(task_mode_id)}.md")


def compose_prompt(profile_id: str | None, task_mode_id: str | None) -> str | None:
    """Compose a final system prompt from a base profile and optional task overlay."""
    profile_text = get_profile_text(profile_id or "")
    normalized_task_mode = (task_mode_id or "").strip().lower()
    task_text = None if not normalized_task_mode or normalized_task_mode == "none" else get_task_mode_text(task_mode_id or "")
    parts = [part for part in (profile_text, task_text) if part]
    if not parts:
        return None
    return "\n\n".join(parts)


def get_preset_text(preset_id: str) -> str | None:
    """Backward-compatible lookup for base profiles."""
    return get_profile_text(preset_id)
