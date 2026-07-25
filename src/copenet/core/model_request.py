"""Purpose-tagged boundary for provider text requests outside interactive chat."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Callable

from copenet.core.harness.tool_loop_common import compose_provider_prompt, provider_system_prompt
from copenet.prompts import PromptPurpose
from copenet.providers import Provider, ProviderEvent


TraceRecorder = Callable[[str, dict[str, object] | None], None]


@dataclass(frozen=True)
class ProviderTextRequest:
    purpose: PromptPurpose
    prompt: str
    model: str | None
    system_prompt: str | None = None
    provider_session_id: str | None = None
    phase: str | None = None


async def stream_provider_text(
    *,
    provider: Provider,
    request: ProviderTextRequest,
    abort_event: asyncio.Event | None = None,
    trace: TraceRecorder | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Render one provider request consistently and expose safe boundary metadata."""
    provider_prompt = compose_provider_prompt(provider, request.prompt, request.system_prompt)
    native_system_prompt = provider_system_prompt(provider, request.system_prompt)
    phase = request.phase or request.purpose.value
    if trace is not None:
        trace(
            "model_request_started",
            {
                "purpose": request.purpose.value,
                "phase": phase,
                "promptChars": len(request.prompt),
                "systemPromptChars": len(request.system_prompt or ""),
                "providerPromptChars": len(provider_prompt),
                "systemPromptTransport": "native" if native_system_prompt else (
                    "embedded" if request.system_prompt else "none"
                ),
            },
        )

    delta_count = 0
    async for event in provider.run(
        prompt=provider_prompt,
        provider_session_id=request.provider_session_id,
        abort_event=abort_event or asyncio.Event(),
        model=request.model,
        system_prompt=native_system_prompt,
    ):
        if event.kind == "delta":
            delta_count += 1
        yield event
        if event.kind == "final":
            break

    if trace is not None:
        trace(
            "model_request_completed",
            {
                "purpose": request.purpose.value,
                "phase": phase,
                "deltaCount": delta_count,
            },
        )


async def collect_provider_text(
    *,
    provider: Provider,
    request: ProviderTextRequest,
    abort_event: asyncio.Event | None = None,
    trace: TraceRecorder | None = None,
) -> str:
    """Collect text from a purpose-tagged provider request."""
    chunks: list[str] = []
    async for event in stream_provider_text(
        provider=provider,
        request=request,
        abort_event=abort_event,
        trace=trace,
    ):
        if event.kind == "delta" and event.text:
            chunks.append(event.text)
        elif event.kind == "final" and event.text and not chunks:
            chunks.append(event.text)
        elif event.kind == "error":
            raise RuntimeError(event.message or f"{request.purpose.value} model request failed")
    return "".join(chunks).strip()
