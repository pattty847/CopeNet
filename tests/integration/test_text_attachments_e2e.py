"""A text attachment (a discussed media transcript) reaches the model on every turn."""

from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.orchestrator import Orchestrator
from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent
from test_multiturn_responses_e2e import _COMPLETED, FakeResponsesProvider, ResumingCliProvider, _collect

TRANSCRIPT = 'Transcript of "Sleep Myths"\nSource: https://example.com/v\n\nEight hours is a floor, not a ceiling.'


def _orchestrator(tmp_path: Path, providers: dict) -> Orchestrator:
    return Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers=providers,
    )


def _user_text(item: dict) -> str:
    return " ".join(part.get("text", "") for part in item["content"] if part.get("type") == "input_text")


@pytest.mark.asyncio
async def test_attached_transcript_reaches_responses_model_and_replays_on_follow_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    provider = FakeResponsesProvider(
        turns=[
            [ProviderEvent(kind="delta", text="The claim is that eight hours is a minimum."), _COMPLETED],
            [ProviderEvent(kind="delta", text="Evidence is mixed."), _COMPLETED],
        ]
    )
    orchestrator = _orchestrator(tmp_path, {"fake-responses": provider})
    attachment = orchestrator._chat_attachment_store.save(
        data=TRANSCRIPT.encode("utf-8"), mime_type="text/plain", filename="Sleep Myths.txt"
    )

    await _collect(
        orchestrator,
        ChatSendRequest(
            session_key="discuss",
            message="What is the main claim?",
            provider="fake-responses",
            attachment_ids=(attachment.attachment_id,),
        ),
    )
    await _collect(
        orchestrator,
        ChatSendRequest(session_key="discuss", message="Is that true?", provider="fake-responses"),
    )

    first_turn_user = [item for item in provider.seen_inputs[0] if item.get("role") == "user"][-1]
    assert first_turn_user["content"][0]["text"] == "What is the main claim?"
    assert '<attached_file name="Sleep Myths.txt">' in _user_text(first_turn_user)
    assert "Eight hours is a floor, not a ceiling." in _user_text(first_turn_user)

    # The follow-up carries the transcript again through the replayed first turn.
    replayed_users = [item for item in provider.seen_inputs[1] if item.get("role") == "user"]
    assert "Eight hours is a floor, not a ceiling." in _user_text(replayed_users[0])
    assert _user_text(replayed_users[-1]) == "Is that true?"


@pytest.mark.asyncio
async def test_attached_transcript_reaches_resuming_cli_prompt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    provider = ResumingCliProvider("claude-cli")
    orchestrator = _orchestrator(tmp_path, {"claude-cli": provider})
    attachment = orchestrator._chat_attachment_store.save(
        data=TRANSCRIPT.encode("utf-8"), mime_type="text/plain", filename="Sleep Myths.txt"
    )

    await _collect(
        orchestrator,
        ChatSendRequest(
            session_key="discuss",
            message="Explain it simply.",
            provider="claude-cli",
            attachment_ids=(attachment.attachment_id,),
        ),
    )

    assert "Explain it simply." in provider.prompts[0]
    assert "Eight hours is a floor, not a ceiling." in provider.prompts[0]


@pytest.mark.asyncio
async def test_transcript_only_send_is_accepted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    provider = FakeResponsesProvider(turns=[[ProviderEvent(kind="delta", text="Got it."), _COMPLETED]])
    orchestrator = _orchestrator(tmp_path, {"fake-responses": provider})
    attachment = orchestrator._chat_attachment_store.save(
        data=TRANSCRIPT.encode("utf-8"), mime_type="text/plain", filename="Sleep Myths.txt"
    )

    events = await _collect(
        orchestrator,
        ChatSendRequest(
            session_key="discuss", message="", provider="fake-responses", attachment_ids=(attachment.attachment_id,)
        ),
    )

    assert any(event.get("state") == "final" for event in events)
    assert "Eight hours is a floor" in _user_text(provider.seen_inputs[0][-1])
