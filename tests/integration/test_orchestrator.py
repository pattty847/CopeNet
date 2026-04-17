import asyncio

import pytest

from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent


class FakeProvider:
    name = "fake"
    display_name = "Fake"

    def __init__(self, *, wait_for_abort: bool = False) -> None:
        self.wait_for_abort = wait_for_abort

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        if self.wait_for_abort:
            await abort_event.wait()
            return
        yield ProviderEvent(kind="delta", text="hello", provider_session_id=provider_session_id or "provider-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False},
        }

    async def list_models(self) -> list:
        return []


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


@pytest.fixture
def fake_orchestrator(tmp_path) -> Orchestrator:
    return Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={"fake": FakeProvider(), "fake-alt": FakeProvider()},
    )


@pytest.mark.asyncio
async def test_send_chat_streams_delta_and_final(fake_orchestrator: Orchestrator) -> None:
    result, events = await _collect_events(
        fake_orchestrator,
        ChatSendRequest(session_key="alpha", message="Hello", provider="fake", model="model-a"),
    )

    assert result["status"] == "ok"
    assert [event["state"] for event in events] == ["delta", "final"]


@pytest.mark.asyncio
async def test_provider_mismatch_raises_binding_error(fake_orchestrator: Orchestrator) -> None:
    await _collect_events(
        fake_orchestrator,
        ChatSendRequest(session_key="alpha", message="Hello", provider="fake", model="model-a"),
    )

    with pytest.raises(RuntimeError, match="locked to provider"):
        await _collect_events(
            fake_orchestrator,
            ChatSendRequest(session_key="alpha", message="Again", provider="fake-alt", model="model-a"),
        )


@pytest.mark.asyncio
async def test_abort_sets_abort_event_and_run_terminates(tmp_path) -> None:
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={"fake": FakeProvider(wait_for_abort=True)},
    )
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    task = asyncio.create_task(
        orchestrator.send_chat(
            ChatSendRequest(session_key="alpha", message="Hello", provider="fake", model="model-a"),
            emit=emit,
        )
    )
    await asyncio.sleep(0.05)
    abort_result = orchestrator.abort("alpha")
    result = await asyncio.wait_for(task, timeout=1.0)

    assert abort_result["aborted"] is True
    assert result["status"] == "ok"
    assert events[-1]["state"] == "final"


@pytest.mark.asyncio
async def test_history_returns_stored_messages(fake_orchestrator: Orchestrator) -> None:
    await _collect_events(
        fake_orchestrator,
        ChatSendRequest(session_key="alpha", message="Hello", provider="fake", model="model-a"),
    )

    history = fake_orchestrator.history("alpha")
    assert [item["role"] for item in history] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_idempotency_key_returns_cached_status(fake_orchestrator: Orchestrator) -> None:
    request = ChatSendRequest(
        session_key="alpha",
        message="Hello",
        provider="fake",
        model="model-a",
        idempotency_key="same-run",
    )
    first, _ = await _collect_events(fake_orchestrator, request)
    second, events = await _collect_events(fake_orchestrator, request)

    assert first["status"] == "ok"
    assert second["status"] == "cached"
    assert events == []


@pytest.mark.asyncio
async def test_send_chat_persists_state_and_answer_artifact(fake_orchestrator: Orchestrator) -> None:
    await _collect_events(
        fake_orchestrator,
        ChatSendRequest(session_key="alpha", message="Inspect the runtime", provider="fake", model="model-a"),
    )

    state = fake_orchestrator._session_state_store.get("alpha")
    assert state is not None
    assert state.task_summary == "Inspect the runtime"
    assert state.plan_snapshot["willAttemptToolLoop"] is False
    assert state.relevant_artifact_ids

    artifacts = fake_orchestrator._artifact_store.list_for_session("alpha")
    assert len(artifacts) == 1
    assert artifacts[0].type == "answer"
    assert artifacts[0].body == "hello"


@pytest.mark.asyncio
async def test_send_chat_can_continue_repo_exploration_after_first_read(tmp_path) -> None:
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
    final_event = events[-1]
    assert final_event["state"] == "final"
    assert final_event["toolExecution"]["toolId"] == "files.read"
    assert "README" in final_event["message"]["content"]
    history = orchestrator.history("alpha")
    assert history[-1]["toolExecution"]["toolId"] == "files.read"


@pytest.mark.asyncio
async def test_debug_copy_session_clones_history_state_and_artifacts(fake_orchestrator: Orchestrator) -> None:
    await _collect_events(
        fake_orchestrator,
        ChatSendRequest(session_key="alpha", message="Inspect the runtime", provider="fake", model="model-a"),
    )

    copied = fake_orchestrator.debug_copy_session("alpha")

    assert copied["key"] != "alpha"
    assert copied["provider"] == "fake"
    assert copied["model"] == "model-a"
    assert copied["providerSessionId"] is None
    assert copied["debugCopy"]["sourceSessionKey"] == "alpha"

    copied_history = fake_orchestrator.history(copied["key"])
    assert [row["role"] for row in copied_history] == ["user", "assistant"]

    copied_state = fake_orchestrator._session_state_store.get(copied["key"])
    assert copied_state is not None
    assert copied_state.task_summary == "Inspect the runtime"
    assert copied_state.relevant_artifact_ids

    copied_artifacts = fake_orchestrator._artifact_store.list_for_session(copied["key"])
    assert copied_artifacts
    assert copied_artifacts[0].metadata["clonedFromArtifactId"]
    copied_runs = fake_orchestrator.list_session_runs(copied["key"])
    assert copied_runs
    assert copied_runs[0]["userMessage"] == "Inspect the runtime"
    assert copied["debugCopy"]["copiedRuns"] == 1


@pytest.mark.asyncio
async def test_export_session_returns_messages_and_markdown(fake_orchestrator: Orchestrator) -> None:
    await _collect_events(
        fake_orchestrator,
        ChatSendRequest(session_key="alpha", message="Inspect the runtime", provider="fake", model="model-a"),
    )

    exported = fake_orchestrator.export_session("alpha")

    assert exported["session"]["key"] == "alpha"
    assert len(exported["messages"]) == 2
    assert "# Conversation Export: alpha" in exported["markdown"]
    assert "Inspect the runtime" in exported["markdown"]
    assert "hello" in exported["markdown"]
