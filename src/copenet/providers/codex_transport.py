"""HTTP transport and content-type detection for the Codex Responses endpoint."""

from __future__ import annotations
import asyncio
import json
from typing import Any, Iterator
from urllib import error, request
from .base import ProviderEvent
from .codex_responses import parse_responses_sse, parse_responses_json

OPENAI_CODEX_ORIGINATOR = "copenet"


def stream_responses(
    *,
    url: str,
    payload: dict[str, Any],
    access_token: str,
    account_id: str | None,
    abort_event: asyncio.Event,
) -> Iterator[ProviderEvent]:
    """POST one Responses turn and yield the Phase 2 tool-loop event vocabulary."""
    body = json.dumps(payload).encode("utf-8")
    headers = _build_openai_codex_headers(access_token=access_token, accept="text/event-stream")
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=180.0) as response:
            content_type = str(response.headers.get("Content-Type") or "")
            kind, payload = classify_responses_body(response, content_type)
            if kind == "sse":
                yield from parse_responses_sse(response=payload, abort_event=abort_event)
                return
            if not abort_event.is_set():
                yield from parse_responses_json(payload)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if exc.code in {401, 403}:
            raise RuntimeError(
                "openai-codex authentication failed. Re-run `uv run copenet auth login --provider openai-codex`."
            ) from exc
        raise RuntimeError(f"openai-codex request failed ({exc.code}): {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"openai-codex transport error: {exc.reason}") from exc


def classify_responses_body(response: Any, content_type: str) -> tuple[str, Any]:
    """Decide whether the body should be streamed as SSE or parsed as JSON.

    Returns ``("sse", iterable_of_lines)`` for SSE bodies and
    ``("json", raw_text)`` otherwise. The live codex backend sometimes returns
    SSE bodies with a missing or non-event-stream Content-Type header, so we
    sniff the first non-blank line when the header is ambiguous.
    """
    if "text/event-stream" in content_type.lower():
        return "sse", response
    buffered: list[Any] = []
    while True:
        line = response.readline()
        if not line:
            break
        text_line = (
            line.decode("utf-8", errors="replace") if isinstance(line, (bytes, bytearray)) else str(line)
        )
        buffered.append(line)
        if text_line.strip():
            stripped = text_line.lstrip()
            if stripped.startswith("event:") or stripped.startswith("data:"):
                return "sse", _ChainedLines(buffered, response)
            # Not SSE — fall through and assemble JSON body below.
            break
    remaining = response.read() if hasattr(response, "read") else b""
    full = _join_lines(buffered + [remaining]) if remaining else _join_lines(buffered)
    if isinstance(full, (bytes, bytearray)):
        return "json", full.decode("utf-8", errors="replace")
    return "json", str(full)


def _join_lines(parts: list[Any]) -> Any:
    if not parts:
        return b""
    if any(isinstance(p, (bytes, bytearray)) for p in parts):
        return b"".join(p if isinstance(p, (bytes, bytearray)) else str(p).encode("utf-8") for p in parts)
    return "".join(str(p) for p in parts)


class _ChainedLines:
    """Iterates the buffered prelude lines then the remaining lines of ``response``."""

    def __init__(self, buffered: list[Any], response: Any) -> None:
        self._buffered = list(buffered)
        self._response = response

    def __iter__(self) -> Iterator[Any]:
        for line in self._buffered:
            yield line
        self._buffered = []
        for line in self._response:
            yield line


def _build_openai_codex_headers(*, access_token: str, accept: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": accept,
        "originator": OPENAI_CODEX_ORIGINATOR,
        "User-Agent": OPENAI_CODEX_ORIGINATOR,
    }
