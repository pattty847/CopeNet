from copenet.core.orchestrator.run_events import _streaming_message_parts


def test_streaming_message_parts_omits_internal_replay_payloads() -> None:
    parts = [
        {
            "kind": "responses_item",
            "item": {"type": "reasoning", "encrypted_content": "opaque" * 1_000},
        },
        {
            "kind": "tool_result",
            "toolExecution": {
                "toolId": "files.read",
                "summary": "Read a file.",
                "replayOutput": "full file" * 1_000,
            },
        },
        {"kind": "text", "text": "Done."},
    ]

    assert _streaming_message_parts(parts) == [
        {
            "kind": "tool_result",
            "toolExecution": {"toolId": "files.read", "summary": "Read a file."},
        },
        {"kind": "text", "text": "Done."},
    ]
    assert parts[1]["toolExecution"]["replayOutput"].startswith("full file")


def test_final_message_parts_keep_narration_where_it_happened() -> None:
    from copenet.core.orchestrator.run_message_parts import _normalize_final_message_parts

    parts = [
        {"kind": "text", "text": "Let me look."},
        {"kind": "tool_call", "toolCall": {"toolId": "files.read", "callId": "c1"}},
        {"kind": "tool_result", "toolExecution": {"toolId": "files.read", "callId": "c1"}},
        {"kind": "text", "text": "Found it."},
    ]

    assert _normalize_final_message_parts(
        parts, assistant_text="Let me look.\n\nFound it."
    ) == parts


def test_final_message_parts_append_text_a_run_never_streamed_as_a_part() -> None:
    from copenet.core.orchestrator.run_message_parts import _normalize_final_message_parts

    tool_result = {"kind": "tool_result", "toolExecution": {"toolId": "files.read"}}

    assert _normalize_final_message_parts([tool_result], assistant_text="Done.") == [
        tool_result,
        {"kind": "text", "text": "Done."},
    ]
