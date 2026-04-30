from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent


def _write_overlay(root: Path) -> None:
    profile_dir = root / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "identity.json").write_text(
        json.dumps(
            {
                "profileId": "pat-profile:patrick",
                "displayName": "Patrick Cope",
                "configured": True,
                "priorities": [{"id": "school", "label": "School", "weight": 1.0}],
                "goals": [{"id": "ship", "text": "Ship CopeNet", "source": "explicit", "updatedAt": "2026-04-30T00:00:00Z"}],
                "tonePreference": {
                    "directness": "terse",
                    "formality": "casual",
                    "preferBullets": True,
                },
                "noiseFilters": ["ignore china crypto bans unless price moves materially"],
                "scheduleBasics": ["Homework due tonight"],
                "recurringConstraints": ["School first when deadlines are imminent"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (profile_dir / "observed_tendencies.json").write_text("[]\n", encoding="utf-8")
    (profile_dir / "guidance_rules.json").write_text(
        json.dumps(
            [
                {
                    "id": "guide-school-first",
                    "rule": "When homework is due tonight, push school before crypto.",
                    "priority": "high",
                    "source": "explicit",
                    "rationale": "Pat asked for corrective nudges.",
                    "updatedAt": "2026-04-30T00:00:00Z",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    (profile_dir / "notes.md").write_text("# Pat Notes\n\nBe helpful.\n", encoding="utf-8")


class ProfileAwareProvider:
    name = "profiled"
    display_name = "Profiled"

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
        yield ProviderEvent(kind="delta", text="done", provider_session_id=provider_session_id or "profiled-session")
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
async def test_send_chat_injects_pat_profile_context_and_emits_profile_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPNET_DATA_DIR", str(tmp_path / "data"))
    _write_overlay(tmp_path / "data")

    provider = ProfileAwareProvider()
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={"profiled": provider},
    )

    chat_events: list[dict[str, Any]] = []
    side_events: list[tuple[str, dict[str, Any]]] = []

    async def emit(payload: dict[str, Any]) -> None:
        chat_events.append(payload)

    async def emit_event(event: str, payload: dict[str, Any]) -> None:
        side_events.append((event, payload))

    result = await orchestrator.send_chat(
        ChatSendRequest(
            session_key="alpha",
            message="Please lead with the punchline.",
            provider="profiled",
            model="model-a",
        ),
        emit=emit,
        emit_event=emit_event,
    )

    assert result["status"] == "ok"
    assert provider.system_prompts
    assert "Pat Profile" in (provider.system_prompts[-1] or "")
    assert "School first when deadlines are imminent" in (provider.system_prompts[-1] or "")
    assert any(event == "profile.changed" for event, _ in side_events)
    assert any(event == "briefing.ready" for event, _ in side_events)
