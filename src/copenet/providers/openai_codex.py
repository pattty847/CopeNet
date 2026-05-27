"""OpenAI Codex subscription-backed provider for CopeNet-controlled harness use."""

from __future__ import annotations

import asyncio
import json
import re
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
                # Phase 2 (HARNESS_REBUILD_V2): native Responses-API tool loop.
                "responsesApi": True,
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
                    "responsesApi": True,
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

    async def stream_responses(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
        instructions: str | None,
        prompt_cache_key: str | None = None,
        reasoning: dict[str, Any] | None = None,
        parallel_tool_calls: bool = True,
        abort_event: asyncio.Event,
    ) -> AsyncIterator[ProviderEvent]:
        """Stream one Responses-API turn over a pre-built input[] array.

        Yields the Phase 2 event vocabulary (verified against PASS-7):
          - kind="delta"            assistant output_text deltas
          - kind="reasoning_delta"  reasoning_summary deltas
          - kind="meta" metadata={"responsesFunctionCall": {id, call_id, name, arguments}}
              one per completed function_call output item
          - kind="meta" metadata={"responsesCompleted": True}  at response.completed

        The harness tool loop owns the messages[] array, executes the calls, and
        re-invokes this method with function_call / function_call_output items
        appended. This method does NOT loop — it streams a single response.
        """
        if abort_event.is_set():
            return
        profile = await asyncio.to_thread(self.auth_service.ensure_valid_profile)
        payload = _build_responses_payload(
            model=_resolve_model(model),
            messages=messages,
            instructions=instructions,
            tools=tools,
            prompt_cache_key=prompt_cache_key,
            reasoning=reasoning,
            parallel_tool_calls=parallel_tool_calls,
        )
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[ProviderEvent | Exception | object] = asyncio.Queue()
        done_marker = object()

        def worker() -> None:
            try:
                for event in _stream_responses_tool_events(
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



def _resolve_model(model: str | None) -> str:
    normalized = str(model or "").strip() or OPENAI_CODEX_DEFAULT_MODEL
    if normalized not in OPENAI_CODEX_MODELS:
        supported = ", ".join(OPENAI_CODEX_MODELS)
        raise ValueError(f"unsupported openai-codex model: {normalized}. Supported models: {supported}")
    return normalized



# Responses function names must match ^[a-zA-Z0-9_-]+$ (dots rejected — confirmed
# live with HTTP 400). Must match copenet.core.tools.contracts.responses_safe_tool_name;
# duplicated here as a one-liner to avoid a providers <-> core.tools import cycle.
_RESPONSES_NAME_INVALID = re.compile(r"[^a-zA-Z0-9_-]")


def _responses_safe_name(name: str) -> str:
    return _RESPONSES_NAME_INVALID.sub("_", name)


def _sanitize_input_function_names(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return input[] with every function_call item's name made Responses-safe.

    The messages array carries canonical dotted tool ids (for flatten/display);
    only the names actually sent to the API are sanitized here. function_call and
    function_call_output pair by call_id, not name, so this is safe.
    """
    out: list[dict[str, Any]] = []
    for item in messages:
        if isinstance(item, dict) and item.get("type") == "function_call" and item.get("name"):
            item = {**item, "name": _responses_safe_name(str(item["name"]))}
        out.append(item)
    return out


def _reasoning_item_text(item: dict[str, Any]) -> str:
    """Extract human-readable summary text from a Responses reasoning output item.

    Standard shape is {type: "reasoning", summary: [{type: "summary_text",
    text: ...}, ...]}. Some variants use `content` or plain `text`. Best-effort
    across them; needs confirmation against a real substantive turn (the trivial
    probe turns produced a reasoning item but its summary may be empty).
    """
    for key in ("summary", "content"):
        blocks = item.get(key)
        if isinstance(blocks, list):
            parts: list[str] = []
            for block in blocks:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                elif isinstance(block, str) and block.strip():
                    parts.append(block.strip())
            if parts:
                return "\n".join(parts)
    text = item.get("text")
    return text.strip() if isinstance(text, str) and text.strip() else ""


def _build_responses_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    instructions: str | None,
    tools: list[dict[str, Any]] | None,
    prompt_cache_key: str | None,
    reasoning: dict[str, Any] | None,
    parallel_tool_calls: bool,
) -> dict[str, Any]:
    safe_input = _sanitize_input_function_names(list(messages)) if messages else [
        {"role": "user", "content": [{"type": "input_text", "text": " "}]}
    ]
    payload: dict[str, Any] = {
        "model": model,
        "input": safe_input,
        "store": False,
        "stream": True,
    }
    payload["instructions"] = (instructions or "").strip() or OPENAI_CODEX_DEFAULT_INSTRUCTIONS
    if tools:
        # Sanitize tool names at the boundary too (defense-in-depth; they normally
        # arrive pre-sanitized from build_responses_tool_schemas).
        payload["tools"] = [
            ({**tool, "name": _responses_safe_name(str(tool["name"]))} if isinstance(tool, dict) and tool.get("name") else tool)
            for tool in tools
        ]
        payload["parallel_tool_calls"] = bool(parallel_tool_calls)
        payload["tool_choice"] = "auto"
    if prompt_cache_key:
        payload["prompt_cache_key"] = prompt_cache_key
    if reasoning:
        # Strip our internal control key before sending to the API.
        reasoning_payload = {k: v for k, v in reasoning.items() if k != "include_encrypted"}
        payload["reasoning"] = reasoning_payload
        # Only request encrypted reasoning content when explicitly opted in. With
        # store=false + a multi-step tool loop, requesting it creates an
        # obligation to replay reasoning items on each re-POST (which the loop
        # does not do). Default off: we still get reasoning_summary deltas for the
        # thinking UX, and the model simply re-reasons per step.
        if reasoning.get("include_encrypted"):
            payload["include"] = ["reasoning.encrypted_content"]
    return payload


def _stream_responses_tool_events(
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
            kind, payload = _classify_responses_body(response, content_type)
            if kind == "sse":
                yield from _parse_responses_sse(response=payload, abort_event=abort_event)
                return
            # Non-SSE (JSON or empty) — emit text + function_call from the parsed body.
            data = _decode_openai_codex_response_body(raw_body=payload, content_type=content_type) if payload else {}
            yield from _emit_responses_nonstream_events(data)
            yield ProviderEvent(kind="meta", metadata={"responsesCompleted": True})
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if exc.code in {401, 403}:
            raise RuntimeError(
                "openai-codex authentication failed. Re-run `uv run copenet auth login --provider openai-codex`."
            ) from exc
        raise RuntimeError(f"openai-codex request failed ({exc.code}): {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"openai-codex transport error: {exc.reason}") from exc


def _parse_responses_sse(*, response: Any, abort_event: asyncio.Event) -> Iterator[ProviderEvent]:
    """Parse the Responses SSE stream into harness ProviderEvents.

    Tracks the function_call lifecycle:
      response.output_item.added (item.type=function_call) -> register by item id
      response.function_call_arguments.delta                -> accumulate arguments
      response.output_item.done (item.type=function_call)   -> emit responsesFunctionCall
    """
    pending_calls: dict[str, dict[str, str]] = {}
    completed = False
    for raw in _iter_sse_lines(response):
        if abort_event.is_set():
            break
        if not raw.startswith("data:"):
            continue
        data = raw[5:].strip()
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
                yield ProviderEvent(kind="delta", text=delta)
            continue
        # Reasoning summary deltas: be name-agnostic. The live codex endpoint did
        # not emit reasoning events for trivial probe turns, and the exact event
        # name for summaries is not pinned down, so match any reasoning delta
        # variant (reasoning_summary.delta / reasoning_summary_text.delta /
        # reasoning_text.delta / reasoning.delta).
        if event_type.startswith("response.reasoning") and event_type.endswith(".delta"):
            delta = str(event.get("delta") or "")
            if delta:
                yield ProviderEvent(kind="reasoning_delta", text=delta)
            continue
        if event_type == "response.output_item.added":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "function_call":
                item_id = str(item.get("id") or "").strip()
                pending_calls[item_id] = {
                    "id": item_id,
                    "call_id": str(item.get("call_id") or "").strip(),
                    "name": str(item.get("name") or "").strip(),
                    "arguments": str(item.get("arguments") or ""),
                }
            continue
        if event_type == "response.function_call_arguments.delta":
            item_id = str(event.get("item_id") or "").strip()
            tracked = pending_calls.get(item_id)
            if tracked is not None:
                tracked["arguments"] = (tracked.get("arguments") or "") + str(event.get("delta") or "")
            continue
        if event_type == "response.output_item.done":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "function_call":
                item_id = str(item.get("id") or "").strip()
                tracked = pending_calls.pop(item_id, None) or {}
                final_args = str(item.get("arguments") or "").strip() or tracked.get("arguments") or ""
                call = {
                    "id": item_id or tracked.get("id") or "",
                    "call_id": str(item.get("call_id") or "").strip() or tracked.get("call_id") or item_id,
                    "name": str(item.get("name") or "").strip() or tracked.get("name") or "",
                    "arguments": final_args,
                }
                if call["name"]:
                    yield ProviderEvent(kind="meta", metadata={"responsesFunctionCall": call})
            elif isinstance(item, dict) and item.get("type") == "reasoning":
                # The live endpoint delivers reasoning as an output ITEM (no
                # streamed *.delta events for it — confirmed via probe scenario D,
                # which showed a 2nd output_item but zero reasoning_summary.delta).
                # Surface its summary text as a single reasoning_delta for the
                # inline-thinking UX.
                summary_text = _reasoning_item_text(item)
                if summary_text:
                    yield ProviderEvent(kind="reasoning_delta", text=summary_text)
            continue
        if event_type in {"response.failed", "error"}:
            raise RuntimeError(_openai_codex_failure_message(event))
        if event_type == "response.completed":
            completed = True
            break

    # Flush any function_call that streamed added+deltas but no explicit done.
    for call in pending_calls.values():
        if call.get("name"):
            yield ProviderEvent(kind="meta", metadata={"responsesFunctionCall": dict(call)})
    yield ProviderEvent(kind="meta", metadata={"responsesCompleted": completed})


def _classify_responses_body(response: Any, content_type: str) -> tuple[str, Any]:
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
        text_line = line.decode("utf-8", errors="replace") if isinstance(line, (bytes, bytearray)) else str(line)
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


def _emit_responses_nonstream_events(data: dict[str, Any]) -> Iterator[ProviderEvent]:
    """Emit text + function_call events from a non-streamed Responses payload.

    Mirrors what ``_parse_responses_sse`` would yield: ``delta`` for assistant
    text, ``meta.responsesFunctionCall`` for each function_call output item.
    """
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip()
            if item_type == "message":
                content = item.get("content")
                if isinstance(content, list):
                    parts: list[str] = []
                    for block in content:
                        if isinstance(block, dict) and str(block.get("type") or "") == "output_text":
                            text = str(block.get("text") or "")
                            if text:
                                parts.append(text)
                    joined = "".join(parts)
                    if joined:
                        yield ProviderEvent(kind="delta", text=joined)
            elif item_type == "function_call":
                call = {
                    "id": str(item.get("id") or "").strip(),
                    "call_id": str(item.get("call_id") or "").strip() or str(item.get("id") or ""),
                    "name": str(item.get("name") or "").strip(),
                    "arguments": str(item.get("arguments") or ""),
                }
                if call["name"]:
                    yield ProviderEvent(kind="meta", metadata={"responsesFunctionCall": call})
            elif item_type == "reasoning":
                summary_text = _reasoning_item_text(item)
                if summary_text:
                    yield ProviderEvent(kind="reasoning_delta", text=summary_text)
        return
    direct_text = data.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        yield ProviderEvent(kind="delta", text=direct_text.strip())


def _iter_sse_lines(response: Any) -> Iterator[str]:
    for raw in response:
        if isinstance(raw, (bytes, bytearray)):
            yield raw.decode("utf-8", errors="replace").strip()
        else:
            yield str(raw).strip()


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
