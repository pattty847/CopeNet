"""A response must complete before its tool calls can leave the parser."""

import asyncio
import json
import pytest
from copenet.providers.codex_responses import parse_responses_sse


def parse(events, abort=None):
    return list(
        parse_responses_sse(
            response=(f"data: {json.dumps(e)}".encode() for e in events), abort_event=abort or asyncio.Event()
        )
    )


def call(item_id="fc"):
    return {
        "type": "function_call",
        "id": item_id,
        "call_id": item_id,
        "name": "files_read",
        "arguments": '{"path":"README.md"}',
    }


@pytest.mark.parametrize("suffix", [[], [{"type": "response.incomplete"}]])
def test_incomplete_response_never_releases_calls(suffix):
    seen = []
    with pytest.raises(RuntimeError, match="incomplete"):
        for event in parse_responses_sse(
            response=(
                f"data: {json.dumps(e)}".encode()
                for e in [{"type": "response.output_item.done", "item": call()}, *suffix]
            ),
            abort_event=asyncio.Event(),
        ):
            seen.append(event)
    assert not any((e.metadata or {}).get("responsesFunctionCall") for e in seen)


def test_abort_discards_pending_calls():
    abort = asyncio.Event()

    def stream():
        yield f"data: {json.dumps({'type': 'response.output_item.added', 'item': call()})}".encode()
        abort.set()
        yield b'data: {"type":"response.completed"}'

    out = list(parse_responses_sse(response=stream(), abort_event=abort))
    assert not any((e.metadata or {}).get("responsesFunctionCall") for e in out)


def test_duplicate_item_done_releases_one_call():
    out = parse(
        [
            {"type": "response.output_item.done", "item": call()},
            {"type": "response.output_item.done", "item": call()},
            {"type": "response.completed"},
        ]
    )
    assert len([e for e in out if (e.metadata or {}).get("responsesFunctionCall")]) == 1


def test_reasoning_deduplication_is_per_item_and_summary_index():
    out = parse(
        [
            {
                "type": "response.reasoning_summary_text.delta",
                "item_id": "r1",
                "summary_index": 0,
                "delta": "first",
            },
            {
                "type": "response.output_item.done",
                "item": {"type": "reasoning", "id": "r2", "summary": [{"text": "second"}]},
            },
            {
                "type": "response.output_item.done",
                "item": {"type": "reasoning", "id": "r1", "summary": [{"text": "first"}, {"text": "third"}]},
            },
            {"type": "response.completed"},
        ]
    )
    assert [e.text for e in out if e.kind == "reasoning_delta"] == ["first", "second", "third"]
