"""Every transport must deliver the same composed profile/Access prompt.

Phase 1 of docs/plans/CONTEXT_CONVEYOR_NEXT_STEPS.md. Before this, `compose_prompt`
was called only in `host/rpc_chat.py`, so the REST/SSE app lane, `copenet chat send`,
Fleet, and the coordination lanes all reached the provider with no profile and no
Access overlay while still escalating tool policy from `task_prompt_id`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.prompts import compose_prompt
from copenet.prompts.loader import PERSONA_PLACEHOLDER, get_task_mode_text
from copenet.providers import ProviderEvent


def assert_composed_prompt_delivered(expected: str, delivered: str | None) -> None:
    """The composed text must reach the provider intact, modulo the persona splice.

    A plain substring check stopped working once persona moved from "appended at the
    end" to "spliced into `{{persona}}`": the composed string still carries the
    placeholder, while the delivered one carries resolved voice in its place. Both
    halves must still appear, in order, so the layering cannot silently drop a layer.
    """
    assert delivered is not None, "provider reached with no instructions"
    head, sep, tail = expected.partition(PERSONA_PLACEHOLDER)
    assert head and head in delivered, "composed prompt did not reach the provider"
    if not sep:
        return
    assert tail and tail in delivered, "text after the persona slot was dropped"
    assert delivered.index(head) < delivered.index(tail), "composed layers arrived out of order"


class RecordingProvider:
    """Captures exactly what reached the provider boundary."""

    name = "openai-codex"
    display_name = "Recording"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def describe(self) -> dict[str, object]:
        return {"id": self.name, "available": True, "capabilities": {"chat": True}}

    async def list_models(self):
        return []

    async def run(self, prompt, provider_session_id, abort_event, model=None, system_prompt=None):
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt, "model": model})
        yield ProviderEvent(kind="delta", text="ok")
        yield ProviderEvent(kind="final", provider_session_id="prov-1")


@pytest.fixture()
def orchestrator(tmp_path: Path) -> tuple[Orchestrator, RecordingProvider]:
    provider = RecordingProvider()
    orch = Orchestrator(sessions_dir=tmp_path, providers={provider.name: provider})
    return orch, provider


def _request(session_key: str, **overrides: Any) -> ChatSendRequest:
    base: dict[str, Any] = {
        "session_key": session_key,
        "message": "hello",
        "provider": "openai-codex",
        "system_prompt_id": "builder",
        "task_prompt_id": "full-access",
        "allow_tools": False,
    }
    base.update(overrides)
    return ChatSendRequest(**base)


async def _noop_emit(_payload: dict[str, Any]) -> None:
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize("session_key", ["ws-lane", "rest-lane", "cli-lane", "fleet-lane", "coordination-lane"])
async def test_every_entry_point_receives_the_composed_profile_and_access_prompt(
    orchestrator: tuple[Orchestrator, RecordingProvider],
    session_key: str,
) -> None:
    """A ChatSendRequest carrying only ids — as every non-WS transport builds it."""
    orch, provider = orchestrator
    expected = compose_prompt("builder", "full-access")
    assert expected  # guard against the presets going missing

    await orch.send_chat(_request(session_key), emit=_noop_emit)

    assert_composed_prompt_delivered(expected, provider.calls[-1]["system_prompt"])


@pytest.mark.asyncio
async def test_explicit_system_prompt_is_treated_as_a_deliberate_override(
    orchestrator: tuple[Orchestrator, RecordingProvider],
) -> None:
    orch, provider = orchestrator

    await orch.send_chat(
        _request("override-lane", system_prompt="OVERRIDE_SENTINEL"),
        emit=_noop_emit,
    )

    system_prompt = provider.calls[-1]["system_prompt"] or ""
    assert "OVERRIDE_SENTINEL" in system_prompt
    assert "Builder" not in system_prompt


@pytest.mark.asyncio
async def test_access_overlay_travels_with_the_escalated_tool_policy(
    orchestrator: tuple[Orchestrator, RecordingProvider],
) -> None:
    """Full Access must never grant authority without also stating what it means.

    Asserts the Access overlay specifically rather than a whole composed prompt:
    `compose_prompt(None, ...)` omits the profile and domain layers that a real
    request carries, so comparing full compositions would only test the layering
    order, not that the authority statement travelled.
    """
    orch, provider = orchestrator
    access_text = (get_task_mode_text("full-access") or "").strip()
    assert access_text

    await orch.send_chat(_request("authority-lane"), emit=_noop_emit)

    assert access_text in (provider.calls[-1]["system_prompt"] or "")
