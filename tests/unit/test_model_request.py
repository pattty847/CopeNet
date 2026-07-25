from __future__ import annotations

import asyncio
from typing import Any

import pytest

from copenet.core.model_request import ProviderTextRequest, collect_provider_text
from copenet.prompts import PromptPurpose
from copenet.providers import ProviderEvent


class RecordingProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[dict[str, Any]] = []

    async def run(self, **kwargs):
        self.calls.append(dict(kwargs))
        yield ProviderEvent(kind="delta", text="result")
        yield ProviderEvent(kind="final")


@pytest.mark.asyncio
async def test_native_system_prompt_stays_in_provider_system_channel() -> None:
    provider = RecordingProvider("openai-codex")

    text = await collect_provider_text(
        provider=provider,  # type: ignore[arg-type]
        request=ProviderTextRequest(
            purpose=PromptPurpose.UTILITY,
            prompt="USER_SENTINEL",
            model="model-a",
            system_prompt="SYSTEM_SENTINEL",
        ),
    )

    assert text == "result"
    assert provider.calls[0]["prompt"] == "USER_SENTINEL"
    assert provider.calls[0]["system_prompt"] == "SYSTEM_SENTINEL"


@pytest.mark.asyncio
async def test_claude_cli_system_prompt_uses_provider_system_channel() -> None:
    provider = RecordingProvider("claude-cli")
    traces: list[tuple[str, dict[str, object] | None]] = []

    text = await collect_provider_text(
        provider=provider,  # type: ignore[arg-type]
        request=ProviderTextRequest(
            purpose=PromptPurpose.UTILITY,
            phase="session_title",
            prompt="USER_SENTINEL",
            model="claude-sonnet-4-6",
            system_prompt="SYSTEM_SENTINEL",
        ),
        abort_event=asyncio.Event(),
        trace=lambda event, payload: traces.append((event, payload)),
    )

    assert text == "result"
    assert provider.calls[0]["prompt"] == "USER_SENTINEL"
    assert provider.calls[0]["system_prompt"] == "SYSTEM_SENTINEL"
    started = next(payload for event, payload in traces if event == "model_request_started")
    assert started == {
        "purpose": "utility",
        "phase": "session_title",
        "promptChars": 13,
        "systemPromptChars": 15,
        "providerPromptChars": 13,
        "systemPromptTransport": "native",
    }
