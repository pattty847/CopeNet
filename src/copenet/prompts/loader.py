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


# Where the persona's voice is spliced into the base contract. The base prompt
# places this deliberately — after the role framing and the precedence rules, but
# before the working sections — so tone is established without being able to argue
# with the contract. Appending persona at the end instead (the old behavior) put
# voice in the strongest position in the prompt, which is backwards.
PERSONA_PLACEHOLDER = "{{persona}}"

BASE_PROMPT_ID = "default"

# Bridge until `profiles/` is dissolved into domains + personas. A profile id today
# carries domain intent ("debug", "refactor") mixed with voice ("friendly",
# "teacher"), so the coding-shaped ones select domains/coding.md. Profiles listed
# as None are explicitly non-coding and inherit only the base contract; anything
# unlisted falls back to _DEFAULT_DOMAIN, since CopeNet's default surface is a code
# workspace. Delete this map once the session carries a real domain field.
_DEFAULT_DOMAIN = "coding"
_PROFILE_DOMAINS: dict[str, str | None] = {
    "direct": None,
    "friendly": None,
    "teacher": None,
}


def get_base_text(base_id: str = BASE_PROMPT_ID) -> str | None:
    """Return the universal agent contract."""
    return get_prompt_text("base", base_id)


def get_domain_text(domain_id: str | None) -> str | None:
    """Return the domain layer text, if any."""
    if not domain_id:
        return None
    return get_prompt_text("domains", domain_id)


def domain_for_profile(profile_id: str | None) -> str | None:
    """Resolve which domain layer a profile implies."""
    normalized = (profile_id or "").strip().lower()
    if normalized in _PROFILE_DOMAINS:
        return _PROFILE_DOMAINS[normalized]
    return _DEFAULT_DOMAIN


def apply_persona(prompt: str | None, persona_text: str | None) -> str | None:
    """Splice persona voice into the base contract's slot.

    Falls back to appending when the prompt has no slot — a request-supplied
    `system_prompt` override or a legacy composition should still receive persona
    rather than silently dropping it.
    """
    if not prompt:
        return "\n\n".join(part for part in (prompt, persona_text) if part) or None
    if PERSONA_PLACEHOLDER not in prompt:
        return "\n\n".join(part for part in (prompt, persona_text) if part)
    return prompt.replace(PERSONA_PLACEHOLDER, (persona_text or "").strip())


def compose_prompt(
    profile_id: str | None,
    task_mode_id: str | None,
    *,
    domain_id: str | None = None,
) -> str | None:
    """Compose the layered system prompt.

    Order is least to most specific, matching the precedence the base contract
    declares: universal contract, then voice, then domain, then the access
    overlay. `{{persona}}` is left in place here — the harness substitutes it once
    the persona service has resolved, since persona depends on provider/model.
    """
    base_text = get_base_text()
    profile_text = get_profile_text(profile_id or "")
    resolved_domain = domain_id if domain_id is not None else domain_for_profile(profile_id)
    domain_text = get_domain_text(resolved_domain)
    normalized_task_mode = (task_mode_id or "").strip().lower()
    task_text = None if not normalized_task_mode or normalized_task_mode == "none" else get_task_mode_text(task_mode_id or "")
    parts = [part for part in (base_text, profile_text, domain_text, task_text) if part]
    if not parts:
        return None
    return "\n\n".join(parts)
