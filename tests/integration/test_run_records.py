import asyncio

import pytest

from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent


class ScriptedPromptedProvider:
    name = "prompted"
    display_name = "Prompted"

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.prompts: list[str] = []
        self._index = 0

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        self.prompts.append(prompt)
        text = self.outputs[self._index]
        self._index += 1
        yield ProviderEvent(kind="delta", text=text, provider_session_id=provider_session_id or "provider-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {
                "chat": True,
                "streaming": True,
                "toolCalls": False,
                "promptedToolUse": True,
            },
        }

    async def list_models(self) -> list:
        return []


async def _collect_events(orchestrator: Orchestrator, request: ChatSendRequest) -> tuple[dict, list[dict]]:
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    result = await orchestrator.send_chat(request, emit=emit)
    return result, events


@pytest.mark.asyncio
async def test_send_chat_persists_run_record_for_multi_step_repo_exploration(tmp_path) -> None:
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={
            "prompted": ScriptedPromptedProvider(
                outputs=[
                    '{"tool_id":"files.list","arguments":{"path":"."}}',
                    '{"tool_id":"files.read","arguments":{"path":"README.md"}}',
                    "I inspected the repo and the README after listing files.",
                ]
            )
        },
    )

    result, events = await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="Inspect the repository", provider="prompted"),
    )

    assert result["status"] == "ok"
    assert events[-1]["state"] == "final"
    runs = orchestrator._run_store.list_for_session("alpha")
    assert len(runs) == 1
    assert runs[0].status == "ok"
    assert [step["toolId"] for step in runs[0].tool_steps] == ["files.list", "files.read"]
    assert runs[0].artifact_ids
    assert "README" in runs[0].output_summary
