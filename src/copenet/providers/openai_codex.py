"""OpenAI Codex subscription-backed provider for CopeNet-controlled harness use."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncIterator

from copenet.core.provider_auth import OPENAI_CODEX_PROVIDER_ID, OpenAICodexAuthService
from copenet.providers.base import ProviderEvent, ProviderModel
from .codex_transport import stream_responses

logger = logging.getLogger(__name__)

OPENAI_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
OPENAI_CODEX_MODELS = ("gpt-5.5", "gpt-5.4")
OPENAI_CODEX_DEFAULT_MODEL = OPENAI_CODEX_MODELS[0]
OPENAI_CODEX_ORIGINATOR = "copenet"


def _resolve_instructions(instructions: str | None) -> str | None:
    """Return caller-owned instructions, or None — never an invented identity.

    The orchestrator owns profile/Access composition for every transport. A
    provider that substituted its own persona here would give the same session a
    different identity depending on which lane it entered through, so an empty
    value is passed through as "no instructions" and logged instead.
    """
    resolved = (instructions or "").strip()
    if resolved:
        return resolved
    logger.warning(
        "openai-codex received no instructions; sending the request without them. "
        "The caller should compose profile/Access text before reaching the provider."
    )
    return None


class OpenAICodexProvider:
    name = OPENAI_CODEX_PROVIDER_ID
    display_name = "OpenAI Codex"

    def __init__(
        self, auth_service: OpenAICodexAuthService | None = None, base_url: str = OPENAI_CODEX_BASE_URL
    ) -> None:
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
                for event in stream_responses(
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
                if not (item.metadata or {}).get("responsesCompleted"):
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
                for event in stream_responses(
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
    safe_input = (
        _sanitize_input_function_names(list(messages))
        if messages
        else [{"role": "user", "content": [{"type": "input_text", "text": " "}]}]
    )
    payload: dict[str, Any] = {
        "model": model,
        "input": safe_input,
        "store": False,
        "stream": True,
    }
    resolved_instructions = _resolve_instructions(instructions)
    if resolved_instructions:
        payload["instructions"] = resolved_instructions
    if tools:
        # Sanitize tool names at the boundary too (defense-in-depth; they normally
        # arrive pre-sanitized from build_responses_tool_schemas).
        payload["tools"] = [
            (
                {**tool, "name": _responses_safe_name(str(tool["name"]))}
                if isinstance(tool, dict) and tool.get("name")
                else tool
            )
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
    resolved_instructions = _resolve_instructions(system_prompt)
    if resolved_instructions:
        payload["instructions"] = resolved_instructions
    return payload
