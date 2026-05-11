from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent


class PersonaDraftProvider:
    name = "persona-draft"
    display_name = "Persona Draft"

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.system_prompts: list[str | None] = []

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        self.prompts.append(prompt)
        self.system_prompts.append(system_prompt)
        yield ProviderEvent(
            kind="delta",
            text='{"displayName":"Drafted Flavor","identityMarkdown":"# Drafted Flavor\\n\\nUses private context.","soulMarkdown":"## Soul","notesMarkdown":"- note"}',
            provider_session_id=provider_session_id or "persona-draft-session",
        )
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict[str, Any]:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False},
        }

    async def list_models(self) -> list:
        return []


@pytest.mark.asyncio
async def test_draft_persona_flavor_uses_private_persona_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPNET_DATA_DIR", str(tmp_path / "data"))
    persona_root = tmp_path / "data" / "personas" / "default"
    (persona_root / "memory").mkdir(parents=True)
    (persona_root / "user").mkdir(parents=True)
    (persona_root / "environment").mkdir(parents=True)
    (persona_root / "memory" / "MEMORY.md").write_text("Pat prefers continuity over generic vibes.\n", encoding="utf-8")
    (persona_root / "user" / "USER.md").write_text("Pat is building CopeNet as a friend-with-a-workshop product.\n", encoding="utf-8")
    (persona_root / "environment" / "TOOLS.md").write_text("Claude and Codex are both available lanes.\n", encoding="utf-8")

    provider = PersonaDraftProvider()
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={"persona-draft": provider},
    )

    payload = await orchestrator.draft_persona_flavor(provider_id="persona-draft", model="model-a")

    assert payload["draft"]["displayName"] == "Drafted Flavor"
    combined_prompt = "\n\n".join(filter(None, [provider.system_prompts[-1], provider.prompts[-1]]))
    assert "Pat prefers continuity over generic vibes." in combined_prompt
    assert "friend-with-a-workshop" in combined_prompt
