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

    @property
    def orchestrator(self) -> Orchestrator:
        return self._orchestrator

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
                await dispatch_rpc(req, send_json, self._orchestrator, tasks)
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
