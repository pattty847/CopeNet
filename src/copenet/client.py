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

    @staticmethod
    def _response_error(frame: dict[str, Any], fallback_prefix: str) -> RuntimeError:
        err = frame.get("error")
        if isinstance(err, dict):
            message = err.get("message")
            if isinstance(message, str) and message.strip():
                return RuntimeError(f"{fallback_prefix}: {message}")
        return RuntimeError(f"{fallback_prefix}: unknown error")

    @staticmethod
    def _payload_dict(frame: dict[str, Any]) -> dict[str, Any]:
        payload = frame.get("payload")
        if not isinstance(payload, dict):
            raise RuntimeError("invalid response payload")
        return payload

    @staticmethod
    def _payload_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
        value = payload.get(key)
        return value if isinstance(value, list) else []

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send one non-streaming RPC request and return the payload."""
        connect_req_id = f"connect-{uuid.uuid4().hex[:8]}"
        req_id = f"{method}-{uuid.uuid4().hex[:8]}"
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
                        raise self._response_error(frame, "connect failed")
                    break

            await ws.send(
                self._to_json(
                    {
                        "type": "req",
                        "id": req_id,
                        "method": method,
                        "params": params or {},
                    }
                )
            )
            while True:
                raw = await ws.recv()
                frame = self._parse_frame(raw)
                if frame.get("type") == "res" and frame.get("id") == req_id:
                    if frame.get("ok") is not True:
                        raise self._response_error(frame, f"{method} failed")
                    return self._payload_dict(frame)

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
                        raise self._response_error(frame, "chat.send failed")
                    payload = self._payload_dict(frame)
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
        params: dict[str, Any] = {"sessionKey": session_key}
        if run_id:
            params["runId"] = run_id
        return await self._rpc("chat.abort", params)

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch the public CopeNet tool catalog."""
        payload = await self._rpc("tools.list", {})
        return self._payload_list(payload, "tools")

    async def list_providers(self) -> list[dict[str, Any]]:
        """Fetch the public provider catalog."""
        payload = await self._rpc("providers.list", {})
        return self._payload_list(payload, "providers")

    async def list_models(self, provider: str | None = None, kind: str = "chat") -> list[dict[str, Any]]:
        """Fetch models for one provider or all providers."""
        params: dict[str, Any] = {"kind": kind}
        if provider:
            params["provider"] = provider
        payload = await self._rpc("models.list", params)
        return self._payload_list(payload, "models")

    async def provider_auth_status(self, provider: str) -> dict[str, Any]:
        """Fetch auth status for a provider-managed credential source."""
        payload = await self._rpc("providerAuth.status", {"provider": provider})
        value = payload.get("status")
        return value if isinstance(value, dict) else {}

    async def provider_auth_begin_login(self, provider: str, redirect_uri: str | None = None) -> dict[str, Any]:
        """Begin a provider auth login flow."""
        params: dict[str, Any] = {"provider": provider}
        if redirect_uri:
            params["redirectUri"] = redirect_uri
        payload = await self._rpc("providerAuth.beginLogin", params)
        value = payload.get("login")
        return value if isinstance(value, dict) else {}

    async def provider_auth_complete_login(
        self,
        provider: str,
        *,
        login_token: str,
        redirect_url: str | None = None,
        code: str | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        """Complete a provider auth login flow."""
        params: dict[str, Any] = {"provider": provider, "loginToken": login_token}
        if redirect_url:
            params["redirectUrl"] = redirect_url
        if code:
            params["code"] = code
        if state:
            params["state"] = state
        payload = await self._rpc("providerAuth.completeLogin", params)
        value = payload.get("status")
        return value if isinstance(value, dict) else {}

    async def provider_auth_logout(self, provider: str) -> dict[str, Any]:
        """Clear provider-managed local auth state."""
        payload = await self._rpc("providerAuth.logout", {"provider": provider})
        value = payload.get("status")
        return value if isinstance(value, dict) else {}

    async def list_sessions(self, include_archived: bool = False) -> list[dict[str, Any]]:
        """Fetch known sessions."""
        payload = await self._rpc("sessions.list", {"includeArchived": include_archived})
        return self._payload_list(payload, "sessions")

    async def resolve_session(self, session_key: str) -> dict[str, Any] | None:
        """Fetch one session by key."""
        payload = await self._rpc("sessions.resolve", {"key": session_key})
        value = payload.get("session")
        return value if isinstance(value, dict) else None

    async def resolve_session_state(self, session_key: str) -> dict[str, Any] | None:
        """Fetch one structured session state by key."""
        payload = await self._rpc("sessions.state", {"key": session_key})
        value = payload.get("state")
        return value if isinstance(value, dict) else None

    async def list_session_artifacts(self, session_key: str, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch recent runtime artifacts for one session."""
        payload = await self._rpc("sessions.artifacts", {"key": session_key, "limit": limit})
        return self._payload_list(payload, "artifacts")

    async def list_session_runs(self, session_key: str, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch recent durable run records for one session."""
        payload = await self._rpc("sessions.runs", {"key": session_key, "limit": limit})
        return self._payload_list(payload, "runs")

    async def resolve_session_run(self, session_key: str, run_id: str) -> dict[str, Any] | None:
        """Fetch one durable run record by session/run id."""
        payload = await self._rpc("sessions.run", {"key": session_key, "runId": run_id})
        value = payload.get("run")
        return value if isinstance(value, dict) else None

    async def debug_copy_session(self, session_key: str) -> dict[str, Any]:
        """Create and return a debug copy of one session."""
        payload = await self._rpc("sessions.debugCopy", {"key": session_key})
        value = payload.get("session")
        if not isinstance(value, dict):
            raise RuntimeError("invalid debug copy payload")
        return value

    async def export_session(self, session_key: str) -> dict[str, Any]:
        """Export one session transcript payload."""
        return await self._rpc("sessions.export", {"key": session_key})

    async def history(self, session_key: str, limit: int = 200) -> list[dict[str, Any]]:
        """Fetch chat history for one session."""
        payload = await self._rpc("chat.history", {"sessionKey": session_key, "limit": limit})
        return self._payload_list(payload, "messages")

    @staticmethod
    def _parse_frame(raw: str) -> dict[str, Any]:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("invalid non-object frame")
        return parsed

    @staticmethod
    def _to_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)
