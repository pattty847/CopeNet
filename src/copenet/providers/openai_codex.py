"""OpenAI Codex subscription-backed provider for CopeNet-controlled harness use."""

from __future__ import annotations

import asyncio
import json
from http.client import IncompleteRead
from typing import Any, AsyncIterator, Iterator
from urllib import error, request

from copenet.core.provider_auth import OPENAI_CODEX_PROVIDER_ID, OpenAICodexAuthService
from copenet.providers.base import ProviderEvent, ProviderModel

OPENAI_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
OPENAI_CODEX_MODELS = ("gpt-5.4", "gpt-5.5")
OPENAI_CODEX_DEFAULT_MODEL = OPENAI_CODEX_MODELS[0]
OPENAI_CODEX_ORIGINATOR = "copenet"
OPENAI_CODEX_DEFAULT_INSTRUCTIONS = "You are CopeNet's coding assistant. Follow the user's request carefully."


class OpenAICodexProvider:
    name = OPENAI_CODEX_PROVIDER_ID
    display_name = "OpenAI Codex"

    def __init__(self, auth_service: OpenAICodexAuthService | None = None, base_url: str = OPENAI_CODEX_BASE_URL) -> None:
        self.auth_service = auth_service or OpenAICodexAuthService()
        self._base_url = base_url.rstrip("/")

    async def describe(self) -> dict[str, object]:
        status = self.auth_service.status()
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": bool(status["authenticated"]),
            "supportsModelSelection": True,
            "modelCount": len(OPENAI_CODEX_MODELS),
            "defaultModel": OPENAI_CODEX_DEFAULT_MODEL,
            "requiresAuth": True,
            "authenticated": bool(status["authenticated"]),
            "authType": "oauth",
            "authStatus": status,
            "capabilities": {
                "chat": True,
                "embeddings": False,
                "toolCalls": False,
                "promptedToolUse": True,
                "streaming": True,
                "resume": False,
            },
        }

    async def list_models(self) -> list[ProviderModel]:
        return [
            ProviderModel(
                id=model_id,
                display_name=model_id.upper().replace("GPT-", "GPT-"),
                provider=self.name,
                description="ChatGPT subscription-backed Codex model routed through CopeNet.",
                kind="chat",
                capabilities={
                    "chat": True,
                    "streaming": True,
                    "toolCalls": False,
                    "promptedToolUse": True,
                    "resume": False,
                },
                recommended_for=["chat", "agentic-work"],
                metadata={"ownedBy": "OpenAI", "transport": "openai-codex-responses"},
            )
            for model_id in OPENAI_CODEX_MODELS
        ]

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        if abort_event.is_set():
            return
        profile = await asyncio.to_thread(self.auth_service.ensure_valid_profile)
        payload = _build_payload(
            model=_resolve_model(model),
            prompt=prompt,
            system_prompt=system_prompt,
        )
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[ProviderEvent | Exception | object] = asyncio.Queue()
        done_marker = object()

        def worker() -> None:
            try:
                for event in _stream_responses(
                    url=f"{self._base_url}/responses",
                    payload=payload,
                    access_token=profile.access_token,
                    account_id=profile.account_id,
                    abort_event=abort_event,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, done_marker)

        task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            while True:
                item = await queue.get()
                if item is done_marker:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            await task
        yield ProviderEvent(kind="final", provider_session_id=provider_session_id)



def _resolve_model(model: str | None) -> str:
    normalized = str(model or "").strip() or OPENAI_CODEX_DEFAULT_MODEL
    if normalized not in OPENAI_CODEX_MODELS:
        supported = ", ".join(OPENAI_CODEX_MODELS)
        raise ValueError(f"unsupported openai-codex model: {normalized}. Supported models: {supported}")
    return normalized



def _build_payload(*, model: str, prompt: str, system_prompt: str | None) -> dict[str, Any]:
    content_text = prompt if prompt.strip() else " "
    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": content_text}],
            }
        ],
        "store": False,
        "stream": True,
        "text": {"verbosity": "medium"},
    }
    instructions = (system_prompt or "").strip() or OPENAI_CODEX_DEFAULT_INSTRUCTIONS
    payload["instructions"] = instructions
    return payload



def _post_responses(*, url: str, payload: dict[str, Any], access_token: str, account_id: str | None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = _build_openai_codex_headers(access_token=access_token, accept="text/event-stream")
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=120.0) as response:
            content_type = str(response.headers.get("Content-Type") or "")
            raw_body = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if exc.code in {401, 403}:
            raise RuntimeError(
                "openai-codex authentication failed. Re-run `uv run copenet auth login --provider openai-codex`."
            ) from exc
        raise RuntimeError(f"openai-codex request failed ({exc.code}): {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"openai-codex transport error: {exc.reason}") from exc
    data = _decode_openai_codex_response_body(raw_body=raw_body, content_type=content_type)
    if not isinstance(data, dict):
        raise RuntimeError("openai-codex returned an invalid response payload")
    return data


def _stream_responses(
    *,
    url: str,
    payload: dict[str, Any],
    access_token: str,
    account_id: str | None,
    abort_event: asyncio.Event,
) -> Iterator[ProviderEvent]:
    body = json.dumps(payload).encode("utf-8")
    headers = _build_openai_codex_headers(access_token=access_token, accept="text/event-stream")
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=120.0) as response:
            content_type = str(response.headers.get("Content-Type") or "")
            if "text/event-stream" not in content_type.lower():
                raw_body = response.read().decode("utf-8", errors="replace")
                data = _decode_openai_codex_response_body(raw_body=raw_body, content_type=content_type)
                text = _extract_response_text(data)
                if text:
                    yield ProviderEvent(kind="delta", text=text)
                return
            yield from _stream_openai_codex_sse(response=response, abort_event=abort_event)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if exc.code in {401, 403}:
            raise RuntimeError(
                "openai-codex authentication failed. Re-run `uv run copenet auth login --provider openai-codex`."
            ) from exc
        raise RuntimeError(f"openai-codex request failed ({exc.code}): {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"openai-codex transport error: {exc.reason}") from exc


def _stream_openai_codex_sse(*, response: Any, abort_event: asyncio.Event) -> Iterator[ProviderEvent]:
    saw_delta = False
    completed_response: dict[str, Any] | None = None
    try:
        for raw in response:
            if abort_event.is_set():
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data:
                continue
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("type") or "").strip()
            if event_type == "response.output_text.delta":
                delta = str(event.get("delta") or "")
                if delta:
                    saw_delta = True
                    yield ProviderEvent(kind="delta", text=delta)
                continue
            if event_type in {"response.failed", "error"}:
                raise RuntimeError(_openai_codex_failure_message(event))
            if event_type == "response.completed":
                response_payload = event.get("response")
                if isinstance(response_payload, dict):
                    completed_response = response_payload
                break
    except IncompleteRead as exc:
        if saw_delta:
            return
        partial_size = len(exc.partial) if isinstance(exc.partial, (bytes, bytearray)) else 0
        raise RuntimeError(f"openai-codex stream ended incomplete before assistant text ({partial_size} bytes read)") from exc

    if not saw_delta and completed_response is not None:
        text = _extract_response_text(completed_response)
        if text:
            yield ProviderEvent(kind="delta", text=text)
    elif not saw_delta and completed_response is None and not abort_event.is_set():
        raise RuntimeError("openai-codex returned no completed response")


def _openai_codex_failure_message(event: dict[str, Any]) -> str:
    failure = event.get("error")
    if isinstance(failure, dict):
        message = str(failure.get("message") or "").strip()
        if message:
            return message
    return str(event.get("message") or "").strip() or "openai-codex request failed"


def _build_openai_codex_headers(*, access_token: str, accept: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": accept,
        "originator": OPENAI_CODEX_ORIGINATOR,
        "User-Agent": OPENAI_CODEX_ORIGINATOR,
    }


def _decode_openai_codex_response_body(*, raw_body: str, content_type: str) -> dict[str, Any]:
    lowered = content_type.lower()
    trimmed = raw_body.lstrip()
    if "text/event-stream" in lowered or trimmed.startswith("event:") or trimmed.startswith("data:"):
        return _decode_openai_codex_sse(raw_body)
    data = json.loads(raw_body)
    return data if isinstance(data, dict) else {}


def _decode_openai_codex_sse(raw_body: str) -> dict[str, Any]:
    deltas: list[str] = []
    completed_response: dict[str, Any] | None = None
    failure_message: str | None = None
    for line in raw_body.splitlines():
        if not line.startswith("data: "):
            continue
        data = line[6:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "").strip()
        if event_type == "response.output_text.delta":
            delta = str(event.get("delta") or "")
            if delta:
                deltas.append(delta)
            continue
        if event_type in {"response.failed", "error"}:
            failure = event.get("error")
            if isinstance(failure, dict):
                failure_message = str(failure.get("message") or "").strip() or None
            if not failure_message:
                failure_message = str(event.get("message") or "").strip() or "openai-codex request failed"
            continue
        if event_type == "response.completed":
            response_payload = event.get("response")
            if isinstance(response_payload, dict):
                completed_response = response_payload
    if failure_message:
        raise RuntimeError(failure_message)
    if completed_response is None:
        if deltas:
            return {"output_text": "".join(deltas)}
        raise RuntimeError("openai-codex returned no completed response")
    if deltas and not completed_response.get("output_text"):
        completed_response = {**completed_response, "output_text": "".join(deltas)}
    return completed_response



def _extract_response_text(payload: dict[str, Any]) -> str:
    direct_text = payload.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    output = payload.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type") or "").strip()
                if block_type == "output_text":
                    text = str(block.get("text") or "").strip()
                    if text:
                        parts.append(text)
                elif block_type == "refusal":
                    refusal = str(block.get("refusal") or "").strip()
                    if refusal:
                        parts.append(refusal)
        joined = "\n".join(part for part in parts if part).strip()
        if joined:
            return joined

    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    raise RuntimeError("openai-codex returned no assistant text")
