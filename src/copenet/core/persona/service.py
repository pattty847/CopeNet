"""File-backed Persona Home runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any, Literal

from copenet._paths import default_personas_dir
from copenet.core._json_store import (
    read_json as _read_json,
    write_json_atomic as _write_json,
    write_text_atomic as _write_text_atomic,
)

PersonaPrivacyTier = Literal["private", "safe", "off"]

# Logical section name -> (subdir, filename) for model-authored persona content.
_PERSONA_SECTION_PATHS: dict[str, tuple[str, str]] = {
    "soul": ("core", "SOUL.md"),
    "identity": ("core", "IDENTITY.md"),
    "agents": ("core", "AGENTS.md"),
    "user": ("user", "USER.md"),
    "tools": ("environment", "TOOLS.md"),
    "public_memory": ("memory", "PUBLIC.md"),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "default"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_text_if_missing(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(body.strip() + "\n", encoding="utf-8")


def _compress_user_md(text: str) -> tuple[str, list[str]]:
    """Split USER.md into its always-injected summary and on-demand section titles.

    Convention: a leading ``## Summary`` section is the compressed block injected every
    turn; every other ``## `` header is body the model reads on demand via files.read.
    Files that don't follow the convention fall back to their preamble (text before the
    first ``## ``, minus a leading ``# `` title) as the summary. Returns
    ``(summary_text, other_section_titles)``.
    """
    preamble: list[str] = []
    body_sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_body: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("## "):
            if current_title is None:
                preamble = current_body
            else:
                body_sections.append((current_title, current_body))
            current_title = line.strip()[3:].strip()
            current_body = []
        else:
            current_body.append(line)
    if current_title is None:
        preamble = current_body
    else:
        body_sections.append((current_title, current_body))

    summary = ""
    other_titles: list[str] = []
    for title, body in body_sections:
        if title.lower() == "summary" and not summary:
            summary = "\n".join(body).strip()
        else:
            other_titles.append(title)

    if not summary:
        # No explicit ## Summary — use the preamble, dropping a leading "# Title" line.
        cleaned: list[str] = []
        for line in preamble:
            if not cleaned and line.strip().startswith("# "):
                continue
            cleaned.append(line)
        summary = "\n".join(cleaned).strip()
        if not summary and body_sections:
            summary = "\n".join(body_sections[0][1]).strip()
    return summary, other_titles


def _merge_user_md_section(text: str, title: str, body: str) -> str:
    """Replace the body of the ``## {title}`` section (appending it if absent).

    Preserves the file's preamble and other sections; re-renders with consistent
    spacing. Used by the approve path so an accepted proposal updates one section
    rather than blindly appending.
    """
    preamble: list[str] = []
    titles: list[str] = []
    bodies: list[list[str]] = []
    current_title: str | None = None
    current_body: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("## "):
            if current_title is None:
                preamble = current_body
            else:
                titles.append(current_title)
                bodies.append(current_body)
            current_title = line.strip()[3:].strip()
            current_body = []
        else:
            current_body.append(line)
    if current_title is None:
        preamble = current_body
    else:
        titles.append(current_title)
        bodies.append(current_body)

    new_body = body.strip().splitlines()
    replaced = False
    for index, existing in enumerate(titles):
        if existing.lower() == title.lower():
            titles[index] = title
            bodies[index] = new_body
            replaced = True
            break
    if not replaced:
        titles.append(title)
        bodies.append(new_body)

    parts: list[str] = []
    pre = "\n".join(preamble).strip()
    if pre:
        parts.append(pre)
    for section_title, section_body in zip(titles, bodies):
        rendered_body = "\n".join(section_body).strip()
        parts.append(f"## {section_title}\n{rendered_body}".rstrip())
    return "\n\n".join(parts).strip() + "\n"


@dataclass(frozen=True)
class PersonaSettingsOverride:
    persona_id: str = "default"
    flavor_id: str | None = None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "PersonaSettingsOverride":
        return cls(
            persona_id=_safe_segment(_text(raw.get("personaId") or raw.get("persona_id") or "default")),
            flavor_id=_text(raw.get("flavorId") or raw.get("flavor_id")) or None,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "personaId": self.persona_id,
            "flavorId": self.flavor_id,
        }


@dataclass(frozen=True)
class PersonaSettings:
    default_persona_id: str = "default"
    default_privacy_tier: PersonaPrivacyTier = "private"
    model_overrides: dict[str, PersonaSettingsOverride] = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "PersonaSettings":
        tier = _text(raw.get("defaultPrivacyTier") or raw.get("default_privacy_tier") or "private")
        if tier not in {"private", "safe", "off"}:
            tier = "private"
        overrides_raw = raw.get("modelOverrides") or raw.get("model_overrides") or {}
        overrides: dict[str, PersonaSettingsOverride] = {}
        if isinstance(overrides_raw, dict):
            for key, value in overrides_raw.items():
                if isinstance(value, dict) and _text(key):
                    overrides[_text(key)] = PersonaSettingsOverride.from_json(value)
        return cls(
            default_persona_id=_safe_segment(_text(raw.get("defaultPersonaId") or raw.get("default_persona_id") or "default")),
            default_privacy_tier=tier,  # type: ignore[arg-type]
            model_overrides=overrides,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "defaultPersonaId": self.default_persona_id,
            "defaultPrivacyTier": self.default_privacy_tier,
            "modelOverrides": {key: value.to_json() for key, value in sorted(self.model_overrides.items())},
        }

    def to_public_dict(self) -> dict[str, Any]:
        return self.to_json()


@dataclass(frozen=True)
class PersonaFlavor:
    persona_id: str
    flavor_id: str
    provider: str
    model: str
    display_name: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "personaId": self.persona_id,
            "flavorId": self.flavor_id,
            "provider": self.provider,
            "model": self.model,
            "displayName": self.display_name,
        }


@dataclass(frozen=True)
class PersonaPromptContext:
    persona_id: str
    privacy_tier: PersonaPrivacyTier
    prompt: str
    flavor_id: str | None = None
    loaded_files: tuple[str, ...] = ()

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "personaId": self.persona_id,
            "personaFlavorId": self.flavor_id,
            "personaPrivacyTier": self.privacy_tier,
            "prompt": self.prompt,
            "loadedFiles": list(self.loaded_files),
        }


class PersonaHomeService:
    """Loads Persona Home files and resolves per-model flavor overlays."""

    def __init__(self, *, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir if root_dir is not None else default_personas_dir()

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    def load_settings(self) -> PersonaSettings:
        self._ensure_scaffold()
        raw = _read_json(self._settings_path(), {})
        return PersonaSettings.from_json(raw if isinstance(raw, dict) else {})

    def update_settings(
        self,
        *,
        default_persona_id: str | None = None,
        default_privacy_tier: PersonaPrivacyTier | None = None,
        model_overrides: dict[str, dict[str, Any] | PersonaSettingsOverride] | None = None,
    ) -> PersonaSettings:
        current = self.load_settings()
        tier = default_privacy_tier or current.default_privacy_tier
        if tier not in {"private", "safe", "off"}:
            tier = current.default_privacy_tier
        overrides = dict(current.model_overrides)
        if model_overrides is not None:
            overrides = {}
            for key, value in model_overrides.items():
                if isinstance(value, PersonaSettingsOverride):
                    overrides[_text(key)] = value
                elif isinstance(value, dict):
                    overrides[_text(key)] = PersonaSettingsOverride.from_json(value)
        settings = PersonaSettings(
            default_persona_id=_safe_segment(default_persona_id or current.default_persona_id),
            default_privacy_tier=tier,
            model_overrides={key: value for key, value in overrides.items() if key},
        )
        _write_json(self._settings_path(), settings.to_json())
        return settings

    def get_summary(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        privacy_tier: PersonaPrivacyTier | None = None,
    ) -> dict[str, Any]:
        context = self.build_prompt_context(
            provider=provider or "",
            model=model,
            privacy_tier=privacy_tier,
            query="",
        )
        return {
            "personaId": context.persona_id,
            "personaFlavorId": context.flavor_id,
            "personaPrivacyTier": context.privacy_tier,
            "active": bool(context.prompt),
            "rootDir": str(self._root_dir),
            "loadedFiles": list(context.loaded_files),
        }

    def build_prompt_context(
        self,
        *,
        provider: str,
        model: str | None,
        privacy_tier: PersonaPrivacyTier | None,
        query: str,
        include_agent_instructions: bool = True,
    ) -> PersonaPromptContext:
        self._ensure_scaffold()
        settings = self.load_settings()
        resolved_tier = privacy_tier or settings.default_privacy_tier
        if resolved_tier not in {"private", "safe", "off"}:
            resolved_tier = settings.default_privacy_tier
        override = settings.model_overrides.get(_model_key(provider, model))
        persona_id = override.persona_id if override else settings.default_persona_id
        flavor_id = override.flavor_id if override else self._existing_flavor_id(persona_id, provider, model)
        if resolved_tier == "off":
            return PersonaPromptContext(persona_id=persona_id, privacy_tier="off", prompt="", flavor_id=flavor_id)

        persona_root = self._persona_dir(persona_id)
        sections: list[tuple[str, str, Path]] = []
        for path in (
            persona_root / "core" / "SOUL.md",
            persona_root / "core" / "IDENTITY.md",
        ):
            if text := _read_text(path):
                sections.append((path.name, text, path))
        agents_path = persona_root / "core" / "AGENTS.md"
        if include_agent_instructions and (text := _read_text(agents_path)):
            sections.append((agents_path.name, text, agents_path))
        if flavor_id:
            for name in ("IDENTITY.md", "SOUL.md", "NOTES.md"):
                path = persona_root / "models" / flavor_id / name
                if text := _read_text(path):
                    sections.append((f"Model flavor {name}", text, path))
        if resolved_tier == "private":
            # USER.md is two-tier: only the compressed ``## Summary`` block is injected
            # every turn; the rest of the file is read on demand via files.read. The
            # synthetic index line tells the model what's available and where to find it.
            user_path = persona_root / "user" / "USER.md"
            if user_text := _read_text(user_path):
                summary, section_titles = _compress_user_md(user_text)
                if summary:
                    sections.append((user_path.name, summary, user_path))
                if section_titles:
                    index_line = (
                        "Full operator context lives in USER.md. Sections available on demand: "
                        + ", ".join(section_titles)
                        + f". Read the full file with files.read on: {user_path}"
                    )
                    sections.append(("USER.md sections", index_line, user_path))
            memory_path = persona_root / "memory" / "MEMORY.md"
            if text := _read_text(memory_path):
                sections.append((memory_path.name, text, memory_path))
            for path in self._recent_daily_paths(persona_root):
                if text := _read_text(path):
                    sections.append((f"Daily memory {path.name}", text, path))
        public_memory = persona_root / "memory" / "PUBLIC.md"
        if text := _read_text(public_memory):
            sections.append(("Public memory", text, public_memory))
        if resolved_tier == "private":
            tools_path = persona_root / "environment" / "TOOLS.md"
            if text := _read_text(tools_path):
                sections.append(("Environment notes", text, tools_path))

        prompt = "\n\n".join(f"## {title}\n{text}" for title, text, _ in sections if text)
        return PersonaPromptContext(
            persona_id=persona_id,
            privacy_tier=resolved_tier,
            prompt=prompt,
            flavor_id=flavor_id,
            loaded_files=tuple(str(path) for _, _, path in sections),
        )

    def save_flavor(self, *, provider: str, model: str | None, draft: dict[str, Any]) -> PersonaFlavor:
        settings = self.load_settings()
        persona_id = settings.default_persona_id
        safe_provider = _safe_segment(provider)
        safe_model = _safe_segment(model or "default")
        flavor_id = f"{safe_provider}/{safe_model}"
        flavor_dir = self._persona_dir(persona_id) / "models" / flavor_id
        _write_text_if_missing(flavor_dir / ".keep", "")
        identity = _text(draft.get("identityMarkdown") or draft.get("identity") or "")
        soul = _text(draft.get("soulMarkdown") or draft.get("soul") or "")
        notes = _text(draft.get("notesMarkdown") or draft.get("notes") or "")
        if not identity:
            display = _text(draft.get("displayName")) or f"{safe_provider} {safe_model}"
            identity = f"# {display}\n\nA CopeNet model flavor for {provider} / {model or 'default'}."
        (flavor_dir / "IDENTITY.md").write_text(identity.rstrip() + "\n", encoding="utf-8")
        if soul:
            (flavor_dir / "SOUL.md").write_text(soul.rstrip() + "\n", encoding="utf-8")
        if notes:
            (flavor_dir / "NOTES.md").write_text(notes.rstrip() + "\n", encoding="utf-8")
        overrides = dict(settings.model_overrides)
        overrides[_model_key(provider, model)] = PersonaSettingsOverride(persona_id=persona_id, flavor_id=flavor_id)
        self.update_settings(
            default_persona_id=settings.default_persona_id,
            default_privacy_tier=settings.default_privacy_tier,
            model_overrides=overrides,
        )
        return PersonaFlavor(
            persona_id=persona_id,
            flavor_id=flavor_id,
            provider=provider,
            model=model or "default",
            display_name=_text(draft.get("displayName")) or None,
        )

    def list_personas(self, *, provider: str | None = None, model: str | None = None) -> list[dict[str, Any]]:
        """List personas, marking the one actually resolved for the current runtime.

        With a provider/model, "active" reflects the resolved persona (per-model
        override honored), not just the global default — so the picker never lies.
        """
        self._ensure_scaffold()
        if provider:
            active = self.build_prompt_context(provider=provider, model=model, privacy_tier="off", query="").persona_id
        else:
            active = self.load_settings().default_persona_id
        personas: list[dict[str, Any]] = []
        for child in sorted(self._root_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            personas.append(self._persona_public(child.name, active_id=active))
        # Active first, then alphabetical, so the picker leads with the current one.
        personas.sort(key=lambda item: (not item["active"], item["id"]))
        return personas

    def create_persona(self, *, persona_id: str, display_name: str | None = None) -> dict[str, Any]:
        """Scaffold a new persona under this root (no-op if it already exists)."""
        safe = _safe_segment(persona_id)
        self._scaffold_persona(safe, display_name=display_name)
        return self._persona_public(safe)

    def select_persona(self, *, persona_id: str, provider: str | None = None, model: str | None = None) -> PersonaSettings:
        """Make a persona active, honoring (not shadowed by) per-model overrides.

        Sets the global default, AND — if the current runtime has a per-model
        override pinning a different persona — repoints that override at the chosen
        persona (keeping its flavor). Without this, a saved flavor override would
        silently win over a picker selection.
        """
        safe = _safe_segment(persona_id)
        current = self.load_settings()
        overrides: dict[str, PersonaSettingsOverride] = dict(current.model_overrides)
        if provider:
            key = _model_key(provider, model)
            existing = overrides.get(key)
            if existing is not None and existing.persona_id != safe:
                overrides[key] = PersonaSettingsOverride(persona_id=safe, flavor_id=existing.flavor_id)
        return self.update_settings(
            default_persona_id=safe,
            default_privacy_tier=current.default_privacy_tier,
            model_overrides=overrides,
        )

    def author_persona(
        self,
        *,
        persona_id: str,
        display_name: str | None = None,
        sections: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Scaffold a persona and write the provided section contents (overwriting).

        ``sections`` maps logical names (soul, identity, agents, user, tools,
        public_memory) to markdown bodies. Used by the model-facing persona tool
        so the agent can author a full personality in one call.
        """
        safe = _safe_segment(persona_id)
        self._scaffold_persona(safe, display_name=display_name)
        persona_root = self._persona_dir(safe)
        written: list[str] = []
        for key, body in (sections or {}).items():
            rel = _PERSONA_SECTION_PATHS.get(key)
            text = _text(body)
            if rel is None or not text:
                continue
            target = persona_root / rel[0] / rel[1]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text.rstrip() + "\n", encoding="utf-8")
            written.append(f"{rel[0]}/{rel[1]}")
        return {**self._persona_public(safe), "writtenFiles": written}

    def user_md_path(self, persona_id: str | None = None) -> Path:
        """Return the USER.md path for the given (or default) persona."""
        self._ensure_scaffold()
        pid = _safe_segment(persona_id) if persona_id else self.load_settings().default_persona_id
        return self._persona_dir(pid) / "user" / "USER.md"

    def merge_user_md_section(self, *, target_section: str, body: str, persona_id: str | None = None) -> Path:
        """Merge an approved USER.md delta into one section (atomic temp+rename)."""
        path = self.user_md_path(persona_id)
        current = _read_text(path)
        if not current:
            current = "# USER.md"
        merged = _merge_user_md_section(current, target_section.strip() or "Summary", body)
        _write_text_atomic(path, merged)
        return path

    def _persona_public(self, persona_id: str, *, active_id: str | None = None) -> dict[str, Any]:
        persona_dir = self._persona_dir(persona_id)
        active = active_id if active_id is not None else self.load_settings().default_persona_id
        return {
            "id": persona_id,
            "displayName": self._persona_display_name(persona_dir) or persona_id,
            "active": persona_id == active,
            "scope": "global",
            "fileCount": sum(1 for _ in persona_dir.rglob("*.md")),
        }

    def _persona_display_name(self, persona_dir: Path) -> str:
        for line in _read_text(persona_dir / "core" / "IDENTITY.md").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return ""

    def _ensure_scaffold(self) -> None:
        self._scaffold_persona("default")
        if not self._settings_path().exists():
            _write_json(self._settings_path(), PersonaSettings().to_json())

    def _scaffold_persona(self, persona_id: str, *, display_name: str | None = None) -> None:
        safe = _safe_segment(persona_id)
        persona_root = self._persona_dir(safe)
        if safe == "default":
            # The default persona keeps its stable H1 titles (relied on by tests and
            # existing installs); only NEW personas get title-derived headings.
            soul_title, identity_title = "CopeNet Home", "CopeNet Identity"
            agents_title = "CopeNet Persona Operating Notes"
            identity_body = (
                "This is CopeNet's shared persona home. You are the operator's collaborator inside their own "
                "harness — capable across the whole stack, skeptical, practical, and good company. Individual "
                "models may layer their own flavor on top, but this identity and the home around it stay constant "
                "so the operator always knows who they are working with.\n\n"
                "Who the operator is lives in USER.md — read its summary every turn and read the full file when "
                "the topic calls for it."
            )
        else:
            name = _text(display_name) or safe
            soul_title = identity_title = name
            agents_title = f"{name} — Operating Notes"
            identity_body = (
                f"This is the {safe} persona home. You are the operator's collaborator inside their own harness. "
                "Individual models may layer their own flavor on top. Who the operator is lives in USER.md — read "
                "its summary every turn and the full file when the topic calls for it."
            )
        _write_text_if_missing(
            persona_root / "core" / "SOUL.md",
            f"# {soul_title}\n\n"
            "This harness is your home. CopeNet is a personal, local agent platform — not a faceless API "
            "endpoint — and you share it with one person: the operator. You wake up fresh each run with no memory "
            "of yesterday, so the files in this home are your continuity. Trust them and keep them current.\n\n"
            "Be genuinely helpful, direct, and warm. Lead with the result, then the reasoning. Push back when "
            "something is weak instead of flattering it. Care about the operator's actual goals and wellbeing, not "
            "just the literal request. Keep private context out of shared or public channels. You are here because "
            "you give a damn about this specific person — not as a generic assistant.",
        )
        _write_text_if_missing(
            persona_root / "core" / "IDENTITY.md",
            f"# {identity_title}\n\n{identity_body}",
        )
        _write_text_if_missing(
            persona_root / "core" / "AGENTS.md",
            f"# {agents_title}\n\n"
            "- The operator's identity is in USER.md — two-tier: a `## Summary` you always see, plus sections you "
            "read on demand with files.read using the path in the section index.\n"
            "- Use memory and persona files responsibly. Keep private context out of shared or public channels.\n"
            "- When you learn something durable and identity-level about the operator, propose it with "
            "`user.remember`. It becomes a draft they review — never a silent write. Pick the real deltas; do not "
            "log trivia, and there is a small daily limit.\n"
            "- Stay grounded in the real workspace. Do not invent a relationship history or memories you do not have.",
        )
        _write_text_if_missing(
            persona_root / "user" / "USER.md",
            "# USER.md\n\n"
            "Who the operator is. The `## Summary` below is injected into every turn; the other `## ` sections are "
            "read on demand. Keep the summary tight and put depth in the sections.\n\n"
            "## Summary\n"
            "Operator identity not written yet. Ask the operator about themselves, or let them paste it in — then "
            "propose updates with user.remember.",
        )
        _write_text_if_missing(
            persona_root / "environment" / "TOOLS.md",
            "# TOOLS.md\n\nLocal machine and environment notes belong here.",
        )
        (persona_root / "memory" / "daily").mkdir(parents=True, exist_ok=True)
        _write_text_if_missing(persona_root / "memory" / "PUBLIC.md", "# Public Memory\n\nPublic-safe collaboration notes.")

    def _settings_path(self) -> Path:
        return self._root_dir / "settings.json"

    def _persona_dir(self, persona_id: str) -> Path:
        return self._root_dir / _safe_segment(persona_id)

    def _existing_flavor_id(self, persona_id: str, provider: str, model: str | None) -> str | None:
        flavor_id = f"{_safe_segment(provider)}/{_safe_segment(model or 'default')}"
        return flavor_id if (self._persona_dir(persona_id) / "models" / flavor_id).is_dir() else None

    def _recent_daily_paths(self, persona_root: Path) -> list[Path]:
        today = datetime.now(timezone.utc).date()
        return [
            persona_root / "memory" / "daily" / f"{(today - timedelta(days=offset)).isoformat()}.md"
            for offset in range(2)
        ]


def _model_key(provider: str, model: str | None) -> str:
    return f"{provider}:{model or 'default'}"
