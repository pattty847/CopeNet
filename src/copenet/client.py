"""Async WebSocket client for CopeNet gateway RPC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable
import uuid
import json

import websockets


ChatEventCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class GatewayConfig:
    """Connection settings for the local CopeNet gateway."""

    url: str = "ws://127.0.0.1:17123/ws"
    token: str = "dev-token"


class GatewayClient:
    """Small RPC client wrapper for CopeNet WS protocol."""

    def __init__(self, config: GatewayConfig | None = None) -> None:
        self._config = config or GatewayConfig()

    async def stream_chat(
        self,
        session_key: str,
        message: str,
        idempotency_key: str,
        provider: str,
        model: str | None,
        on_event: ChatEventCallback,
        on_started: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Send one chat request and stream matching chat events."""
        connect_req_id = f"connect-{uuid.uuid4().hex[:8]}"
        send_req_id = f"send-{uuid.uuid4().hex[:8]}"

        async with websockets.connect(self._config.url, max_size=10 * 1024 * 1024) as ws:
            while True:
                raw = await ws.recv()
                frame = self._parse_frame(raw)
                if frame.get("type") == "event" and frame.get("event") == "connect.challenge":
                    await ws.send(
                        self._to_json(
                            {
                                "type": "req",
                                "id": connect_req_id,
                                "method": "connect",
                                "params": {"auth": {"token": self._config.token}},
                            }
                        )
                    )
                    continue
                if frame.get("type") == "res" and frame.get("id") == connect_req_id:
                    if frame.get("ok") is not True:
                        err = frame.get("error") or {}
                        raise RuntimeError(f"connect failed: {err.get('message') or 'unknown error'}")
                    break

            await ws.send(
                self._to_json(
                    {
                        "type": "req",
                        "id": send_req_id,
                        "method": "chat.send",
                        "params": {
                            "sessionKey": session_key,
                            "message": message,
                            "idempotencyKey": idempotency_key,
                            "provider": provider,
                            "model": model,
                        },
                    }
                )
            )

            active_run_id: str | None = None
            send_result: dict[str, Any] = {"runId": idempotency_key, "status": "started"}

            while True:
                raw = await ws.recv()
                frame = self._parse_frame(raw)
                frame_type = frame.get("type")

                if frame_type == "res" and frame.get("id") == send_req_id:
                    if frame.get("ok") is not True:
                        err = frame.get("error") or {}
                        raise RuntimeError(f"chat.send failed: {err.get('message') or 'unknown error'}")
                    payload = frame.get("payload") or {}
                    if isinstance(payload, dict):
                        send_result = payload
                        run_id = payload.get("runId")
                        if isinstance(run_id, str) and run_id.strip():
                            active_run_id = run_id.strip()
                            if on_started is not None:
                                await on_started(active_run_id)
                        status = str(payload.get("status") or "").strip()
                        if status in {"in_flight", "cached"}:
                            return payload
                    continue

                if frame_type == "event" and frame.get("event") == "chat":
                    payload = frame.get("payload") or {}
                    if not isinstance(payload, dict):
                        continue
                    run_id = payload.get("runId")
                    if isinstance(run_id, str) and run_id.strip():
                        if active_run_id is None:
                            active_run_id = run_id.strip()
                            if on_started is not None:
                                await on_started(active_run_id)
                        elif run_id.strip() != active_run_id:
                            continue
                    await on_event(payload)
                    state = str(payload.get("state") or "")
                    if state in {"final", "error", "aborted"}:
                        return send_result

    async def abort(self, session_key: str, run_id: str | None = None) -> dict[str, Any]:
        """Send chat.abort for a session/run."""
        connect_req_id = f"connect-{uuid.uuid4().hex[:8]}"
        abort_req_id = f"abort-{uuid.uuid4().hex[:8]}"
        async with websockets.connect(self._config.url, max_size=2 * 1024 * 1024) as ws:
            while True:
                raw = await ws.recv()
                frame = self._parse_frame(raw)
                if frame.get("type") == "event" and frame.get("event") == "connect.challenge":
                    await ws.send(
                        self._to_json(
                            {
                                "type": "req",
                                "id": connect_req_id,
                                "method": "connect",
                                "params": {"auth": {"token": self._config.token}},
                            }
                        )
                    )
                    continue
                if frame.get("type") == "res" and frame.get("id") == connect_req_id:
                    if frame.get("ok") is not True:
                        err = frame.get("error") or {}
                        raise RuntimeError(f"connect failed: {err.get('message') or 'unknown error'}")
                    break

            params: dict[str, Any] = {"sessionKey": session_key}
            if run_id:
                params["runId"] = run_id
            await ws.send(
                self._to_json(
                    {
                        "type": "req",
                        "id": abort_req_id,
                        "method": "chat.abort",
                        "params": params,
                    }
                )
            )
            while True:
                raw = await ws.recv()
                frame = self._parse_frame(raw)
                if frame.get("type") == "res" and frame.get("id") == abort_req_id:
                    if frame.get("ok") is not True:
                        err = frame.get("error") or {}
                        raise RuntimeError(f"chat.abort failed: {err.get('message') or 'unknown error'}")
                    payload = frame.get("payload") or {}
                    return payload if isinstance(payload, dict) else {"ok": True}

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch the public CopeNet tool catalog."""
        connect_req_id = f"connect-{uuid.uuid4().hex[:8]}"
        list_req_id = f"tools-{uuid.uuid4().hex[:8]}"
        async with websockets.connect(self._config.url, max_size=2 * 1024 * 1024) as ws:
            while True:
                raw = await ws.recv()
                frame = self._parse_frame(raw)
                if frame.get("type") == "event" and frame.get("event") == "connect.challenge":
                    await ws.send(
                        self._to_json(
                            {
                                "type": "req",
                                "id": connect_req_id,
                                "method": "connect",
                                "params": {"auth": {"token": self._config.token}},
                            }
                        )
                    )
                    continue
                if frame.get("type") == "res" and frame.get("id") == connect_req_id:
                    if frame.get("ok") is not True:
                        err = frame.get("error") or {}
                        raise RuntimeError(f"connect failed: {err.get('message') or 'unknown error'}")
                    break

            await ws.send(
                self._to_json(
                    {
                        "type": "req",
                        "id": list_req_id,
                        "method": "tools.list",
                        "params": {},
                    }
                )
            )
            while True:
                raw = await ws.recv()
                frame = self._parse_frame(raw)
                if frame.get("type") == "res" and frame.get("id") == list_req_id:
                    if frame.get("ok") is not True:
                        err = frame.get("error") or {}
                        raise RuntimeError(f"tools.list failed: {err.get('message') or 'unknown error'}")
                    payload = frame.get("payload") or {}
                    tools = payload.get("tools") if isinstance(payload, dict) else []
                    return tools if isinstance(tools, list) else []

    @staticmethod
    def _parse_frame(raw: str) -> dict[str, Any]:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("invalid non-object frame")
        return parsed

    @staticmethod
    def _to_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)
