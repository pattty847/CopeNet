from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent


class PersonaAwareProvider:
    name = "persona-aware"
    display_name = "Persona Aware"

    def __init__(self) -> None:
        self.system_prompts: list[str | None] = []

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        self.system_prompts.append(system_prompt)
        yield ProviderEvent(kind="delta", text="done", provider_session_id=provider_session_id or "persona-session")
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
async def test_send_chat_injects_persona_context_and_locks_session_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPNET_DATA_DIR", str(tmp_path / "data"))
    persona_root = tmp_path / "data" / "personas"
    memory_dir = persona_root / "default" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("Private CopeNet continuity memory.\n", encoding="utf-8")

    provider = PersonaAwareProvider()
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={"persona-aware": provider},
    )
    orchestrator._memory_service.upsert_memory(
        category="ongoing_priority",
        title="Persona runtime work",
        summary="RELEVANCE_MEMORY_SENTINEL",
    )

    async def emit(_: dict[str, Any]) -> None:
        return None

    result = await orchestrator.send_chat(
        ChatSendRequest(
            session_key="alpha",
            message="Help me continue the persona runtime work.",
            provider="persona-aware",
            model="model-a",
        ),
        emit=emit,
    )

    assert result["status"] == "ok"
    system_prompt = provider.system_prompts[-1] or ""
    assert "CopeNet Home" in system_prompt
    assert "Private CopeNet continuity memory." in system_prompt
    assert "CopeNet Persona Operating Notes" not in system_prompt
    assert "RELEVANCE_MEMORY_SENTINEL" not in system_prompt
    session = orchestrator.resolve_session("alpha")
    assert session["personaId"] == "default"
    assert session["personaPrivacyTier"] == "private"


@pytest.mark.asyncio
async def test_send_chat_safe_persona_context_excludes_private_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPNET_DATA_DIR", str(tmp_path / "data"))
    memory_dir = tmp_path / "data" / "personas" / "default" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("Private operator memory.\n", encoding="utf-8")
    (memory_dir / "PUBLIC.md").write_text("Public-safe operator collaboration style.\n", encoding="utf-8")

    provider = PersonaAwareProvider()
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={"persona-aware": provider},
    )

    async def emit(_: dict[str, Any]) -> None:
        return None

    await orchestrator.send_chat(
        ChatSendRequest(
            session_key="shared-alpha",
            message="Reply in the shared channel.",
            provider="persona-aware",
            model="model-a",
            persona_privacy_tier="safe",
        ),
        emit=emit,
    )

    system_prompt = provider.system_prompts[-1] or ""
    assert "Public-safe operator collaboration style." in system_prompt
    assert "Private operator memory." not in system_prompt
    assert orchestrator.resolve_session("shared-alpha")["personaPrivacyTier"] == "safe"


@pytest.mark.asyncio
async def test_send_chat_code_profile_injects_persona_agent_notes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COPNET_DATA_DIR", str(tmp_path / "data"))
    provider = PersonaAwareProvider()
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={"persona-aware": provider},
    )

    async def emit(_: dict[str, Any]) -> None:
        return None

    await orchestrator.send_chat(
        ChatSendRequest(
            session_key="code-alpha",
            message="Fix the code.",
            provider="persona-aware",
            model="model-a",
            system_prompt_id="builder",
        ),
        emit=emit,
    )

    assert "CopeNet Persona Operating Notes" in (provider.system_prompts[-1] or "")
