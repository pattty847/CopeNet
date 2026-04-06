"""WebSocket RPC server scaffold for CopeNet."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from copenet.orchestrator import ChatSendRequest, Orchestrator, SessionInFlightError
from copenet.prompts import compose_prompt, list_profiles, list_task_modes
from copenet.host.rpc_schema import (
    ChatEventPayload,
    EventFrame,
    ResponseFrame,
    RpcError,
    make_chat_event,
    make_event_frame,
    make_response_frame,
    parse_request_frame,
)


class CopeNetWsServer:
    """Minimal CopeNet WS RPC handler."""

    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self._orchestrator = orchestrator or Orchestrator()
        self._token = os.environ.get("COPNET_TOKEN", os.environ.get("PROMPT_ANYWHERE_TOKEN", "dev-token")).strip()

    async def handle(self, websocket: WebSocket) -> None:
        """Accept and serve one websocket session."""
        await websocket.accept()
        send_lock = asyncio.Lock()
        connected = False
        nonce = str(uuid4())
        tasks: set[asyncio.Task] = set()

        async def send_json(payload: dict[str, Any]) -> None:
            async with send_lock:
                await websocket.send_json(payload)

        await send_json(make_event_frame(EventFrame(event="connect.challenge", payload={"nonce": nonce})))

        try:
            while True:
                frame_raw = await websocket.receive_json()
                if not isinstance(frame_raw, dict):
                    await send_json(
                        make_response_frame(
                            ResponseFrame(
                                id="unknown",
                                ok=False,
                                error=RpcError(code="INVALID_REQUEST", message="request frame must be an object"),
                            )
                        )
                    )
                    continue

                try:
                    req = parse_request_frame(frame_raw)
                except ValueError as exc:
                    await send_json(
                        make_response_frame(
                            ResponseFrame(
                                id=str(frame_raw.get("id") or "unknown"),
                                ok=False,
                                error=RpcError(code="INVALID_REQUEST", message=str(exc)),
                            )
                        )
                    )
                    continue

                if not connected:
                    if req.method != "connect":
                        await send_json(
                            make_response_frame(
                                ResponseFrame(
                                    id=req.id,
                                    ok=False,
                                    error=RpcError(
                                        code="UNAUTHORIZED",
                                        message="first request must be connect",
                                    ),
                                )
                            )
                        )
                        await websocket.close(code=1008)
                        return
                    connected = await self._handle_connect(req.id, req.params, send_json)
                    if not connected:
                        await websocket.close(code=1008)
                        return
                    continue

                if req.method == "chat.send":
                    await self._handle_chat_send(req.id, req.params, send_json, tasks)
                elif req.method == "chat.abort":
                    await self._handle_chat_abort(req.id, req.params, send_json)
                elif req.method == "chat.history":
                    await self._handle_chat_history(req.id, req.params, send_json)
                elif req.method == "sessions.list":
                    include_archived = bool((req.params or {}).get("includeArchived", False))
                    await send_json(
                        make_response_frame(
                            ResponseFrame(
                                id=req.id,
                                ok=True,
                                payload={"sessions": self._orchestrator.list_sessions(include_archived=include_archived)},
                            )
                        )
                    )
                elif req.method == "prompts.list":
                    await send_json(
                        make_response_frame(
                            ResponseFrame(
                                id=req.id,
                                ok=True,
                                payload={
                                    "prompts": list_profiles(),
                                    "profiles": list_profiles(),
                                    "taskModes": list_task_modes(),
                                },
                            )
                        )
                    )
                elif req.method == "providers.list":
                    await send_json(
                        make_response_frame(
                            ResponseFrame(
                                id=req.id,
                                ok=True,
                                payload={"providers": await self._orchestrator.list_providers_catalog()},
                            )
                        )
                    )
                elif req.method == "models.list":
                    provider_id = str((req.params or {}).get("provider") or "").strip() or None
                    kind = str((req.params or {}).get("kind") or "chat").strip() or "chat"
                    await send_json(
                        make_response_frame(
                            ResponseFrame(
                                id=req.id,
                                ok=True,
                                payload={"models": await self._orchestrator.list_models(provider_id=provider_id, kind=kind)},
                            )
                        )
                    )
                elif req.method == "tools.list":
                    await send_json(
                        make_response_frame(
                            ResponseFrame(
                                id=req.id,
                                ok=True,
                                payload={"tools": self._orchestrator.list_tools()},
                            )
                        )
                    )
                elif req.method == "sessions.create":
                    raw = req.params or {}
                    provider = str(raw.get("provider") or "").strip()
                    model = str(raw.get("model") or "").strip() or None
                    key = str(raw.get("key") or "").strip() or None
                    title = str(raw.get("title") or "").strip() or None
                    system_prompt_id = str(raw.get("systemPromptId") or "").strip() or None
                    task_prompt_id = str(raw.get("taskPromptId") or "").strip() or None
                    if not provider:
                        await send_json(
                            make_response_frame(
                                ResponseFrame(
                                    id=req.id,
                                    ok=False,
                                    error=RpcError(code="INVALID_REQUEST", message="provider is required"),
                                )
                            )
                        )
                        continue
                    try:
                        session = self._orchestrator.create_session_with_profile(
                            provider=provider,
                            model=model,
                            key=key,
                            title=title,
                            system_prompt_id=system_prompt_id,
                            task_prompt_id=task_prompt_id,
                        )
                    except Exception as exc:
                        await send_json(
                            make_response_frame(
                                ResponseFrame(
                                    id=req.id,
                                    ok=False,
                                    error=RpcError(code="INVALID_REQUEST", message=str(exc)),
                                )
                            )
                        )
                        continue
                    await send_json(make_response_frame(ResponseFrame(id=req.id, ok=True, payload={"session": session})))
                elif req.method == "sessions.rename":
                    raw = req.params or {}
                    key = str(raw.get("key") or "").strip()
                    if not key:
                        await send_json(
                            make_response_frame(
                                ResponseFrame(
                                    id=req.id,
                                    ok=False,
                                    error=RpcError(code="INVALID_REQUEST", message="key is required"),
                                )
                            )
                        )
                        continue
                    try:
                        session = self._orchestrator.rename_session(
                            session_key=key,
                            title=str(raw.get("title") or "").strip() or None,
                        )
                    except Exception as exc:
                        await send_json(
                            make_response_frame(
                                ResponseFrame(
                                    id=req.id,
                                    ok=False,
                                    error=RpcError(code="INVALID_REQUEST", message=str(exc)),
                                )
                            )
                        )
                        continue
                    await send_json(make_response_frame(ResponseFrame(id=req.id, ok=True, payload={"session": session})))
                elif req.method == "sessions.archive":
                    raw = req.params or {}
                    key = str(raw.get("key") or "").strip()
                    if not key:
                        await send_json(
                            make_response_frame(
                                ResponseFrame(
                                    id=req.id,
                                    ok=False,
                                    error=RpcError(code="INVALID_REQUEST", message="key is required"),
                                )
                            )
                        )
                        continue
                    try:
                        session = self._orchestrator.archive_session(
                            session_key=key,
                            archived=bool(raw.get("archived", True)),
                        )
                    except Exception as exc:
                        await send_json(
                            make_response_frame(
                                ResponseFrame(
                                    id=req.id,
                                    ok=False,
                                    error=RpcError(code="INVALID_REQUEST", message=str(exc)),
                                )
                            )
                        )
                        continue
                    await send_json(make_response_frame(ResponseFrame(id=req.id, ok=True, payload={"session": session})))
                elif req.method == "sessions.resolve":
                    key = str((req.params or {}).get("key") or "").strip()
                    if not key:
                        await send_json(
                            make_response_frame(
                                ResponseFrame(
                                    id=req.id,
                                    ok=False,
                                    error=RpcError(code="INVALID_REQUEST", message="key is required"),
                                )
                            )
                        )
                        continue
                    await send_json(
                        make_response_frame(
                            ResponseFrame(
                                id=req.id,
                                ok=True,
                                payload={"session": self._orchestrator.resolve_session(key)},
                            )
                        )
                    )
                else:
                    await send_json(
                        make_response_frame(
                            ResponseFrame(
                                id=req.id,
                                ok=False,
                                error=RpcError(code="METHOD_NOT_FOUND", message=f"unknown method: {req.method}"),
                            )
                        )
                    )
        except WebSocketDisconnect:
            pass
        finally:
            for task in list(tasks):
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle_connect(
        self,
        request_id: str,
        params: dict[str, Any] | None,
        send_json,
    ) -> bool:
        auth = (params or {}).get("auth")
        token = auth.get("token") if isinstance(auth, dict) else None
        if self._token and token != self._token:
            await send_json(
                make_response_frame(
                    ResponseFrame(
                        id=request_id,
                        ok=False,
                        error=RpcError(code="UNAUTHORIZED", message="invalid token"),
                    )
                )
            )
            return False

        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=True,
                    payload={
                        "type": "hello-ok",
                        "protocol": 1,
                        "features": {
                            "methods": [
                                "connect",
                                "chat.send",
                                "chat.abort",
                                "chat.history",
                                "prompts.list",
                                "providers.list",
                                "models.list",
                                "tools.list",
                                "sessions.list",
                                "sessions.create",
                                "sessions.rename",
                                "sessions.archive",
                                "sessions.resolve",
                            ],
                            "events": ["connect.challenge", "chat"],
                        },
                    },
                )
            )
        )
        return True

    async def _handle_chat_send(self, request_id: str, params: dict[str, Any] | None, send_json, tasks) -> None:
        raw = params or {}
        session_key = str(raw.get("sessionKey") or "").strip()
        message = str(raw.get("message") or "").strip()
        idempotency_key = str(raw.get("idempotencyKey") or "").strip()
        if not session_key or not message:
            await send_json(
                make_response_frame(
                    ResponseFrame(
                        id=request_id,
                        ok=False,
                        error=RpcError(code="INVALID_REQUEST", message="sessionKey and message are required"),
                    )
                )
            )
            return

        run_id = idempotency_key or str(uuid4())
        profile_id = str(raw.get("systemPromptId") or "").strip()
        task_prompt_id = str(raw.get("taskPromptId") or "").strip()
        system_prompt = compose_prompt(profile_id or None, task_prompt_id or None)

        await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"runId": run_id, "status": "started"})))

        async def emit_chat(payload: dict[str, Any]) -> None:
            await send_json(
                make_chat_event(
                    ChatEventPayload(
                        run_id=str(payload.get("runId") or run_id),
                        session_key=str(payload.get("sessionKey") or session_key),
                        seq=int(payload.get("seq") or 0),
                        state=str(payload.get("state") or "error"),
                        message=payload.get("message") if isinstance(payload.get("message"), dict) else None,
                        error_message=str(payload.get("errorMessage")) if payload.get("errorMessage") else None,
                        provider=str(payload.get("provider")) if payload.get("provider") else None,
                        model=str(payload.get("model")) if payload.get("model") else None,
                        capabilities=payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else None,
                        tool_execution=payload.get("toolExecution") if isinstance(payload.get("toolExecution"), dict) else None,
                    )
                )
            )

        async def run() -> None:
            try:
                await self._orchestrator.send_chat(
                    ChatSendRequest(
                        session_key=session_key,
                        message=message,
                        idempotency_key=run_id,
                        provider=str(raw.get("provider") or "codex-cli"),
                        model=str(raw.get("model") or "").strip() or None,
                        system_prompt_id=profile_id or None,
                        task_prompt_id=task_prompt_id or None,
                        timeout_ms=int(raw.get("timeoutMs")) if raw.get("timeoutMs") else None,
                        system_prompt=system_prompt,
                    ),
                    emit=emit_chat,
                )
            except SessionInFlightError as exc:
                await send_json(
                    make_response_frame(
                        ResponseFrame(
                            id=request_id,
                            ok=True,
                            payload={"runId": exc.run_id, "status": "in_flight"},
                        )
                    )
                )
            except Exception as exc:
                await emit_chat(
                    {
                        "runId": run_id,
                        "sessionKey": session_key,
                        "seq": 1,
                        "state": "error",
                        "errorMessage": str(exc),
                    }
                )

        task = asyncio.create_task(run())
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    async def _handle_chat_abort(self, request_id: str, params: dict[str, Any] | None, send_json) -> None:
        raw = params or {}
        session_key = str(raw.get("sessionKey") or "").strip()
        run_id = str(raw.get("runId") or "").strip() or None
        if not session_key and not run_id:
            await send_json(
                make_response_frame(
                    ResponseFrame(
                        id=request_id,
                        ok=False,
                        error=RpcError(code="INVALID_REQUEST", message="sessionKey or runId is required"),
                    )
                )
            )
            return
        result = self._orchestrator.abort(session_key=session_key, run_id=run_id)
        await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=result)))

    async def _handle_chat_history(self, request_id: str, params: dict[str, Any] | None, send_json) -> None:
        raw = params or {}
        session_key = str(raw.get("sessionKey") or "").strip()
        limit = int(raw.get("limit") or 200)
        if not session_key:
            await send_json(
                make_response_frame(
                    ResponseFrame(
                        id=request_id,
                        ok=False,
                        error=RpcError(code="INVALID_REQUEST", message="sessionKey is required"),
                    )
                )
            )
            return
        messages = self._orchestrator.history(session_key=session_key, limit=limit)
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=True,
                    payload={"sessionKey": session_key, "messages": messages},
                )
            )
        )
