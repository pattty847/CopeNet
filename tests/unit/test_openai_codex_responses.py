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
    # Provider sanitizes dotted tool names at the API boundary.
    assert payload["tools"][0]["name"] == "files_read"
    assert payload["parallel_tool_calls"] is True
    assert payload["tool_choice"] == "auto"
    assert payload["prompt_cache_key"] == "session-69"
    assert payload["reasoning"] == {"effort": "high", "summary": "auto"}
    # Encrypted reasoning content is NOT requested by default (would require
    # replaying reasoning items across the tool loop's re-POSTs).
    assert "include" not in payload


def test_build_responses_payload_requests_encrypted_reasoning_only_on_opt_in() -> None:
    payload = _build_responses_payload(
        model="gpt-5.5",
        messages=[],
        instructions=None,
        tools=None,
        prompt_cache_key=None,
        reasoning={"effort": "high", "summary": "auto", "include_encrypted": True},
        parallel_tool_calls=True,
    )
    assert payload["include"] == ["reasoning.encrypted_content"]
    # The internal control key is stripped from what we send to the API.
    assert "include_encrypted" not in payload["reasoning"]


def test_build_responses_payload_sanitizes_dotted_function_names() -> None:
    """Live API rejects dotted function names (HTTP 400). The payload builder must
    sanitize both tools[] and input[] function_call names to ^[a-zA-Z0-9_-]+$."""
    payload = _build_responses_payload(
        model="gpt-5.5",
        messages=[
            {"role": "user", "content": [{"type": "input_text", "text": "read it"}]},
            {"type": "function_call", "id": "fc0", "call_id": "c0", "name": "files.read", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "c0", "output": "data"},
        ],
        instructions=None,
        tools=[{"type": "function", "name": "shell.exec", "description": "d", "parameters": {}}],
        prompt_cache_key=None,
        reasoning=None,
        parallel_tool_calls=True,
    )
    fc = next(item for item in payload["input"] if item.get("type") == "function_call")
    assert fc["name"] == "files_read"
    assert payload["tools"][0]["name"] == "shell_exec"
    # function_call_output pairs by call_id (no name to sanitize).
    fco = next(item for item in payload["input"] if item.get("type") == "function_call_output")
    assert fco["call_id"] == "c0"


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


def test_parse_responses_sse_matches_reasoning_delta_name_variants() -> None:
    """Reasoning summary deltas are matched name-agnostically (live event name
    for summaries is not pinned down)."""
    for ev_type in (
        "response.reasoning_summary.delta",
        "response.reasoning_summary_text.delta",
        "response.reasoning_text.delta",
        "response.reasoning.delta",
    ):
        events = _sse([{"type": ev_type, "delta": "mid-thought"}, {"type": "response.completed", "response": {}}])
        out = list(_parse_responses_sse(response=iter(events), abort_event=asyncio.Event()))
        assert any(e.kind == "reasoning_delta" and e.text == "mid-thought" for e in out), ev_type
        reasoning = next(e for e in out if e.kind == "reasoning_delta")
        expected_source = "raw" if ev_type == "response.reasoning_text.delta" else "summary"
        assert reasoning.metadata == {"reasoningSource": expected_source, "providerEventType": ev_type}


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


def test_parse_responses_sse_surfaces_reasoning_output_item() -> None:
    """The live endpoint delivers reasoning as an output item (not *.delta events),
    so output_item.done with type=reasoning must surface its summary as thinking."""
    events = _sse(
        [
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "reasoning",
                    "id": "rs_0",
                    "summary": [{"type": "summary_text", "text": "First I'll read the file."}],
                },
            },
            {
                "type": "response.output_item.done",
                "item": {"type": "function_call", "id": "fc_0", "call_id": "c0", "name": "files_read", "arguments": "{}"},
            },
            {"type": "response.completed", "response": {}},
        ]
    )
    out = list(_parse_responses_sse(response=iter(events), abort_event=asyncio.Event()))
    assert any(e.kind == "reasoning_delta" and "read the file" in (e.text or "") for e in out)
    assert any(e.kind == "meta" and e.metadata and e.metadata.get("responsesFunctionCall") for e in out)


def test_parse_responses_sse_does_not_double_emit_streamed_reasoning() -> None:
    """gpt-5.5 streams the summary as reasoning_summary_text.delta AND repeats
    the same text in a terminal output_item.done (type=reasoning). The parser
    must emit it once — the output-item path is a fallback only for turns that
    send the item with no deltas. Regression for duplicated thinking blocks in
    the chat UI."""
    events = _sse(
        [
            {"type": "response.reasoning_summary_text.delta", "delta": "First I'll "},
            {"type": "response.reasoning_summary_text.delta", "delta": "read the file."},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "reasoning",
                    "id": "rs_0",
                    "summary": [{"type": "summary_text", "text": "First I'll read the file."}],
                },
            },
            {"type": "response.completed", "response": {}},
        ]
    )
    out = list(_parse_responses_sse(response=iter(events), abort_event=asyncio.Event()))
    reasoning = [e for e in out if e.kind == "reasoning_delta"]
    # Two streamed deltas, and the redundant output_item must be suppressed.
    assert len(reasoning) == 2
    assert "".join(e.text or "" for e in reasoning) == "First I'll read the file."


def test_parse_responses_sse_raises_on_failure_event() -> None:
    events = _sse([{"type": "response.failed", "error": {"message": "boom"}}])
    import pytest

    with pytest.raises(RuntimeError, match="boom"):
        list(_parse_responses_sse(response=iter(events), abort_event=asyncio.Event()))


def test_classify_responses_body_sniffs_sse_when_header_missing() -> None:
    """Live codex backend sometimes returns SSE bodies with an empty
    Content-Type header. The classifier must sniff the first non-blank line
    and dispatch to the SSE parser so function_call events aren't dropped.
    Regression for the "openai-codex returned no assistant text" failure mode.
    """
    from io import BytesIO
    from copenet.providers.openai_codex import _classify_responses_body, _parse_responses_sse

    body = (
        b"\n"
        b"event: response.output_item.done\n"
        b"data: " + json.dumps({
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_1",
                "name": "files_read",
                "arguments": "{\"path\":\"README.md\"}",
            },
        }).encode("utf-8") + b"\n"
        b"event: response.completed\n"
        b"data: " + json.dumps({"type": "response.completed"}).encode("utf-8") + b"\n"
    )

    class _LineStream:
        def __init__(self, raw: bytes) -> None:
            self._buf = BytesIO(raw)
        def readline(self) -> bytes:
            return self._buf.readline()
        def read(self) -> bytes:
            return self._buf.read()
        def __iter__(self):
            for line in self._buf:
                yield line

    kind, payload = _classify_responses_body(_LineStream(body), content_type="")
    assert kind == "sse"
    events = list(_parse_responses_sse(response=payload, abort_event=asyncio.Event()))
    assert any(
        e.kind == "meta" and e.metadata and isinstance(e.metadata.get("responsesFunctionCall"), dict)
        and e.metadata["responsesFunctionCall"].get("name") == "files_read"
        for e in events
    )


def test_classify_responses_body_returns_json_for_non_sse() -> None:
    from io import BytesIO
    from copenet.providers.openai_codex import _classify_responses_body

    class _LineStream:
        def __init__(self, raw: bytes) -> None:
            self._buf = BytesIO(raw)
        def readline(self) -> bytes:
            return self._buf.readline()
        def read(self) -> bytes:
            return self._buf.read()
        def __iter__(self):
            for line in self._buf:
                yield line

    body = b'{"output_text":"hi"}'
    kind, payload = _classify_responses_body(_LineStream(body), content_type="application/json")
    assert kind == "json"
    assert "output_text" in payload
