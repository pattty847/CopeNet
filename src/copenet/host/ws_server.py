"""WebSocket RPC server scaffold for CopeNet."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from copenet.core.orchestrator import Orchestrator
from copenet.host.rpc_dispatch import dispatch_rpc
from copenet.host.rpc_schema import (
    EventFrame,
    ResponseFrame,
    RpcError,
    make_event_frame,
    make_response_frame,
    parse_request_frame,
)


class CopeNetWsServer:
    """Minimal CopeNet WS RPC handler."""

    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self._orchestrator = orchestrator or Orchestrator()
        self._token = os.environ.get("COPNET_TOKEN", "dev-token").strip()
        # Every authenticated connection's send_json, so chat/approval events can
        # fan out to all of them (reconnected socket, second device) instead of
        # only the socket that started the run.
        self._connections: set[Any] = set()

    @property
    def orchestrator(self) -> Orchestrator:
        return self._orchestrator

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Send one event payload to every connected client, best-effort.

        Iterates a snapshot so a client disconnecting mid-broadcast (and removing
        itself from the set) can't break the loop; a dead socket's send just
        raises and is skipped.
        """
        for send in list(self._connections):
            try:
                await send(payload)
            except Exception:
                continue

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
                    self._connections.add(send_json)
                    continue
                if os.environ.get("COPNET_RPC_DEBUG") == "1":
                    print(f"RPC {req.method} {req.id}", flush=True)
                await dispatch_rpc(req, send_json, self._orchestrator, tasks, self.broadcast)
        except WebSocketDisconnect:
            pass
        finally:
            # Stop fanning events to this socket once it's gone. Accepted chat
            # runs belong to the session/run store, not to a particular browser
            # socket — remote/mobile clients can reconnect during a run and the
            # run keeps streaming to whatever connections remain.
            self._connections.discard(send_json)

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
                                "prompts.optimize",
                                "providers.list",
                                "profile.get",
                                "identity.context",
                                "persona.get",
                                "persona.settings.get",
                                "persona.settings.update",
                                "persona.context",
                                "persona.flavor.draft",
                                "persona.flavor.save",
                                "persona.readFile",
                                "persona.writeFile",
                                "profile.changelog",
                                "briefing.get",
                                "memory.list",
                                "memory.upsert",
                                "memory.archive",
                                "runtime.context",
                                "runtime.workspace.browse",
                                "runtime.workspace.set",
                                "providerAuth.status",
                                "providerAuth.beginLogin",
                                "providerAuth.completeLogin",
                                "providerAuth.logout",
                                "messaging.config.get",
                                "messaging.config.update",
                                "messaging.test",
                                "messaging.destinations.list",
                                "messaging.destinations.upsert",
                                "messaging.destinations.delete",
                                "messaging.routes.list",
                                "messaging.routes.upsert",
                                "messaging.routes.delete",
                                "messaging.routes.resolve",
                                "models.list",
                                "tools.list",
                                "sessions.list",
                                "sessions.create",
                                "sessions.merge.create",
                                "sessions.merge.state",
                                "sessions.rename",
                                "sessions.archive",
                                "sessions.artifacts",
                                "sessions.revertEdit",
                                "workspace.listFiles",
                                "workspace.readFile",
                                "workspace.writeFile",
                                "chat.decideApproval",
                                "approvals.list",
                                "sessions.export",
                                "sessions.debugCopy",
                                "sessions.runs",
                                "sessions.run",
                                "sessions.state",
                                "sessions.resolve",
                                "pulse.list",
                                "pulse.create_from_session",
                                "pulse.save",
                                "pulse.dismiss",
                                "nasa.apod",
                                "nasa.apod.list",
                            ],
                            "events": ["connect.challenge", "chat", "profile.changed", "briefing.ready", "memory.changed", "sessions.merge.updated", "pulse.updated", "messaging.updated", "approval.pending", "approval.resolved"],
                        },
                    },
                )
            )
        )
        return True
