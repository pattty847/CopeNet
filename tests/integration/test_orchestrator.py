import asyncio

import pytest

from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.sessions import SessionStore, TranscriptMessage, TranscriptStore
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


class MergeSummaryProvider:
    name = "merge"
    display_name = "Merge"

    def __init__(self, summaries: dict[str, str], *, failing_sources: set[str] | None = None) -> None:
        self.summaries = summaries
        self.failing_sources = set(failing_sources or set())
        self.prompts: list[str] = []

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        self.prompts.append(prompt)
        source_key = ""
        for line in prompt.splitlines():
          if line.startswith("Source session key:"):
              source_key = line.split(":", 1)[1].strip()
              break
        if source_key in self.failing_sources:
            raise RuntimeError(f"summary failed for {source_key}")
        text = self.summaries.get(source_key, f"Summary for {source_key or 'unknown source'}")
        yield ProviderEvent(kind="delta", text=text, provider_session_id=provider_session_id or "merge-session")
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


class PulseSummaryProvider:
    name = "pulse"
    display_name = "Pulse"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        self.prompts.append(prompt)
        source_key = "unknown"
        for line in prompt.splitlines():
            if line.startswith("Source session key:"):
                source_key = line.split(":", 1)[1].strip()
                break
        if "Create a CopeNet Pulse" in prompt:
            yield ProviderEvent(
                kind="delta",
                text=(
                    f"Title: Pulse for {source_key}\n"
                    f"Summary: Compact summary for {source_key}.\n"
                    f"Why now: This thread looks worth revisiting."
                ),
                provider_session_id=provider_session_id or "pulse-session",
            )
            yield ProviderEvent(kind="final")
            return
        yield ProviderEvent(kind="delta", text=f"Summary for {source_key}", provider_session_id=provider_session_id or "pulse-session")
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



class PersonalSummaryProvider:
    name = "personal"
    display_name = "Personal"

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        yield ProviderEvent(
            kind="delta",
            text=(
                "Key decisions:\n"
                "- Start with the customer update.\n"
                "- Keep the plan to three steps.\n\n"
                "Open questions:\n"
                "- Who needs to review the note?"
            ),
            provider_session_id=provider_session_id or "personal-session",
        )
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


@pytest.mark.asyncio
async def test_send_chat_enriches_personal_history_state(tmp_path) -> None:
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={"personal": PersonalSummaryProvider()},
    )
    orchestrator.create_session_with_profile(
        provider="personal",
        model="personal-model",
        key="alpha",
        title="Personal Alpha",
        starter_intent="plan_my_next_steps",
    )

    await _collect_events(
        orchestrator,
        ChatSendRequest(
            session_key="alpha",
            message="How should I sequence the launch tasks for next week?",
            provider="personal",
            model="personal-model",
        ),
    )

    state = orchestrator._session_state_store.get("alpha")
    assert state is not None
    assert state.starter_intent == "plan_my_next_steps"
    assert state.topical_tags == ["planning", "execution"]
    assert state.goals == ["How should I sequence the launch tasks for next week?"]
    assert "How should I sequence the launch tasks for next week?" in state.unresolved_questions
    assert "Who needs to review the note?" in state.unresolved_questions
    assert state.prior_decisions[:2] == [
        "Start with the customer update.",
        "Keep the plan to three steps.",
    ]


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
async def test_send_chat_emits_live_tool_lifecycle_events(tmp_path) -> None:
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={
            "prompted": ScriptedPromptedProvider(
                outputs=[
                    '{"tool_id":"files.read","arguments":{"path":"README.md"}}',
                    "I used the README.",
                ]
            )
        },
    )

    result, events = await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="Read the README", provider="prompted"),
    )

    assert result["status"] == "ok"
    assert [event["state"] for event in events] == ["tool_called", "tool_result", "delta", "final"]
    assert events[0]["toolCall"]["toolId"] == "files.read"
    assert events[0]["toolCall"]["arguments"] == {"path": "README.md"}
    assert events[1]["toolExecution"]["toolId"] == "files.read"
    assert events[1]["toolExecution"]["ok"] is True
    assert events[2]["message"]["parts"][0]["kind"] == "tool_call"
    assert events[2]["message"]["parts"][1]["kind"] == "tool_result"
    assert events[2]["message"]["parts"][2]["kind"] == "text"


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


@pytest.mark.asyncio
async def test_merge_sessions_creates_session_tracks_progress_and_writes_merge_brief(tmp_path) -> None:
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={
            "fake": FakeProvider(),
            "merge": MergeSummaryProvider(
                {
                    "alpha": "Alpha summary with decision A and open question A.",
                    "beta": "Beta summary with decision B and open question B.",
                }
            ),
        },
    )

    await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="Inspect alpha", provider="fake", model="model-a"),
    )
    await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="beta", message="Inspect beta", provider="fake", model="model-a"),
    )

    side_events: list[tuple[str, dict]] = []

    async def emit_side(event: str, payload: dict) -> None:
        side_events.append((event, payload))

    created = await orchestrator.merge_sessions(
        source_session_keys=["alpha", "beta"],
        provider="merge",
        model="merge-model",
        system_prompt_id="default",
        task_prompt_id="none",
        workspace_root=str(tmp_path),
        title="Merged Workspace",
        emit_event=emit_side,
    )

    merged_key = created["session"]["key"]
    initial_state = created["mergeState"]
    assert created["session"]["title"] == "Merged Workspace"
    assert initial_state["status"] in {"pending", "running"}
    assert initial_state["totalSources"] == 2
    assert initial_state["completedSources"] == 0

    await asyncio.wait_for(asyncio.gather(*list(orchestrator._background_tasks)), timeout=1.0)

    record = orchestrator._session_state_store.get(merged_key)
    assert record is not None
    assert record.merge_state is not None
    assert record.merge_state["status"] == "complete"
    assert record.merge_state["completed_sources"] == 2
    assert len(record.merge_state["sources"]) == 2
    assert {source["session_key"] for source in record.merge_state["sources"]} == {"alpha", "beta"}

    history = orchestrator.history(merged_key)
    assert [row["role"] for row in history] == ["assistant"]
    assert "Merged context prepared from 2 sessions." in history[0]["content"]
    assert "Alpha summary with decision A" in history[0]["content"]
    assert "Beta summary with decision B" in history[0]["content"]

    artifacts = orchestrator._artifact_store.list_for_session(merged_key)
    assert artifacts
    assert artifacts[0].type == "merge_brief"
    assert "Merged context prepared from 2 sessions." in artifacts[0].body

    merge_updates = [payload for event, payload in side_events if event == "sessions.merge.updated"]
    assert merge_updates
    assert merge_updates[-1]["mergeState"]["status"] == "complete"
    assert merge_updates[-1]["message"]["content"].startswith("Merged context prepared")


@pytest.mark.asyncio
async def test_merge_sessions_surfaces_partial_failure_and_stays_usable(tmp_path) -> None:
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={
            "fake": FakeProvider(),
            "merge": MergeSummaryProvider(
                {"alpha": "Alpha summary is available."},
                failing_sources={"beta"},
            ),
        },
    )

    await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="Inspect alpha", provider="fake", model="model-a"),
    )
    await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="beta", message="Inspect beta", provider="fake", model="model-a"),
    )

    created = await orchestrator.merge_sessions(
        source_session_keys=["alpha", "beta"],
        provider="merge",
        model="merge-model",
        system_prompt_id="default",
        task_prompt_id="none",
        workspace_root=str(tmp_path),
    )
    merged_key = created["session"]["key"]

    await asyncio.wait_for(asyncio.gather(*list(orchestrator._background_tasks)), timeout=1.0)

    record = orchestrator._session_state_store.get(merged_key)
    assert record is not None
    assert record.merge_state is not None
    assert record.merge_state["status"] == "failed"
    assert record.merge_state["completed_sources"] == 1
    assert any(source["status"] == "failed" for source in record.merge_state["sources"])

    history = orchestrator.history(merged_key)
    assert [row["role"] for row in history] == ["assistant"]
    assert "Alpha summary is available." in history[0]["content"]
    assert "beta" in history[0]["content"].lower()


@pytest.mark.asyncio
async def test_create_pulse_from_session_persists_record_and_uses_summary_provider(tmp_path) -> None:
    provider = PulseSummaryProvider()
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={"pulse": provider},
    )
    session = orchestrator.create_session_with_profile(provider="pulse", model="pulse-model", key="alpha", title="Alpha Session")
    orchestrator._transcript_store.append_message(
        session["sessionId"],
        TranscriptMessage(
            run_id="run-1",
            role="assistant",
            content="We should revisit the provider contract after the current pass.",
            provider="pulse",
            model="pulse-model",
            provider_session_id=None,
            timestamp="2026-05-07T00:00:00+00:00",
            state="final",
        ),
    )
    state = orchestrator._session_state_store.get_or_create("alpha")
    state.task_summary = "Review provider drift"
    state.unresolved_questions = ["Should Pulse reuse merge summaries?"]
    orchestrator._session_state_store.save(state)

    pulse = await orchestrator.create_pulse_from_session(
        session_key="alpha",
        provider="pulse",
        model="pulse-model",
        system_prompt_id="default",
        task_prompt_id="none",
    )

    assert pulse["title"] == "Pulse for alpha"
    assert pulse["status"] == "new"
    assert pulse["sourceSessionKeys"] == ["alpha"]
    listed = orchestrator.list_pulses()
    assert listed[0]["pulseId"] == pulse["pulseId"]
    assert any("Create a CopeNet Pulse" in prompt for prompt in provider.prompts)


@pytest.mark.asyncio
async def test_save_pulses_creates_single_session_and_multi_merge(tmp_path) -> None:
    provider = PulseSummaryProvider()
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={"pulse": provider},
    )
    alpha = orchestrator.create_session_with_profile(provider="pulse", model="pulse-model", key="alpha", title="Alpha Session")
    beta = orchestrator.create_session_with_profile(provider="pulse", model="pulse-model", key="beta", title="Beta Session")
    for session in (alpha, beta):
        orchestrator._transcript_store.append_message(
            session["sessionId"],
            TranscriptMessage(
                run_id=f"run-{session['key']}",
                role="assistant",
                content=f"Session content for {session['key']}",
                provider="pulse",
                model="pulse-model",
                provider_session_id=None,
                timestamp="2026-05-07T00:00:00+00:00",
                state="final",
            ),
        )

    pulse_one = await orchestrator.create_pulse_from_session(
        session_key="alpha",
        provider="pulse",
        model="pulse-model",
        system_prompt_id="default",
        task_prompt_id="none",
    )
    pulse_two = await orchestrator.create_pulse_from_session(
        session_key="beta",
        provider="pulse",
        model="pulse-model",
        system_prompt_id="default",
        task_prompt_id="none",
    )

    single = await orchestrator.save_pulses(
        pulse_ids=[pulse_one["pulseId"]],
        provider="pulse",
        model="pulse-model",
        system_prompt_id="default",
        task_prompt_id="none",
        workspace_root=None,
    )
    assert single["session"]["title"].startswith("Pulse — ")
    single_history = orchestrator.history(single["session"]["key"])
    assert any("Pulse saved from 1 source session." in str(item.get("content") or "") for item in single_history)

    multi = await orchestrator.save_pulses(
        pulse_ids=[pulse_one["pulseId"], pulse_two["pulseId"]],
        provider="pulse",
        model="pulse-model",
        system_prompt_id="default",
        task_prompt_id="none",
        workspace_root=None,
    )
    await asyncio.wait_for(asyncio.gather(*list(orchestrator._background_tasks)), timeout=1.0)

    assert multi["mergeState"] is not None
    assert multi["session"]["title"].startswith("Pulse Workspace")
    assert orchestrator.list_pulses() == []
