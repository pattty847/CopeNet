from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.host.api import create_app
from copenet.providers import ProviderEvent, ProviderModel


class FakeLocalProvider:
    def __init__(self, name: str, response_text: str) -> None:
        self.name = name
        self.display_name = name.title()
        self.response_text = response_text
        self.calls: list[dict[str, str | None]] = []

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        self.calls.append({"prompt": prompt, "model": model, "system_prompt": system_prompt})
        yield ProviderEvent(kind="delta", text=self.response_text, provider_session_id=provider_session_id)
        yield ProviderEvent(kind="final", provider_session_id=provider_session_id)

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False, "promptedToolUse": True},
        }

    async def list_models(self) -> list[ProviderModel]:
        return [
            ProviderModel(
                id=f"{self.name}-model",
                display_name=f"{self.display_name} Model",
                provider=self.name,
                capabilities={"chat": True},
            )
        ]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_library(root: Path) -> None:
    _write(root / "Voice Map.md", "# Voice Map\n\n## Core voice traits\n- fake-expert certainty\n- deadpan ridiculous jargon\n\n## Risks / what to avoid\n- sounding like a normie explaining the joke\n")
    _write(root / "Humor Mechanisms.md", "# Humor Mechanisms\n\n## Faux-clinical overanalysis\nnormal image becomes biological failure.\n\n## Cadence-first gibberish parody\nsports desk rhythm with cursed content.\n")
    _write(root / "Meme Engines.md", "# Meme Engines\n\n## Institutional brainrot\nTranslate cursed behavior into polished memo language.\n\n## Political inversion\nApply bootstrap rhetoric upward.\n")
    _write(root / "Caption Pattern Bank.md", "# Caption Pattern Bank\n\n## Pattern\nvisual cue -> inference -> collapse\n")
    _write(root / "Human Nuance Capture.md", "# Human Nuance Capture\n\n## Goal\nCapture hidden lore and image provenance.\n")
    _write(root / "Topical Memeifier.md", "# Topical Memeifier\n\n## Workflow\nStart from contradiction and choose the engine.\n")
    _write(root / "Subculture Lexicon - Looksmaxxing Mogging.md", "# Lexicon\n\n- mogging\n- clavicular\n- low T\n")
    _write(root / "Feedback" / "2026-04-18-post-bank-feedback.md", "# Feedback\n\n## Updated rules\nLess abstract, more artifact. Avoid quirky slogan energy.\n")
    _write(root / "Case Studies" / "2026-04-18-clavicular-mugshot-meme.md", "# Case Study\n\n## Why it works\nDense diagnostic chain.\n")
    _write(root / "Case Studies" / "2026-04-19-sports-talk-gibberish-parody.md", "# Sports talk gibberish parody\n\n## Why it works\nCadence-first jargon parody.\n")


@pytest.fixture
def app_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    kb_root = tmp_path / "meme-kb"
    _seed_library(kb_root)
    monkeypatch.setenv("COPNET_MEME_KB_ROOT", str(kb_root))
    lm_studio = FakeLocalProvider(
        "lm-studio",
        """
        {
          "candidates": [
            {
              "direction": "Existential caption",
              "format": "reaction_caption",
              "text": "ROTATED THE FRY 12 DEGREES AND NOW IT COUNTS AS A DIFFERENT ASSET CLASS / before the allocation committee notices",
              "optional_caption": "copeharderpls",
              "needs_visual_context": true,
              "notes": "works with a thousand-yard stare image"
            },
            {
              "direction": "Relatable office joke",
              "format": "one-liner",
              "text": "just another office burnout moment",
              "needs_visual_context": false
            }
          ]
        }
        """.strip(),
    )
    ollama = FakeLocalProvider(
        "ollama",
        """
        {
          "candidates": [
            {
              "direction": "Deadpan market joke",
              "format": "tweet_screenshot",
              "text": "THE MARKET ISN'T CRASHING IT'S JUST EXPRESSING ITSELF / under compliance review",
              "needs_visual_context": false,
              "notes": "tweet screenshot shell"
            }
          ]
        }
        """.strip(),
    )
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={"lm-studio": lm_studio, "ollama": ollama},
    )
    _, token = orchestrator.register_app(app_id="subtext", display_name="Subtext", default_provider="lm-studio")
    app = create_app(orchestrator)
    with TestClient(app) as client:
        yield client, token, lm_studio, ollama


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_meme_ideation_endpoint_happy_path(app_client) -> None:
    client, token, lm_studio, _ = app_client

    response = client.post(
        "/api/v1/memes/ideate",
        headers=_auth(token),
        json={
            "topic": "market panic",
            "trendSummary": "retail traders acting brave in a selloff",
            "requestedCount": 2,
            "model": "uncensored-gemma-4",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "lm-studio"
    assert payload["model"] == "uncensored-gemma-4"
    assert payload["preset"] == "meme-ideation"
    assert payload["schemaVersion"] == "v1"
    assert payload["promptVersion"] == "meme-ideation-v2"
    assert payload["knowledgePackVersion"] == "meme-kb-v1"
    assert payload["artifactShell"]
    assert payload["mutationNotes"]
    assert payload["candidates"][0]["direction"] == "Existential caption"
    assert "retail traders acting brave in a selloff" in (lm_studio.calls[0]["prompt"] or "")
    assert "Anti-pattern bans" in (lm_studio.calls[0]["system_prompt"] or "")


def test_meme_ideation_endpoint_accepts_frontend_alias_preset(app_client) -> None:
    client, token, lm_studio, _ = app_client

    response = client.post(
        "/api/v1/memes/ideate",
        headers=_auth(token),
        json={
            "topic": "discipline posting",
            "trendSummary": "three weeks of routine content turning into moral superiority",
            "requestedCount": 4,
            "preset": "sharpshooter",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["preset"] == "sharpshooter"
    assert "Preset mode: sharpshooter" in (lm_studio.calls[0]["prompt"] or "")


def test_meme_ideation_endpoint_supports_provider_override(app_client) -> None:
    client, token, _, ollama = app_client

    response = client.post(
        "/api/v1/memes/ideate",
        headers=_auth(token),
        json={"imageSpringboard": "guy laughing while portfolio burns", "requestedCount": 1, "provider": "ollama"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "ollama"
    assert payload["candidates"][0]["format"] == "tweet_screenshot"
    assert payload["artifactShell"] in {"reaction image overlay", "screenshot annotation"}
    assert len(ollama.calls) == 1


def test_meme_ideation_endpoint_judge_filters_mid_candidates(app_client) -> None:
    client, token, _, _ = app_client

    response = client.post(
        "/api/v1/memes/ideate",
        headers=_auth(token),
        json={"topic": "market panic", "requestedCount": 2, "debug": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["candidates"]) == 1
    assert payload["judgeWarnings"]
    assert any("anti-mid threshold" in warning for warning in payload["judgeWarnings"] + payload.get("warnings", []))


def test_meme_ideation_endpoint_handles_missing_knowledge_base_with_warning(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    monkeypatch.setenv("COPNET_MEME_KB_ROOT", str(tmp_path / "missing-kb"))
    provider = FakeLocalProvider(
        "lm-studio",
        '{"candidates":[{"direction":"Artifact","format":"receipt","text":"pending review before the allocation committee notices","needs_visual_context":true}]}',
    )
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={"lm-studio": provider},
    )
    _, token = orchestrator.register_app(app_id="subtext", display_name="Subtext", default_provider="lm-studio")
    app = create_app(orchestrator)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/memes/ideate",
            headers=_auth(token),
            json={"topic": "policy panic", "trendSummary": "temporary operation spin", "requestedCount": 1},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["warnings"]
    assert "meme knowledge base not found" in payload["warnings"][0]


def test_meme_ideation_endpoint_rejects_invalid_requests(app_client) -> None:
    client, token, _, _ = app_client

    response = client.post(
        "/api/v1/memes/ideate",
        headers=_auth(token),
        json={"requestedCount": 99},
    )

    assert response.status_code == 422
