"""WebSocket RPC schema helpers for CopeNet gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

FrameType = Literal["req", "res", "event"]
ChatState = Literal["delta", "final", "error", "aborted"]


@dataclass(frozen=True)
class RpcError:
    """Structured RPC error payload."""

    code: str
    message: str
    details: Any | None = None


@dataclass(frozen=True)
class ChatEventPayload:
    """Payload for `event=chat` frames."""

    run_id: str
    session_key: str
    seq: int
    state: ChatState
    message: dict[str, Any] | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class RequestFrame:
    """Inbound client request frame."""

    id: str
    method: str
    params: dict[str, Any] | None = None


@dataclass(frozen=True)
class ResponseFrame:
    """Server response frame."""

    id: str
    ok: bool
    payload: dict[str, Any] | None = None
    error: RpcError | None = None


@dataclass(frozen=True)
class EventFrame:
    """Server event frame."""

    event: str
    payload: dict[str, Any] | None = None
    seq: int | None = None


def parse_request_frame(raw: dict[str, Any]) -> RequestFrame:
    """Validate and normalize a request frame. Raises ValueError if invalid."""
    if raw.get("type") != "req":
        raise ValueError("invalid frame type: expected 'req'")

    frame_id = raw.get("id")
    method = raw.get("method")
    params = raw.get("params")

    if not isinstance(frame_id, str) or not frame_id.strip():
        raise ValueError("invalid request id")
    if not isinstance(method, str) or not method.strip():
        raise ValueError("invalid request method")
    if params is not None and not isinstance(params, dict):
        raise ValueError("invalid request params")

    return RequestFrame(id=frame_id.strip(), method=method.strip(), params=params)


def make_response_frame(frame: ResponseFrame) -> dict[str, Any]:
    """Serialize a response frame to a transport dictionary."""
    payload: dict[str, Any] = {
        "type": "res",
        "id": frame.id,
        "ok": frame.ok,
    }
    if frame.payload is not None:
        payload["payload"] = frame.payload
    if frame.error is not None:
        payload["error"] = {
            "code": frame.error.code,
            "message": frame.error.message,
            "details": frame.error.details,
        }
    return payload


def make_event_frame(frame: EventFrame) -> dict[str, Any]:
    """Serialize an event frame to a transport dictionary."""
    payload: dict[str, Any] = {
        "type": "event",
        "event": frame.event,
    }
    if frame.payload is not None:
        payload["payload"] = frame.payload
    if frame.seq is not None:
        payload["seq"] = frame.seq
    return payload


def make_chat_event(payload: ChatEventPayload) -> dict[str, Any]:
    """Build a normalized `chat` event frame."""
    return make_event_frame(
        EventFrame(
            event="chat",
            payload={
                "runId": payload.run_id,
                "sessionKey": payload.session_key,
                "seq": payload.seq,
                "state": payload.state,
                "message": payload.message,
                "errorMessage": payload.error_message,
            },
            seq=payload.seq,
        )
    )
