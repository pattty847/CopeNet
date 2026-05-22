"""Unit tests for the canonical Responses API item builders.

Verifies the exact shapes accepted by chatgpt.com/backend-api/codex/responses,
matching what PASS-7's live probe captured.
"""

from __future__ import annotations

import json

from copenet.core.harness.responses_items import (
    assistant_message_item,
    function_call_item,
    function_call_output_item,
    parts_to_response_items,
    transcript_to_input_array,
    user_input_item,
)


def test_user_input_item_matches_probed_shape() -> None:
    item = user_input_item("What's 2+2?")
    assert item == {
        "role": "user",
        "content": [{"type": "input_text", "text": "What's 2+2?"}],
    }


def test_assistant_message_item_matches_probed_shape() -> None:
    item = assistant_message_item(message_id="msg_test_0", text="4")
    assert item == {
        "type": "message",
        "role": "assistant",
        "id": "msg_test_0",
        "content": [{"type": "output_text", "text": "4", "annotations": []}],
        "status": "completed",
    }


def test_function_call_item_serializes_dict_arguments() -> None:
    item = function_call_item(
        item_id="fc_test_0",
        call_id="call_test_0",
        name="get_weather",
        arguments={"city": "San Francisco"},
    )
    assert item["type"] == "function_call"
    assert item["id"] == "fc_test_0"
    assert item["call_id"] == "call_test_0"
    assert item["name"] == "get_weather"
    # arguments must be a JSON string per Responses API contract
    assert isinstance(item["arguments"], str)
    assert json.loads(item["arguments"]) == {"city": "San Francisco"}


def test_function_call_item_passes_through_string_arguments() -> None:
    item = function_call_item(
        item_id="fc_test_0",
        call_id="call_test_0",
        name="read_file",
        arguments='{"path":"foo.txt"}',
    )
    assert item["arguments"] == '{"path":"foo.txt"}'


def test_function_call_output_item_matches_probed_shape() -> None:
    item = function_call_output_item(call_id="call_test_0", output="Hello, world!")
    assert item == {
        "type": "function_call_output",
        "call_id": "call_test_0",
        "output": "Hello, world!",
    }


def test_function_call_output_item_serializes_dict_output() -> None:
    item = function_call_output_item(call_id="call_test_0", output={"result": "ok", "value": 42})
    assert item["type"] == "function_call_output"
    assert item["call_id"] == "call_test_0"
    parsed = json.loads(item["output"])
    assert parsed == {"result": "ok", "value": 42}


def test_parts_to_response_items_emits_text_then_tool_exchange() -> None:
    parts = [
        {"kind": "text", "text": "Let me read the file."},
        {
            "kind": "tool_call",
            "toolCall": {"callId": "call_1", "toolId": "files.read", "arguments": {"path": "foo.txt"}},
        },
        {
            "kind": "tool_result",
            "toolExecution": {"callId": "call_1", "toolId": "files.read", "body": "Hello, world!"},
        },
        {"kind": "text", "text": "It says hello."},
    ]
    items = parts_to_response_items(parts, run_id="run_test")
    assert len(items) == 4
    assert items[0]["type"] == "message"
    assert items[0]["content"][0]["text"] == "Let me read the file."
    assert items[1]["type"] == "function_call"
    assert items[1]["call_id"] == "call_1"
    assert items[2]["type"] == "function_call_output"
    assert items[2]["call_id"] == "call_1"
    assert items[2]["output"] == "Hello, world!"
    assert items[3]["type"] == "message"
    assert items[3]["content"][0]["text"] == "It says hello."


def test_parts_to_response_items_skips_invalid_parts() -> None:
    parts = [
        {"kind": "text", "text": ""},  # empty text — skip
        {"kind": "tool_call", "toolCall": {}},  # no callId/toolId — skip
        {"kind": "tool_result", "toolExecution": {}},  # no callId — skip
        {"kind": "text", "text": "real text"},
    ]
    items = parts_to_response_items(parts, run_id="run_test")
    assert len(items) == 1
    assert items[0]["content"][0]["text"] == "real text"


def test_transcript_to_input_array_replays_full_conversation() -> None:
    # Transcript contains PAST turns only. The new user message is passed separately
    # and appended at the end — matches how runtime.py would call this.
    transcript = [
        {"role": "user", "content": "What's in foo.txt?"},
        {
            "role": "assistant",
            "run_id": "run_a",
            "parts": [
                {"kind": "tool_call", "toolCall": {"callId": "call_a", "toolId": "files.read", "arguments": {"path": "foo.txt"}}},
                {"kind": "tool_result", "toolExecution": {"callId": "call_a", "body": "Hello"}},
                {"kind": "text", "text": "It says Hello."},
            ],
            "content": "It says Hello.",
        },
    ]
    items = transcript_to_input_array(
        transcript_messages=transcript,
        current_user_message="And bar.txt?",
    )
    # user msg + (function_call + function_call_output + assistant text) + new user msg = 5
    assert len(items) == 5
    assert items[0]["role"] == "user"
    assert items[0]["content"][0]["text"] == "What's in foo.txt?"
    assert items[1]["type"] == "function_call"
    assert items[2]["type"] == "function_call_output"
    assert items[3]["type"] == "message" and items[3]["role"] == "assistant"
    assert items[4]["role"] == "user"
    assert items[4]["content"][0]["text"] == "And bar.txt?"


def test_transcript_to_input_array_falls_back_to_content_when_no_parts() -> None:
    """Legacy transcript messages without structured parts still replay via content."""
    transcript = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "run_id": "run_a", "content": "Hi there!"},
    ]
    items = transcript_to_input_array(
        transcript_messages=transcript,
        current_user_message="How are you?",
    )
    assert len(items) == 3
    assert items[1]["type"] == "message"
    assert items[1]["content"][0]["text"] == "Hi there!"


def test_tool_output_for_replay_prefers_body_string() -> None:
    """Tool output serialization: body string > body dict > summary > output."""
    parts = [
        {
            "kind": "tool_result",
            "toolExecution": {
                "callId": "c1",
                "body": "raw string body",
                "summary": "summary",
                "output": {"k": "v"},
            },
        }
    ]
    items = parts_to_response_items(parts, run_id="run_test")
    assert items[0]["output"] == "raw string body"


def test_tool_output_for_replay_serializes_dict_body() -> None:
    parts = [
        {
            "kind": "tool_result",
            "toolExecution": {
                "callId": "c1",
                "body": {"matches": [{"path": "foo.txt"}]},
            },
        }
    ]
    items = parts_to_response_items(parts, run_id="run_test")
    parsed = json.loads(items[0]["output"])
    assert parsed == {"matches": [{"path": "foo.txt"}]}


def test_tool_output_for_replay_falls_back_to_summary() -> None:
    parts = [
        {
            "kind": "tool_result",
            "toolExecution": {
                "callId": "c1",
                "summary": "Listed 3 entries.",
            },
        }
    ]
    items = parts_to_response_items(parts, run_id="run_test")
    assert items[0]["output"] == "Listed 3 entries."
