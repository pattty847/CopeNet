"""Responses protocol state: terminal authorization and item-scoped output."""

from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field
from http.client import IncompleteRead
from typing import Any, Iterator
from .base import ProviderEvent, resolved_model_event

_REASONING_DELTAS = {
    "response.reasoning_summary.delta": "summary",
    "response.reasoning_summary_text.delta": "summary",
    "response.reasoning_text.delta": "raw",
    "response.reasoning.delta": "summary",
}


def failure_message(event: dict) -> str:
    response = event.get("response") or {}
    error = event.get("error") or response.get("error") or {}
    return error.get("message") or event.get("message") or "openai-codex request failed"


def decode_event(raw: bytes | str) -> dict | None:
    line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data or data == "[DONE]":
        return None
    try:
        event = json.loads(data)
    except json.JSONDecodeError as exc:
        raise RuntimeError("openai-codex returned malformed SSE data") from exc
    if not isinstance(event, dict):
        raise RuntimeError("openai-codex returned invalid SSE data")
    return event


@dataclass
class ResponseState:
    calls: dict[str, dict[str, str]] = field(default_factory=dict)
    completed_calls: set[str] = field(default_factory=set)
    reasoning_text: dict[tuple[str, str, int], str] = field(default_factory=dict)
    text_items: set[str] = field(default_factory=set)
    saw_text_delta: bool = False
    announced_model: bool = False

    def reasoning_delta(self, event: dict) -> Iterator[ProviderEvent]:
        source = _REASONING_DELTAS[event["type"]]
        delta = event.get("delta", "")
        if not isinstance(delta, str):
            raise RuntimeError("openai-codex returned invalid reasoning text")
        if delta:
            key = (
                event.get("item_id", ""),
                source,
                event.get("summary_index", event.get("content_index", 0)),
            )
            self.reasoning_text[key] = self.reasoning_text.get(key, "") + delta
            yield ProviderEvent(
                kind="reasoning_delta",
                text=delta,
                metadata={"reasoningSource": source, "providerEventType": event["type"]},
            )

    def reasoning_item(self, item: dict) -> Iterator[ProviderEvent]:
        for field_name, source in (("summary", "summary"), ("content", "raw")):
            for index, block in enumerate(item.get(field_name, [])):
                text = block.get("text", "")
                key = (item.get("id", ""), source, index)
                streamed = self.reasoning_text.get(key, "")
                # A done item can complete a partially streamed summary. Emit
                # only its unseen suffix; a different item has a different key.
                suffix = text[len(streamed) :] if text.startswith(streamed) else text if not streamed else ""
                self.reasoning_text[key] = text
                if suffix:
                    yield ProviderEvent(
                        kind="reasoning_delta",
                        text=suffix,
                        metadata={
                            "reasoningSource": source,
                            "providerEventType": "response.output_item.done",
                        },
                    )

    def add_call(self, item: dict, *, complete: bool) -> None:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise RuntimeError("openai-codex function call has no item id")
        if item_id in self.completed_calls:
            return
        tracked = self.calls.get(item_id, {})
        call = {key: item.get(key) or tracked.get(key, "") for key in ("id", "call_id", "name", "arguments")}
        if not all(isinstance(value, str) for value in call.values()):
            raise RuntimeError("openai-codex returned invalid function call fields")
        self.calls[item_id] = call
        if complete:
            self.completed_calls.add(item_id)

    def output_item(self, item: dict) -> Iterator[ProviderEvent]:
        kind = item.get("type")
        if kind == "function_call":
            self.add_call(item, complete=True)
        elif kind == "reasoning":
            yield from self.reasoning_item(item)
        elif kind == "message":
            item_id = item.get("id", "")
            if not self.saw_text_delta and item_id not in self.text_items:
                for block in item.get("content", []):
                    text = block.get("text") if block.get("type") == "output_text" else block.get("refusal")
                    if text:
                        yield ProviderEvent(kind="delta", text=text)
            self.text_items.add(item_id)

    def consume(self, event: dict) -> Iterator[ProviderEvent]:
        event_type = event.get("type")
        if not self.announced_model:
            response = event.get("response")
            model = response.get("model") if isinstance(response, dict) else None
            announcement = resolved_model_event(model)
            if announcement is not None:
                self.announced_model = True
                yield announcement
        if event_type == "response.output_text.delta":
            delta = event.get("delta", "")
            if not isinstance(delta, str):
                raise RuntimeError("openai-codex returned invalid output text")
            if delta:
                self.saw_text_delta = True
                yield ProviderEvent(kind="delta", text=delta)
        elif event_type in _REASONING_DELTAS:
            yield from self.reasoning_delta(event)
        elif event_type == "response.output_item.added":
            item = event.get("item", {})
            if item.get("type") == "function_call":
                self.add_call(item, complete=False)
        elif event_type == "response.function_call_arguments.delta":
            call = self.calls.get(event.get("item_id"))
            if call is None:
                raise RuntimeError("openai-codex arguments have no matching function call")
            call["arguments"] += event.get("delta", "")
        elif event_type == "response.output_item.done":
            yield from self.output_item(event.get("item", {}))
        elif event_type in {"response.failed", "error"}:
            raise RuntimeError(failure_message(event))
        elif event_type == "response.incomplete":
            raise RuntimeError("openai-codex response incomplete")

    def finish(self, response: dict) -> Iterator[ProviderEvent]:
        if response.get("status", "completed") != "completed":
            raise RuntimeError("openai-codex response incomplete")
        for item in response.get("output", []):
            yield from self.output_item(item)
        # Added+deltas alone are not a completed function call. Recovery requires
        # an authoritative item in the successful terminal response's output.
        if set(self.calls) - self.completed_calls:
            raise RuntimeError("openai-codex response contains incomplete function calls")
        if not self.saw_text_delta and not self.text_items and response.get("output_text"):
            yield ProviderEvent(kind="delta", text=response["output_text"])
        for call in self.calls.values():
            if not call["name"] or not call["call_id"]:
                raise RuntimeError("openai-codex function call has no name or call id")
            try:
                arguments = json.loads(call["arguments"])
            except json.JSONDecodeError as exc:
                raise RuntimeError("openai-codex function call arguments are incomplete") from exc
            if not isinstance(arguments, dict):
                raise RuntimeError("openai-codex function call arguments must be an object")
        for call in self.calls.values():
            yield ProviderEvent(kind="meta", metadata={"responsesFunctionCall": dict(call)})
        yield ProviderEvent(kind="meta", metadata={"responsesCompleted": True})


def parse_responses_sse(*, response: Any, abort_event: asyncio.Event) -> Iterator[ProviderEvent]:
    state = ResponseState()
    try:
        for raw in response:
            if abort_event.is_set():
                return
            event = decode_event(raw)
            if event is None:
                continue
            yield from state.consume(event)
            if event.get("type") == "response.completed":
                yield from state.finish(event.get("response", {}))
                return
    except IncompleteRead as exc:
        if not abort_event.is_set():
            raise RuntimeError("openai-codex stream ended incomplete") from exc
    if not abort_event.is_set():
        raise RuntimeError("openai-codex stream ended incomplete")


def parse_responses_json(raw: str) -> Iterator[ProviderEvent]:
    response = json.loads(raw)
    if not isinstance(response, dict) or response.get("status") != "completed":
        raise RuntimeError("openai-codex JSON response incomplete")
    state = ResponseState()
    yield from state.consume({"type": "response.created", "response": response})
    yield from state.finish(response)
