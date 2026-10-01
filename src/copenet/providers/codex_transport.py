"""HTTP transport for the Codex Responses endpoint (auth headers, error mapping)."""

from __future__ import annotations
import asyncio
import json
from typing import Any, Iterator
from urllib import error, request
from .base import ProviderEvent
from .responses_stream import classify_responses_body, parse_responses_json, parse_responses_sse

OPENAI_CODEX_ORIGINATOR = "copenet"


def stream_responses(
    *,
    url: str,
    payload: dict[str, Any],
    access_token: str,
    account_id: str | None,
    abort_event: asyncio.Event,
    session_id: str | None = None,
) -> Iterator[ProviderEvent]:
    """POST one Responses turn and yield the Phase 2 tool-loop event vocabulary."""
    body = json.dumps(payload).encode("utf-8")
    headers = _build_openai_codex_headers(access_token=access_token, accept="text/event-stream", session_id=session_id)
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=180.0) as response:
            content_type = str(response.headers.get("Content-Type") or "")
            kind, payload = classify_responses_body(response, content_type)
            if kind == "sse":
                yield from parse_responses_sse(response=payload, abort_event=abort_event, label="openai-codex")
                return
            if not abort_event.is_set():
                yield from parse_responses_json(payload, label="openai-codex")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if exc.code in {401, 403}:
            raise RuntimeError(
                "openai-codex authentication failed. Re-run `uv run copenet auth login --provider openai-codex`."
            ) from exc
        raise RuntimeError(f"openai-codex request failed ({exc.code}): {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"openai-codex transport error: {exc.reason}") from exc


def _build_openai_codex_headers(*, access_token: str, accept: str, session_id: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": accept,
        "originator": OPENAI_CODEX_ORIGINATOR,
        "User-Agent": OPENAI_CODEX_ORIGINATOR,
    }
    if session_id:
        # Codex's own client sends these on every request (codex-rs/codex-api
        # requests/headers.rs: build_session_headers). Gateways in front of this
        # backend describe a stable per-conversation header as what keeps a
        # session on a cache-warm upstream; one CopeNet session is one thread.
        headers["session-id"] = session_id
        headers["thread-id"] = session_id
    return headers
