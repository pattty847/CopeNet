"""LM Studio provider: local models over LM Studio's OpenAI Responses endpoint.

LM Studio serves `/v1/responses` with custom function tools and
`function_call_output` replay, so this lane runs on the same harness tool loop as
openai-codex instead of a loop of its own. The model catalog comes from LM
Studio's native REST API (`/api/v1/models`), which reports what the Responses
endpoint does not: which models are loaded and the context length they were
loaded with.

The server may run on another machine (a GPU box on the tailnet). Set
`COPNET_LM_STUDIO_BASE_URL` and turn on "Serve on Local Network" in LM Studio.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterator, Iterator
from urllib import error, request

from .base import ProviderEvent, ProviderModel
from .responses_stream import (
    classify_responses_body,
    parse_responses_json,
    parse_responses_sse,
    sanitize_input_function_names,
)

LM_STUDIO_PROVIDER_ID = "lm-studio"
LM_STUDIO_DEFAULT_BASE_URL = "http://127.0.0.1:1234"

# describe() runs inside the providers.list bootstrap call, so an unreachable
# server (a GPU box that is switched off) must fail fast rather than stall the UI.
CATALOG_TIMEOUT_SEC = 2.0
# A local model can spend minutes on prompt processing before the first token.
RESPONSE_TIMEOUT_SEC = 600.0

_CAPABILITIES = {
    "chat": True,
    "embeddings": False,
    "toolCalls": False,
    "promptedToolUse": False,
    "streaming": True,
    "resume": False,
    "responsesApi": True,
}


class LmStudioProvider:
    name = LM_STUDIO_PROVIDER_ID
    display_name = "LM Studio"

    def __init__(self, base_url: str | None = None) -> None:
        resolved = base_url or os.environ.get("COPNET_LM_STUDIO_BASE_URL") or LM_STUDIO_DEFAULT_BASE_URL
        self._base_url = resolved.rstrip("/")

    async def describe(self) -> dict[str, object]:
        meta: dict[str, object] = {
            "id": self.name,
            "displayName": self.display_name,
            "supportsModelSelection": True,
            "requiresAuth": False,
            "authType": "none",
            "baseUrl": self._base_url,
            "capabilities": dict(_CAPABILITIES),
        }
        try:
            models = await self.list_models()
        except Exception as exc:
            return {**meta, "available": False, "modelCount": 0, "error": _unreachable_message(self._base_url, exc)}
        return {
            **meta,
            "available": True,
            "modelCount": len(models),
            "defaultModel": _default_model_id(models),
            "loadedModels": [
                {"id": model.id, "contextLength": model.metadata["loadedContextLength"]}
                for model in models
                if model.metadata and model.metadata.get("loaded")
            ],
        }

    async def list_models(self) -> list[ProviderModel]:
        data = await asyncio.to_thread(_get_json, f"{self._base_url}/api/v1/models", CATALOG_TIMEOUT_SEC)
        rows = data.get("models") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError("LM Studio returned an invalid model list")
        return [_model_from_row(row, self.name) for row in rows if isinstance(row, dict) and row.get("type") == "llm" and row.get("key")]

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        """Plain chat turn (no tools): one user input over the Responses endpoint."""
        messages = [{"role": "user", "content": [{"type": "input_text", "text": prompt if prompt.strip() else " "}]}]
        async for event in self.stream_responses(
            messages=messages,
            tools=None,
            model=model,
            instructions=system_prompt,
            abort_event=abort_event,
        ):
            if not (event.metadata or {}).get("responsesCompleted"):
                yield event
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
        """Stream one Responses turn; same event vocabulary as openai-codex.

        `prompt_cache_key` and `reasoning` are accepted for the loop's contract and
        not sent: LM Studio keeps its own prompt cache per loaded model, and the
        reasoning parameter is model-specific there, so sending the Codex default to
        an arbitrary local model would be a guess.
        """
        if abort_event.is_set():
            return
        payload = build_responses_payload(
            model=model or await self._default_model(),
            messages=messages,
            instructions=instructions,
            tools=tools,
            parallel_tool_calls=parallel_tool_calls,
        )
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[ProviderEvent | Exception | object] = asyncio.Queue()
        done_marker = object()

        def worker() -> None:
            try:
                for event in _post_responses(f"{self._base_url}/v1/responses", payload, abort_event):
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

    async def _default_model(self) -> str:
        model_id = _default_model_id(await self.list_models())
        if model_id is None:
            raise RuntimeError("LM Studio has no chat models downloaded.")
        return model_id


def build_responses_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    instructions: str | None,
    tools: list[dict[str, Any]] | None,
    parallel_tool_calls: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "input": list(messages) or [{"role": "user", "content": [{"type": "input_text", "text": " "}]}],
        "stream": True,
    }
    if instructions and instructions.strip():
        payload["instructions"] = instructions.strip()
    if tools:
        # Tool names arrive Responses-safe from build_responses_tool_schemas, and the
        # loop maps them back to dotted ids. Replayed function_call items carry the
        # dotted id, so sanitize those the same way openai-codex does.
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
        payload["parallel_tool_calls"] = bool(parallel_tool_calls)
        payload["input"] = sanitize_input_function_names(payload["input"])
    return payload


def _model_from_row(row: dict[str, Any], provider: str) -> ProviderModel:
    instances = [inst for inst in row.get("loaded_instances") or [] if isinstance(inst, dict)]
    capabilities = row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {}
    loaded_context = next(
        (inst["config"]["context_length"] for inst in instances if isinstance((inst.get("config") or {}).get("context_length"), int)),
        None,
    )
    model_id = str(row["key"])
    return ProviderModel(
        id=model_id,
        display_name=str(row.get("display_name") or model_id),
        provider=provider,
        kind="chat",
        capabilities=dict(_CAPABILITIES),
        recommended_for=["chat"],
        metadata={
            "publisher": row.get("publisher"),
            "loaded": bool(instances),
            # The budget reads this key. A loaded model answers within the context it
            # was LOADED with (LM Studio's default is 4096), not the architecture's
            # maximum, so the loaded value wins whenever there is one.
            "maxContextLength": loaded_context or row.get("max_context_length"),
            "loadedContextLength": loaded_context,
            "architectureMaxContextLength": row.get("max_context_length"),
            "trainedForToolUse": capabilities.get("trained_for_tool_use"),
            "vision": capabilities.get("vision"),
        },
    )


def _default_model_id(models: list[ProviderModel]) -> str | None:
    loaded = next((model.id for model in models if model.metadata and model.metadata.get("loaded")), None)
    return loaded or (models[0].id if models else None)


def _get_json(url: str, timeout_sec: float) -> Any:
    req = request.Request(url, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_responses(url: str, payload: dict[str, Any], abort_event: asyncio.Event) -> Iterator[ProviderEvent]:
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=RESPONSE_TIMEOUT_SEC) as response:
            kind, body = classify_responses_body(response, str(response.headers.get("Content-Type") or ""))
            if kind == "sse":
                yield from parse_responses_sse(response=body, abort_event=abort_event, label=LM_STUDIO_PROVIDER_ID)
            elif not abort_event.is_set():
                yield from parse_responses_json(body, label=LM_STUDIO_PROVIDER_ID)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"lm-studio request failed ({exc.code}): {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"lm-studio transport error: {exc.reason}") from exc


def _unreachable_message(base_url: str, exc: Exception) -> str:
    reason = getattr(exc, "reason", None) or exc
    return (
        f"LM Studio is not reachable at {base_url} ({reason}). Start its server, or on another "
        "machine enable Serve on Local Network and set COPNET_LM_STUDIO_BASE_URL."
    )
