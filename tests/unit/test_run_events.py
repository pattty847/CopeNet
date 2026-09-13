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
