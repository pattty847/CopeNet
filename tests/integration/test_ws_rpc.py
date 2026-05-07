from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.host.api import create_app
from copenet.providers import ProviderEvent, ProviderModel


class FakeProvider:
    def __init__(
        self,
        *,
        name: str = "fake",
        display_name: str = "Fake",
        wait_for_abort: bool = False,
        response_text: str = "hello from fake provider",
    ) -> None:
        self.name = name
        self.display_name = display_name
        self.wait_for_abort = wait_for_abort
        self.response_text = response_text

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
        yield ProviderEvent(kind="delta", text=self.response_text, provider_session_id=provider_session_id or "fake-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict[str, Any]:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False},
        }

    async def list_models(self) -> list[ProviderModel]:
        return [
            ProviderModel(
                id="model-a",
                display_name="Model A",
                provider=self.name,
                description="Primary test model",
                capabilities={"chat": True},
            )
        ]


class PromptedToolProvider:
    def __init__(self, *, name: str, display_name: str, tool_json: str, follow_up: str) -> None:
        self.name = name
        self.display_name = display_name
        self.tool_json = tool_json
        self.follow_up = follow_up
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
        if len(self.prompts) == 1:
            yield ProviderEvent(kind="delta", text=self.tool_json, provider_session_id=provider_session_id or f"{self.name}-session")
            yield ProviderEvent(kind="final")
            return
        yield ProviderEvent(kind="delta", text=self.follow_up, provider_session_id=provider_session_id or f"{self.name}-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict[str, Any]:
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

    async def list_models(self) -> list[ProviderModel]:
        return [
            ProviderModel(
                id="tool-model",
                display_name="Tool Model",
                provider=self.name,
                description="Prompted tool-use test model",
                capabilities={"chat": True},
            )
        ]


class MergeSummaryProvider:
    def __init__(self, *, name: str = "merge", display_name: str = "Merge") -> None:
        self.name = name
        self.display_name = display_name

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        source_key = "unknown"
        for line in prompt.splitlines():
            if line.startswith("Source session key:"):
                source_key = line.split(":", 1)[1].strip()
                break
        yield ProviderEvent(kind="delta", text=f"Summary for {source_key}", provider_session_id=provider_session_id or "merge-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict[str, Any]:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False},
        }

    async def list_models(self) -> list[ProviderModel]:
        return [
            ProviderModel(
                id="merge-model",
                display_name="Merge Model",
                provider=self.name,
                description="Merge summary test model",
                capabilities={"chat": True},
            )
        ]


class RpcSocket:
    def __init__(self, websocket) -> None:
        self._websocket = websocket
        self._buffer: list[dict[str, Any]] = []
        self._request_counter = 0

    def _take_buffered(self, predicate) -> dict[str, Any] | None:
        for index, frame in enumerate(self._buffer):
            if predicate(frame):
                return self._buffer.pop(index)
        return None

    def _next_matching(self, predicate) -> dict[str, Any]:
        buffered = self._take_buffered(predicate)
        if buffered is not None:
            return buffered
        while True:
            frame = self._websocket.receive_json()
            if predicate(frame):
                return frame
            self._buffer.append(frame)

    def recv_challenge(self) -> dict[str, Any]:
        return self._next_matching(lambda frame: frame.get("type") == "event" and frame.get("event") == "connect.challenge")

    def request(self, method: str, params: dict[str, Any] | None = None, request_id: str | None = None) -> str:
        self._request_counter += 1
        actual_id = request_id or f"req-{self._request_counter}"
        payload: dict[str, Any] = {"type": "req", "id": actual_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._websocket.send_json(payload)
        return actual_id

    def recv_response(self, request_id: str) -> dict[str, Any]:
        return self._next_matching(lambda frame: frame.get("type") == "res" and frame.get("id") == request_id)

    def connect(self, token: str = "test-token") -> dict[str, Any]:
        request_id = self.request("connect", {"auth": {"token": token}}, request_id="connect-1")
        return self.recv_response(request_id)

    def recv_chat_until_terminal(
        self,
        *,
        session_key: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        def matches(frame: dict[str, Any]) -> bool:
            if frame.get("type") != "event" or frame.get("event") != "chat":
                return False
            payload = frame.get("payload") or {}
            if session_key and payload.get("sessionKey") != session_key:
                return False
            if run_id and payload.get("runId") != run_id:
                return False
            return True

        events: list[dict[str, Any]] = []
        while True:
            frame = self._next_matching(matches)
            events.append(frame)
            state = ((frame.get("payload") or {}).get("state") or "").strip()
            if state in {"final", "error", "aborted"}:
                return events


@pytest.fixture
def rpc_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("COPNET_TOKEN", "test-token")
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    outside_root = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_root.mkdir(exist_ok=True)

    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={
            "fake": FakeProvider(),
            "blocking": FakeProvider(name="blocking", display_name="Blocking", wait_for_abort=True),
            "merge": MergeSummaryProvider(),
            "prompted-success": PromptedToolProvider(
                name="prompted-success",
                display_name="Prompted Success",
                tool_json='{"tool_id":"files.read","arguments":{"path":"README.md"}}',
                follow_up="Used the README contents to answer.",
            ),
            "prompted-blocked": PromptedToolProvider(
                name="prompted-blocked",
                display_name="Prompted Blocked",
                tool_json=f'{{"tool_id":"files.list","arguments":{{"path":"{outside_root}"}}}}',
                follow_up="I inspected a directory outside the home workspace and marked it clearly.",
            ),
        },
    )

    app = create_app(orchestrator=orchestrator)
    with TestClient(app) as client:
        yield client


@contextmanager
def _open_rpc(client: TestClient, token: str = "test-token"):
    with client.websocket_connect("/ws") as websocket:
        socket = RpcSocket(websocket)
        challenge = socket.recv_challenge()
        assert challenge["payload"]["nonce"]
        response = socket.connect(token=token)
        assert response["ok"] is True
        assert response["payload"]["type"] == "hello-ok"
        yield socket


def test_connect_handshake_requires_valid_token(rpc_client: TestClient) -> None:
    with rpc_client.websocket_connect("/ws") as websocket:
        socket = RpcSocket(websocket)
        challenge = socket.recv_challenge()
        assert challenge["type"] == "event"
        assert challenge["event"] == "connect.challenge"
        assert challenge["payload"]["nonce"]

        response = socket.connect()
        assert response["ok"] is True
        assert "chat.send" in response["payload"]["features"]["methods"]
        assert "sessions.merge.create" in response["payload"]["features"]["methods"]
        assert "sessions.merge.state" in response["payload"]["features"]["methods"]
        assert "sessions.runs" in response["payload"]["features"]["methods"]
        assert "sessions.run" in response["payload"]["features"]["methods"]
        assert "sessions.state" in response["payload"]["features"]["methods"]
        assert "messaging.config.get" in response["payload"]["features"]["methods"]
        assert "messaging.config.update" in response["payload"]["features"]["methods"]
        assert "messaging.test" in response["payload"]["features"]["methods"]
        assert "chat" in response["payload"]["features"]["events"]
        assert "sessions.merge.updated" in response["payload"]["features"]["events"]
        assert "messaging.updated" in response["payload"]["features"]["events"]

    with rpc_client.websocket_connect("/ws") as websocket:
        socket = RpcSocket(websocket)
        socket.recv_challenge()
        failure = socket.connect(token="wrong-token")
        assert failure["ok"] is False
        assert failure["error"]["code"] == "UNAUTHORIZED"
        assert failure["error"]["message"] == "invalid token"


def test_catalog_and_session_rpcs_expose_public_shapes(rpc_client: TestClient, tmp_path: Path) -> None:
    with _open_rpc(rpc_client) as socket:
        messaging_id = socket.request("messaging.config.get")
        messaging = socket.recv_response(messaging_id)
        assert messaging["payload"]["config"] == {
            "telegram": None,
            "destinations": [],
            "approvalPolicy": {
                "requireApprovalByDefault": True,
                "hardlineBlocklist": [],
            },
        }

        providers_id = socket.request("providers.list")
        providers = socket.recv_response(providers_id)
        provider_rows = providers["payload"]["providers"]
        assert {row["id"] for row in provider_rows} >= {"fake", "blocking", "prompted-success", "prompted-blocked"}

        models_id = socket.request("models.list", {"provider": "fake"})
        models = socket.recv_response(models_id)
        assert models["payload"]["models"] == [
            {
                "id": "model-a",
                "displayName": "Model A",
                "provider": "fake",
                "description": "Primary test model",
                "kind": "chat",
                "capabilities": {"chat": True},
                "recommendedFor": [],
                "metadata": {},
            }
        ]

        tools_id = socket.request("tools.list")
        tools = socket.recv_response(tools_id)
        tool_rows = tools["payload"]["tools"]
        assert {tool["id"] for tool in tool_rows} == {
            "context.prepare",
            "files.list",
            "files.read",
            "files.rg",
            "files.search",
            "git.diff",
            "git.status",
            "shell.exec",
        }
        assert {"id", "name", "description", "category", "inputSchema", "safetyLevel", "capabilities"} <= set(tool_rows[0])

        sessions_id = socket.request("sessions.list")
        sessions = socket.recv_response(sessions_id)
        assert sessions["payload"]["sessions"] == []

        runtime_context_id = socket.request("runtime.context")
        runtime_context = socket.recv_response(runtime_context_id)
        assert runtime_context["payload"]["runtimeContext"]["workspaceRoot"] == str(tmp_path)
        assert runtime_context["payload"]["runtimeContext"]["fileToolScope"] == "workspace_home_visible_roaming"

        set_workspace_id = socket.request("runtime.workspace.set", {"workspaceRoot": str(tmp_path)})
        set_workspace_response = socket.recv_response(set_workspace_id)
        assert set_workspace_response["payload"]["workspaceRoot"] == str(tmp_path)

        create_id = socket.request(
            "sessions.create",
            {
                "provider": "fake",
                "model": "model-a",
                "key": "alpha",
                "title": "Alpha Session",
                "systemPromptId": "default",
                "taskPromptId": "general",
                "workspaceRoot": str(tmp_path),
            },
        )
        create_response = socket.recv_response(create_id)
        session = create_response["payload"]["session"]
        assert session["key"] == "alpha"
        assert session["provider"] == "fake"
        assert session["model"] == "model-a"
        assert session["systemPromptId"] == "default"
        assert session["taskPromptId"] == "general"
        assert session["workspaceRoot"] == str(tmp_path)
        assert session["archived"] is False

        resolve_id = socket.request("sessions.resolve", {"key": "alpha"})
        resolve_response = socket.recv_response(resolve_id)
        assert resolve_response["payload"]["session"]["key"] == "alpha"

        history_id = socket.request("chat.history", {"sessionKey": "alpha"})
        history_response = socket.recv_response(history_id)
        assert history_response["payload"] == {"sessionKey": "alpha", "messages": []}

        archive_id = socket.request("sessions.archive", {"key": "alpha", "archived": True})
        archive_response = socket.recv_response(archive_id)
        assert archive_response["payload"]["session"]["archived"] is True

        debug_copy_id = socket.request("sessions.debugCopy", {"key": "alpha"})
        debug_copy_response = socket.recv_response(debug_copy_id)
        copied_session = debug_copy_response["payload"]["session"]
        assert copied_session["key"] != "alpha"
        assert copied_session["debugCopy"]["sourceSessionKey"] == "alpha"

        export_id = socket.request("sessions.export", {"key": "alpha"})
        export_response = socket.recv_response(export_id)
        assert export_response["payload"]["session"]["key"] == "alpha"
        assert export_response["payload"]["messages"] == []
        assert "# Conversation Export: Alpha Session" in export_response["payload"]["markdown"]

        active_list_id = socket.request("sessions.list")
        active_list = socket.recv_response(active_list_id)
        assert [row["key"] for row in active_list["payload"]["sessions"]] == [copied_session["key"]]

        archived_list_id = socket.request("sessions.list", {"includeArchived": True})
        archived_list = socket.recv_response(archived_list_id)
        assert {row["key"] for row in archived_list["payload"]["sessions"]} == {"alpha", copied_session["key"]}
        alpha_row = next(row for row in archived_list["payload"]["sessions"] if row["key"] == "alpha")
        assert alpha_row["archived"] is True


def test_messaging_rpcs_update_policy_and_emit_live_status(rpc_client: TestClient) -> None:
    with _open_rpc(rpc_client) as socket:
        update_id = socket.request(
            "messaging.config.update",
            {
                "approvalPolicy": {
                    "requireApprovalByDefault": False,
                    "hardlineBlocklist": ["telegram:@blocked"],
                }
            },
        )
        update_response = socket.recv_response(update_id)
        assert update_response["payload"]["config"]["approvalPolicy"] == {
            "requireApprovalByDefault": False,
            "hardlineBlocklist": ["telegram:@blocked"],
        }

        update_event = socket._next_matching(
            lambda candidate: candidate.get("type") == "event" and candidate.get("event") == "messaging.updated"
        )
        assert update_event["payload"]["config"]["approvalPolicy"]["requireApprovalByDefault"] is False

        test_id = socket.request("messaging.test", {"platform": "telegram"})
        test_response = socket.recv_response(test_id)
        assert test_response["payload"]["platform"] == "telegram"
        assert test_response["payload"]["config"]["telegram"] is None
        assert test_response["payload"]["result"]["ok"] is False
        assert test_response["payload"]["result"]["connectionStatus"] == "unconfigured"


def test_chat_send_streams_history_and_locked_binding_errors(rpc_client: TestClient) -> None:
    with _open_rpc(rpc_client) as socket:
        create_id = socket.request(
            "sessions.create",
            {
                "provider": "fake",
                "model": "model-a",
                "key": "alpha",
                "systemPromptId": "default",
                "taskPromptId": "general",
            },
        )
        socket.recv_response(create_id)

        send_id = socket.request(
            "chat.send",
            {
                "sessionKey": "alpha",
                "message": "Hello there",
                "provider": "fake",
                "model": "model-a",
                "systemPromptId": "default",
                "taskPromptId": "general",
            },
        )
        started = socket.recv_response(send_id)
        assert started["payload"]["status"] == "started"

        events = socket.recv_chat_until_terminal(session_key="alpha", run_id=started["payload"]["runId"])
        assert [frame["payload"]["state"] for frame in events] == ["delta", "final"]
        final_payload = events[-1]["payload"]
        assert final_payload["message"]["role"] == "assistant"
        assert final_payload["message"]["content"] == "hello from fake provider"

        history_id = socket.request("chat.history", {"sessionKey": "alpha"})
        history_response = socket.recv_response(history_id)
        messages = history_response["payload"]["messages"]
        assert [message["role"] for message in messages] == ["user", "assistant"]
        assert messages[-1]["content"] == "hello from fake provider"

        mismatch_id = socket.request(
            "chat.send",
            {
                "sessionKey": "alpha",
                "message": "Try a different model",
                "provider": "fake",
                "model": "model-b",
                "systemPromptId": "default",
                "taskPromptId": "general",
            },
        )
        mismatch_started = socket.recv_response(mismatch_id)
        mismatch_events = socket.recv_chat_until_terminal(session_key="alpha", run_id=mismatch_started["payload"]["runId"])
        assert mismatch_events[-1]["payload"]["state"] == "error"
        assert "locked to model" in mismatch_events[-1]["payload"]["errorMessage"]


def test_chat_abort_returns_run_id_and_final_event(rpc_client: TestClient) -> None:
    with _open_rpc(rpc_client) as socket:
        send_id = socket.request(
            "chat.send",
            {
                "sessionKey": "abort-me",
                "message": "Wait for abort",
                "provider": "blocking",
            },
        )
        started = socket.recv_response(send_id)
        run_id = started["payload"]["runId"]

        abort_id = socket.request("chat.abort", {"sessionKey": "abort-me"})
        abort_response = socket.recv_response(abort_id)
        assert abort_response["payload"] == {"ok": True, "aborted": True, "runIds": [run_id]}

        events = socket.recv_chat_until_terminal(session_key="abort-me", run_id=run_id)
        assert events[-1]["payload"]["state"] == "final"
        assert events[-1]["payload"]["message"] is None


def test_chat_transport_exposes_tool_execution_shapes(rpc_client: TestClient, tmp_path: Path) -> None:
    with _open_rpc(rpc_client) as socket:
        success_id = socket.request(
            "chat.send",
            {
                "sessionKey": "tool-success",
                "message": "Read the README",
                "provider": "prompted-success",
            },
        )
        success_started = socket.recv_response(success_id)
        success_events = socket.recv_chat_until_terminal(
            session_key="tool-success",
            run_id=success_started["payload"]["runId"],
        )
        success_final = success_events[-1]["payload"]
        assert [event["payload"]["state"] for event in success_events] == ["tool_called", "tool_result", "delta", "final"]
        assert success_events[0]["payload"]["toolCall"]["toolId"] == "files.read"
        assert success_events[0]["payload"]["toolCall"]["arguments"] == {"path": "README.md"}
        assert success_events[1]["payload"]["toolExecution"]["toolId"] == "files.read"
        assert success_final["toolExecution"]["toolId"] == "files.read"
        assert success_final["toolExecution"]["ok"] is True
        assert success_final["toolExecution"]["summary"] == "Read file README.md."
        assert {
            event["payload"]["toolExecution"]["toolId"]
            for event in success_events
            if event["payload"].get("toolExecution")
        } == {"files.read"}

        success_history_id = socket.request("chat.history", {"sessionKey": "tool-success"})
        success_history = socket.recv_response(success_history_id)
        assert success_history["payload"]["messages"][-1]["toolExecution"]["toolId"] == "files.read"

        blocked_id = socket.request(
            "chat.send",
            {
                "sessionKey": "tool-blocked",
                "message": "Inspect the desktop",
                "provider": "prompted-blocked",
            },
        )
        blocked_started = socket.recv_response(blocked_id)
        blocked_events = socket.recv_chat_until_terminal(
            session_key="tool-blocked",
            run_id=blocked_started["payload"]["runId"],
        )
        blocked_final = blocked_events[-1]["payload"]
        assert blocked_events[0]["payload"]["state"] == "tool_called"
        assert blocked_events[1]["payload"]["state"] == "tool_result"
        assert blocked_final["toolExecution"]["toolId"] == "files.list"
        assert blocked_final["toolExecution"]["ok"] is True
        assert blocked_final["toolExecution"]["scope"] == "outside_workspace"
        assert blocked_final["toolExecution"]["workspaceRoot"] == str(tmp_path)


def test_session_run_rpcs_expose_durable_run_records(rpc_client: TestClient, tmp_path: Path) -> None:
    with _open_rpc(rpc_client) as socket:
        send_id = socket.request(
            "chat.send",
            {
                "sessionKey": "tool-success",
                "message": "Read the README",
                "provider": "prompted-success",
            },
        )
        started = socket.recv_response(send_id)
        run_id = started["payload"]["runId"]
        socket.recv_chat_until_terminal(session_key="tool-success", run_id=run_id)

        runs_id = socket.request("sessions.runs", {"key": "tool-success"})
        runs_response = socket.recv_response(runs_id)
        runs = runs_response["payload"]["runs"]
        assert len(runs) == 1
        assert runs[0]["runId"] == run_id
        assert runs[0]["status"] == "ok"
        assert runs[0]["artifactIds"]
        assert runs[0]["toolSteps"][0]["toolId"] == "files.read"
        assert runs[0]["toolSteps"][0]["scope"] == "inside_workspace"
        assert runs[0]["metadata"]["workspaceRoot"] == str(tmp_path)

        run_detail_id = socket.request("sessions.run", {"key": "tool-success", "runId": run_id})
        run_detail = socket.recv_response(run_detail_id)
        assert run_detail["payload"]["run"]["runId"] == run_id
        assert run_detail["payload"]["run"]["toolSteps"][0]["summary"] == "Read file README.md."


def test_session_state_rpc_exposes_runtime_state(rpc_client: TestClient) -> None:
    with _open_rpc(rpc_client) as socket:
        send_id = socket.request(
            "chat.send",
            {
                "sessionKey": "tool-success",
                "message": "Read the README",
                "provider": "prompted-success",
            },
        )
        started = socket.recv_response(send_id)
        socket.recv_chat_until_terminal(session_key="tool-success", run_id=started["payload"]["runId"])

        state_id = socket.request("sessions.state", {"key": "tool-success"})
        state_response = socket.recv_response(state_id)
        state = state_response["payload"]["state"]
        assert state["session_key"] == "tool-success"
        assert state["task_summary"] == "Read the README"


def test_sessions_create_can_seed_personal_starter_intent(rpc_client: TestClient, tmp_path: Path) -> None:
    with _open_rpc(rpc_client) as socket:
        create_id = socket.request(
            "sessions.create",
            {
                "provider": "fake",
                "model": "model-a",
                "key": "personal-alpha",
                "title": "Personal Alpha",
                "workspaceRoot": str(tmp_path),
                "starterIntentId": "plan_my_next_steps",
            },
        )
        socket.recv_response(create_id)

        state_id = socket.request("sessions.state", {"key": "personal-alpha"})
        state_response = socket.recv_response(state_id)
        state = state_response["payload"]["state"]
        assert state["starter_intent"] == "plan_my_next_steps"
        assert state["topical_tags"] == ["planning", "execution"]


def test_sessions_merge_create_opens_session_and_emits_progress(rpc_client: TestClient, tmp_path: Path) -> None:
    with _open_rpc(rpc_client) as socket:
        for key in ("alpha", "beta"):
            send_id = socket.request(
                "chat.send",
                {
                    "sessionKey": key,
                    "message": f"Inspect {key}",
                    "provider": "fake",
                    "model": "model-a",
                },
            )
            started = socket.recv_response(send_id)
            socket.recv_chat_until_terminal(session_key=key, run_id=started["payload"]["runId"])

        merge_id = socket.request(
            "sessions.merge.create",
            {
                "sourceSessionKeys": ["alpha", "beta"],
                "provider": "merge",
                "model": "merge-model",
                "systemPromptId": "default",
                "taskPromptId": "none",
                "workspaceRoot": str(tmp_path),
                "title": "Merged Alpha Beta",
            },
        )
        merge_res = socket.recv_response(merge_id)
        merged_session = merge_res["payload"]["session"]
        assert merged_session["title"] == "Merged Alpha Beta"
        assert merge_res["payload"]["mergeState"]["totalSources"] == 2

        updates: list[dict[str, Any]] = []
        while True:
            frame = socket._next_matching(
                lambda candidate: candidate.get("type") == "event"
                and candidate.get("event") == "sessions.merge.updated"
                and (candidate.get("payload") or {}).get("sessionKey") == merged_session["key"]
            )
            updates.append(frame)
            if frame["payload"]["mergeState"]["status"] in {"complete", "failed"}:
                break

        assert updates[-1]["payload"]["mergeState"]["status"] == "complete"
        assert updates[-1]["payload"]["message"]["content"].startswith("Merged context prepared from 2 sessions.")

        history_id = socket.request("chat.history", {"sessionKey": merged_session["key"]})
        history = socket.recv_response(history_id)
        assert history["payload"]["messages"][-1]["content"].startswith("Merged context prepared from 2 sessions.")

        merge_state_id = socket.request("sessions.merge.state", {"key": merged_session["key"]})
        merge_state_res = socket.recv_response(merge_state_id)
        assert merge_state_res["payload"]["mergeState"]["completedSources"] == 2
        assert {source["sessionKey"] for source in merge_state_res["payload"]["mergeState"]["sources"]} == {"alpha", "beta"}


def test_session_artifacts_rpc_exposes_runtime_artifacts(rpc_client: TestClient) -> None:
    with _open_rpc(rpc_client) as socket:
        send_id = socket.request(
            "chat.send",
            {
                "sessionKey": "tool-success",
                "message": "Read the README",
                "provider": "prompted-success",
            },
        )
        started = socket.recv_response(send_id)
        socket.recv_chat_until_terminal(session_key="tool-success", run_id=started["payload"]["runId"])

        artifacts_id = socket.request("sessions.artifacts", {"key": "tool-success"})
        artifacts_response = socket.recv_response(artifacts_id)
        artifacts = artifacts_response["payload"]["artifacts"]
        assert artifacts
        assert all(row["sessionKey"] == "tool-success" for row in artifacts)
        assert all(row["artifactId"] for row in artifacts)
        assert {row["type"] for row in artifacts} >= {"answer"}


def test_profile_rpcs_return_profile_changelog_and_briefing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_TOKEN", "test-token")
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    monkeypatch.setenv("COPNET_DATA_DIR", str(tmp_path / "data"))

    profile_dir = tmp_path / "data" / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "identity.json").write_text(
        json.dumps(
            {
                "profileId": "pat-profile:patrick",
                "displayName": "Patrick Cope",
                "configured": True,
                "priorities": [{"id": "school", "label": "School", "weight": 1.0}],
                "goals": [{"id": "ship", "text": "Ship CopeNet", "source": "explicit", "updatedAt": "2026-04-30T00:00:00Z"}],
                "tonePreference": {"directness": "terse", "formality": "casual", "preferBullets": True},
                "noiseFilters": ["ignore china crypto bans unless price moves materially"],
                "scheduleBasics": ["Homework due tonight"],
                "recurringConstraints": ["School first when deadlines are imminent"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (profile_dir / "observed_tendencies.json").write_text("[]\n", encoding="utf-8")
    (profile_dir / "guidance_rules.json").write_text("[]\n", encoding="utf-8")
    (profile_dir / "notes.md").write_text("# Notes\n\nReal overlay.\n", encoding="utf-8")
    (profile_dir / "changelog.jsonl").write_text(
        json.dumps(
            {
                "id": "chg-1",
                "kind": "tone_updated",
                "summary": "Updated tone preference to lead with the punchline.",
                "source": "explicit",
                "changedAt": "2026-04-30T00:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={"fake": FakeProvider()},
    )
    app = create_app(orchestrator=orchestrator)

    with TestClient(app) as client, _open_rpc(client) as socket:
        profile_id = socket.request("profile.get")
        profile_res = socket.recv_response(profile_id)
        assert profile_res["ok"] is True
        assert profile_res["payload"]["profile"]["displayName"] == "Patrick Cope"

        changelog_id = socket.request("profile.changelog")
        changelog_res = socket.recv_response(changelog_id)
        assert changelog_res["ok"] is True
        assert changelog_res["payload"]["changelog"][0]["summary"].startswith("Updated tone preference")

        briefing_id = socket.request("briefing.get")
        briefing_res = socket.recv_response(briefing_id)
        assert briefing_res["ok"] is True
        assert briefing_res["payload"]["briefing"] is not None
