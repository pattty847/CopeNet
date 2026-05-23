"""Unit tests for the openai-codex Responses SSE parser + payload builder (Phase 2)."""

from __future__ import annotations

import asyncio
import json

from copenet.providers.openai_codex import _build_responses_payload, _parse_responses_sse


def _sse(events: list[dict]) -> list[bytes]:
    return [f"data: {json.dumps(ev)}".encode("utf-8") for ev in events]


def test_build_responses_payload_includes_tools_cache_key_and_reasoning() -> None:
    payload = _build_responses_payload(
        model="gpt-5.5",
        messages=[{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
        instructions="be terse",
        tools=[{"type": "function", "name": "files.read", "description": "d", "parameters": {}}],
        prompt_cache_key="session-69",
        reasoning={"effort": "high", "summary": "auto"},
        parallel_tool_calls=True,
    )
    assert payload["model"] == "gpt-5.5"
    assert payload["stream"] is True
    assert payload["store"] is False
    assert payload["instructions"] == "be terse"
    assert payload["tools"][0]["name"] == "files.read"
    assert payload["parallel_tool_calls"] is True
    assert payload["tool_choice"] == "auto"
    assert payload["prompt_cache_key"] == "session-69"
    assert payload["reasoning"] == {"effort": "high", "summary": "auto"}
    assert payload["include"] == ["reasoning.encrypted_content"]


def test_build_responses_payload_omits_tools_when_none() -> None:
    payload = _build_responses_payload(
        model="gpt-5.5",
        messages=[],
        instructions=None,
        tools=None,
        prompt_cache_key=None,
        reasoning=None,
        parallel_tool_calls=True,
    )
    assert "tools" not in payload
    assert "prompt_cache_key" not in payload
    assert "reasoning" not in payload
    # Empty messages get a placeholder so the API doesn't reject the request.
    assert payload["input"]


def test_parse_responses_sse_emits_text_reasoning_and_function_call() -> None:
    events = _sse(
        [
            {"type": "response.reasoning_summary.delta", "delta": "let me think"},
            {"type": "response.output_text.delta", "delta": "Hello "},
            {"type": "response.output_text.delta", "delta": "there"},
            {
                "type": "response.output_item.added",
                "item": {"type": "function_call", "id": "fc_0", "call_id": "call_0", "name": "files.read", "arguments": ""},
            },
            {"type": "response.function_call_arguments.delta", "item_id": "fc_0", "delta": '{"path":'},
            {"type": "response.function_call_arguments.delta", "item_id": "fc_0", "delta": '"foo.txt"}'},
            {
                "type": "response.output_item.done",
                "item": {"type": "function_call", "id": "fc_0", "call_id": "call_0", "name": "files.read", "arguments": '{"path":"foo.txt"}'},
            },
            {"type": "response.completed", "response": {"id": "resp_0"}},
        ]
    )
    out = list(_parse_responses_sse(response=iter(events), abort_event=asyncio.Event()))
    kinds = [e.kind for e in out]
    assert "reasoning_delta" in kinds
    text = "".join(e.text or "" for e in out if e.kind == "delta")
    assert text == "Hello there"
    fcs = [e.metadata["responsesFunctionCall"] for e in out if e.kind == "meta" and e.metadata and e.metadata.get("responsesFunctionCall")]
    assert len(fcs) == 1
    assert fcs[0]["call_id"] == "call_0"
    assert fcs[0]["name"] == "files.read"
    assert json.loads(fcs[0]["arguments"]) == {"path": "foo.txt"}
    assert out[-1].metadata.get("responsesCompleted") is True


def test_parse_responses_sse_flushes_function_call_without_done() -> None:
    """A function_call that streamed added+deltas but no explicit done still flushes."""
    events = _sse(
        [
            {
                "type": "response.output_item.added",
                "item": {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "shell.exec", "arguments": ""},
            },
            {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": '{"command":"ls"}'},
            {"type": "response.completed", "response": {}},
        ]
    )
    out = list(_parse_responses_sse(response=iter(events), abort_event=asyncio.Event()))
    fcs = [e.metadata["responsesFunctionCall"] for e in out if e.kind == "meta" and e.metadata and e.metadata.get("responsesFunctionCall")]
    assert len(fcs) == 1
    assert fcs[0]["name"] == "shell.exec"
    assert json.loads(fcs[0]["arguments"]) == {"command": "ls"}


def test_parse_responses_sse_raises_on_failure_event() -> None:
    events = _sse([{"type": "response.failed", "error": {"message": "boom"}}])
    import pytest

    with pytest.raises(RuntimeError, match="boom"):
        list(_parse_responses_sse(response=iter(events), abort_event=asyncio.Event()))
