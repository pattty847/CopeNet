"""Unit tests for Phase 1 message-history assembly (HARNESS_REBUILD_V2)."""

from __future__ import annotations

from copenet.core.orchestrator.messages import (
    build_chat_messages,
    estimate_input_tokens,
    flatten_messages_to_prompt,
    trim_messages_to_token_budget,
)


def test_build_chat_messages_appends_current_user_message_last() -> None:
    messages = build_chat_messages(
        transcript_messages=[],
        current_user_message="hello there",
    )
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"][0]["text"] == "hello there"


def test_build_chat_messages_replays_prior_turns_with_tool_exchange() -> None:
    transcript = [
        {"role": "user", "content": "What is in foo.txt?"},
        {
            "role": "assistant",
            "runId": "run_a",
            "parts": [
                {
                    "kind": "tool_call",
                    "toolCall": {"callId": "call_a", "toolId": "files.read", "arguments": {"path": "foo.txt"}},
                },
                {
                    "kind": "tool_result",
                    "toolExecution": {"callId": "call_a", "toolId": "files.read", "summary": "Read foo.txt", "body": "Hello"},
                },
                {"kind": "text", "text": "It says Hello."},
            ],
            "content": "It says Hello.",
        },
    ]
    messages = build_chat_messages(
        transcript_messages=transcript,
        current_user_message="And bar.txt?",
    )
    # user, function_call, function_call_output, assistant message, new user
    assert [m.get("type") or m.get("role") for m in messages] == [
        "user",
        "function_call",
        "function_call_output",
        "message",
        "user",
    ]
    # function_call and output share the call_id (so the API can pair them).
    assert messages[1]["call_id"] == messages[2]["call_id"] == "call_a"
    assert messages[-1]["content"][0]["text"] == "And bar.txt?"


def test_replay_carries_real_tool_output_not_just_summary() -> None:
    """A prior tool result's actual output (replayOutput) must survive into the
    next turn's function_call_output, so multi-turn coding keeps what it read."""
    transcript = [
        {"role": "user", "content": "what is in foo.txt?"},
        {
            "role": "assistant",
            "runId": "r1",
            "parts": [
                {"kind": "tool_call", "toolCall": {"callId": "c1", "toolId": "files.read", "arguments": {"path": "foo.txt"}}},
                {
                    "kind": "tool_result",
                    "toolExecution": {
                        "callId": "c1",
                        "toolId": "files.read",
                        "summary": "Read file foo.txt.",  # terse — must NOT be what replays
                        "replayOutput": "line one\nline two\nimportant config value = 42",
                    },
                },
                {"kind": "text", "text": "foo.txt has a config value."},
            ],
            "content": "foo.txt has a config value.",
        },
    ]
    messages = build_chat_messages(transcript_messages=transcript, current_user_message="what was the config value?")
    fco = next(m for m in messages if m.get("type") == "function_call_output")
    assert "important config value = 42" in fco["output"]
    assert fco["output"] != "Read file foo.txt."


def test_flatten_messages_to_prompt_separates_history_from_live_request() -> None:
    transcript = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "runId": "r1", "content": "first answer"},
    ]
    messages = build_chat_messages(
        transcript_messages=transcript,
        current_user_message="second question",
    )
    prompt = flatten_messages_to_prompt(messages)
    assert "Conversation so far:" in prompt
    assert "user: first question" in prompt
    assert "assistant: first answer" in prompt
    assert "Current user request:\nsecond question" in prompt


def test_flatten_messages_first_turn_has_no_history_section() -> None:
    messages = build_chat_messages(transcript_messages=[], current_user_message="just this")
    prompt = flatten_messages_to_prompt(messages)
    assert "Conversation so far" not in prompt
    assert "Current user request:\njust this" in prompt


def test_flatten_messages_renders_tool_exchange_readably() -> None:
    transcript = [
        {"role": "user", "content": "read it"},
        {
            "role": "assistant",
            "runId": "r1",
            "parts": [
                {"kind": "tool_call", "toolCall": {"callId": "c1", "toolId": "files.read", "arguments": {"path": "x"}}},
                {"kind": "tool_result", "toolExecution": {"callId": "c1", "summary": "Read x", "body": "contents"}},
                {"kind": "text", "text": "done"},
            ],
            "content": "done",
        },
    ]
    messages = build_chat_messages(transcript_messages=transcript, current_user_message="next")
    prompt = flatten_messages_to_prompt(messages)
    assert "assistant called files.read" in prompt
    assert "tool result: contents" in prompt


def test_estimate_input_tokens_is_roughly_char_quarter() -> None:
    messages = [{"role": "user", "content": [{"type": "input_text", "text": "a" * 400}]}]
    assert estimate_input_tokens(messages) == 100


def test_token_budget_drops_oldest_complete_turns_and_keeps_tool_pairs() -> None:
    messages = [
        {"role": "user", "content": [{"type": "input_text", "text": "A" * 80}]},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "B" * 80}]},
        {"role": "user", "content": [{"type": "input_text", "text": "read recent"}]},
        {
            "type": "function_call",
            "call_id": "call-1",
            "name": "files_read",
            "arguments": '{"path":"x"}',
        },
        {"type": "function_call_output", "call_id": "call-1", "output": "C" * 80},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "recent answer"}]},
        {"role": "user", "content": [{"type": "input_text", "text": "current"}]},
    ]

    trimmed = trim_messages_to_token_budget(messages, max_context_tokens=20)

    assert trimmed == [messages[-1]]

    with_recent_turn = trim_messages_to_token_budget(messages, max_context_tokens=50)
    assert [item.get("type") for item in with_recent_turn] == [
        None,
        "function_call",
        "function_call_output",
        "message",
        None,
    ]
    assert with_recent_turn[1]["call_id"] == with_recent_turn[2]["call_id"] == "call-1"


def test_token_budget_always_keeps_oversized_current_turn() -> None:
    messages = [
        {"role": "user", "content": [{"type": "input_text", "text": "old"}]},
        {"role": "user", "content": [{"type": "input_text", "text": "X" * 1000}]},
    ]

    trimmed = trim_messages_to_token_budget(messages, max_context_tokens=10)

    assert trimmed == [messages[-1]]
