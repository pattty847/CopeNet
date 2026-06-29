"""Profile, persona, and memory facade methods for the orchestrator."""

from __future__ import annotations

import asyncio

from copenet.core.persona import PersonaPrivacyTier

from .persona_flavor import parse_persona_flavor_draft as _parse_persona_flavor_draft


class IdentityFacadeMixin:
    def get_persona(self, *, provider: str | None = None, model: str | None = None, privacy_tier: PersonaPrivacyTier | None = None) -> dict:
        """Return the resolved Persona Home summary for UI clients."""
        return self._persona_service.get_summary(provider=provider, model=model, privacy_tier=privacy_tier)

    def get_persona_settings(self) -> dict:
        """Return Persona Home defaults and provider/model overrides."""
        return self._persona_service.load_settings().to_public_dict()

    def list_personas(self, *, provider: str | None = None, model: str | None = None) -> list[dict]:
        """List available personas (active one first) for the persona picker."""
        return self._persona_service.list_personas(provider=provider, model=model)

    def create_persona(self, *, persona_id: str, display_name: str | None = None) -> dict:
        """Create a new persona scaffold and return its public record."""
        return self._persona_service.create_persona(persona_id=persona_id, display_name=display_name)

    def select_persona(self, *, persona_id: str, provider: str | None = None, model: str | None = None) -> dict:
        """Activate a persona for the current runtime (overrides honored)."""
        return self._persona_service.select_persona(persona_id=persona_id, provider=provider, model=model).to_public_dict()

    def update_persona_settings(
        self,
        *,
        default_persona_id: str | None = None,
        default_privacy_tier: PersonaPrivacyTier | None = None,
        model_overrides: dict | None = None,
    ) -> dict:
        """Persist Persona Home defaults and provider/model overrides."""
        return self._persona_service.update_settings(
            default_persona_id=default_persona_id,
            default_privacy_tier=default_privacy_tier,
            model_overrides=model_overrides,
        ).to_public_dict()

    def get_persona_context(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        privacy_tier: PersonaPrivacyTier | None = None,
        query: str = "",
    ) -> dict:
        """Return effective Persona Home prompt context for debugging and UI proof."""
        return self._persona_service.build_prompt_context(
            provider=provider or "",
            model=model,
            privacy_tier=privacy_tier,
            query=query,
        ).to_public_dict()

    async def draft_persona_flavor(self, *, provider_id: str, model: str | None = None) -> dict:
        """Ask a model to draft its own compact identity flavor without saving it."""
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ValueError(f"unsupported provider: {provider_id}")
        persona_context = self._persona_service.build_prompt_context(
            provider=provider_id,
            model=model,
            privacy_tier="private",
            query="draft a model flavor",
        )
        prompt = (
            "Use this CopeNet Persona Home context as your base and draft a model-specific flavor.\n\n"
            f"{persona_context.prompt}\n\n"
            "Draft a compact CopeNet model identity flavor for yourself. "
            "Return JSON only with displayName, identityMarkdown, soulMarkdown, and notesMarkdown. "
            "Reflect the operator/workspace reality honestly. "
            "Do not invent new private memories or claim a relationship history you do not have."
        )
        abort_event = asyncio.Event()
        parts: list[str] = []
        async for event in provider.run(
            prompt=prompt,
            provider_session_id=None,
            abort_event=abort_event,
            model=model,
            system_prompt=(
                "You draft concise assistant identity files for local operator review. "
                "Use the provided Persona Home context carefully and stay grounded in the real workspace."
            ),
        ):
            if event.kind == "delta" and event.text:
                parts.append(event.text)
        raw_text = "".join(parts).strip()
        return {
            "provider": provider_id,
            "model": model,
            "draft": _parse_persona_flavor_draft(raw_text),
            "rawText": raw_text,
        }

    def save_persona_flavor(self, *, provider_id: str, model: str | None = None, draft: dict | None = None) -> dict:
        """Save an operator-approved model identity flavor."""
        return self._persona_service.save_flavor(provider=provider_id, model=model, draft=draft or {}).to_public_dict()

    def list_memory(self, *, include_archived: bool = False, category: str | None = None, status: str = "active", limit: int = 50) -> list[dict]:
        """Return recent user-visible memory items (status: active | draft | all)."""
        return [
            item.to_public_dict()
            for item in self._memory_service.list_memory(
                include_archived=include_archived,
                category=category if category in {"preference", "project_convention", "ongoing_priority", "fact"} else None,
                status=status,
                limit=limit,
            )
        ]

    def upsert_memory(
        self,
        *,
        category: str,
        title: str,
        summary: str,
        detail: str | None = None,
        tags: list[str] | None = None,
        memory_id: str | None = None,
    ) -> dict:
        """Create or update one user-visible memory item."""
        item = self._memory_service.upsert_memory(
            memory_id=memory_id,
            category=category,  # type: ignore[arg-type]
            title=title,
            summary=summary,
            detail=detail,
            tags=tags or [],
            source="explicit",
            confidence=0.95,
        )
        return item.to_public_dict()

    def archive_memory(self, *, memory_id: str, archived: bool = True) -> dict | None:
        """Archive or restore one memory item."""
        item = self._memory_service.archive_memory(memory_id, archived=archived)
        return item.to_public_dict() if item is not None else None

    def approve_memory(
        self,
        *,
        memory_id: str,
        category: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        detail: str | None = None,
        tags: list[str] | None = None,
    ) -> dict | None:
        """Commit a model-proposed draft (optionally with operator edits)."""
        item = self._memory_service.approve_memory(
            memory_id,
            category=category,  # type: ignore[arg-type]
            title=title,
            summary=summary,
            detail=detail,
            tags=tags,
        )
        return item.to_public_dict() if item is not None else None

    def discard_memory(self, *, memory_id: str) -> bool:
        """Delete a model-proposed draft outright."""
        return self._memory_service.discard_memory(memory_id)

    def list_user_notes(self, *, status: str = "draft") -> list[dict]:
        """Return model-proposed USER.md deltas (status: draft | approved | all)."""
        return [item.to_public_dict() for item in self._user_notes_service.list_proposals(status=status)]

    def approve_user_note(
        self,
        *,
        note_id: str,
        target_section: str | None = None,
        summary: str | None = None,
        body: str | None = None,
    ) -> dict | None:
        """Merge a USER.md proposal into the active persona's USER.md (optionally edited)."""
        item = self._user_notes_service.approve_user_note(
            note_id,
            target_section=target_section,
            summary=summary,
            body=body,
        )
        return item.to_public_dict() if item is not None else None

    def discard_user_note(self, *, note_id: str) -> bool:
        """Delete a model-proposed USER.md draft outright."""
        return self._user_notes_service.discard_user_note(note_id)

    def get_return_briefing(self) -> dict | None:
        """Return the latest return briefing payload, if any."""
        briefing = self._briefing_service.build_return_briefing()
        return briefing.to_public_dict() if briefing is not None else None
