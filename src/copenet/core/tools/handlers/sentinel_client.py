"""Small, loopback-only HTTP client for Sentinel's GUI Agent API."""

from __future__ import annotations

import asyncio
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class SentinelApiError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def sentinel_base_url() -> str:
    raw = os.environ.get("COPNET_SENTINEL_URL", "http://127.0.0.1:17100").strip()
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise SentinelApiError("invalid_base_url", "COPNET_SENTINEL_URL must be an HTTP loopback origin (127.0.0.1 or localhost).")
    try:
        port = parsed.port
    except ValueError as exc:
        raise SentinelApiError("invalid_base_url", "COPNET_SENTINEL_URL has an invalid port.") from exc
    if port is None:
        raise SentinelApiError("invalid_base_url", "COPNET_SENTINEL_URL must include Sentinel's API port.")
    return f"http://{parsed.hostname}:{port}"


async def sentinel_request(
    method: str, path: str, *, params: dict | None = None, payload: dict | None = None,
    timeout: float = 2.0, screenshot: bool = False,
) -> dict:
    base_url = sentinel_base_url()
    query = f"?{urlencode(params)}" if params else ""
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = Request(f"{base_url}{path}{query}", data=body, headers=headers, method=method)

    def fetch() -> dict:
        try:
            # A redirect must never turn a local observation into remote egress.
            opener = build_opener(ProxyHandler({}), _NoRedirect())
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(3_000_001)
        except HTTPError as exc:
            raw = exc.read(3_000_001)
        except (URLError, TimeoutError, OSError) as exc:
            raise SentinelApiError("gui_unavailable", f"Sentinel GUI Agent API is unavailable at {base_url}: {exc}") from exc
        if len(raw) > 3_000_000:
            raise SentinelApiError("response_too_large", "Sentinel API response exceeded 3 MB.")
        try:
            envelope = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise SentinelApiError("invalid_response", "Sentinel API returned invalid JSON.") from exc
        if not isinstance(envelope, dict) or not isinstance(envelope.get("ok"), bool):
            raise SentinelApiError("invalid_response", "Sentinel API returned an invalid envelope.")
        if not envelope["ok"]:
            error = envelope.get("error")
            if not isinstance(error, dict):
                raise SentinelApiError("invalid_response", "Sentinel API returned an invalid error envelope.")
            raise SentinelApiError(str(error.get("code") or "api_error"), str(error.get("message") or "Sentinel API request failed."))
        if screenshot:
            if not isinstance(envelope.get("path"), str):
                raise SentinelApiError("invalid_response", "Sentinel screenshot response has no path.")
        elif not isinstance(envelope.get("meta"), dict) or not isinstance(envelope.get("data"), dict):
            raise SentinelApiError("invalid_response", "Sentinel API response has no meta/data envelope.")
        return envelope

    return await asyncio.to_thread(fetch)
