"""WebSocket RPC server scaffold for CopeNet."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from copenet.orchestrator import ChatSendRequest, Orchestrator, SessionInFlightError
from copenet.prompts import get_preset_text, list_presets
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
                    await send_json(
                        make_response_frame(
                            ResponseFrame(
                                id=req.id,
                                ok=True,
                                payload={"sessions": self._orchestrator.list_sessions()},
                            )
                        )
                    )
                elif req.method == "prompts.list":
                    await send_json(
                        make_response_frame(
                            ResponseFrame(
                                id=req.id,
                                ok=True,
                                payload={"prompts": list_presets()},
                            )
                        )
                    )
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
                                "sessions.list",
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
        system_prompt: str | None = None
        preset_id = str(raw.get("systemPromptId") or "").strip()
        if preset_id:
            system_prompt = get_preset_text(preset_id)

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
