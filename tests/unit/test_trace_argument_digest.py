from __future__ import annotations

from copenet.core.harness.tool_loop_common import ARGUMENT_VALUE_CHAR_LIMIT, argument_digest, trace_tool_requested


def test_short_arguments_ride_the_lifecycle_tier_verbatim() -> None:
    """A command or a path IS the trace — digesting it away would defeat the point."""
    digest = argument_digest({"command": "rg -n TODO src/", "cwd": "/repo", "timeoutSeconds": 30})
    assert digest == {"command": "rg -n TODO src/", "cwd": "/repo", "timeoutSeconds": 30}


def test_a_files_write_body_is_replaced_by_its_size() -> None:
    body = "x" * (ARGUMENT_VALUE_CHAR_LIMIT + 1)
    digest = argument_digest({"path": "src/app.py", "content": body})
    assert digest["path"] == "src/app.py"
    assert digest["content"] == {"chars": len(body), "omitted": True}


def test_collections_are_summarized_not_copied() -> None:
    digest = argument_digest({"paths": ["a", "b", "c"], "options": {"deep": True, "limit": 5}})
    assert digest["paths"] == {"itemCount": 3, "omitted": True}
    assert digest["options"] == {"keys": ["deep", "limit"], "omitted": True}


def test_trace_tool_requested_splits_the_digest_from_the_full_arguments() -> None:
    recorded: list[tuple[str, dict]] = []
    body = "y" * (ARGUMENT_VALUE_CHAR_LIMIT + 1)
    trace_tool_requested(
        lambda event, payload: recorded.append((event, payload or {})),
        tool_id="files.write",
        arguments={"path": "a.py", "content": body},
        step=2,
        call_id="call-1",
        flags={"native": True},
    )

    assert [event for event, _ in recorded] == ["tool_requested", "tool_arguments"]
    lifecycle = recorded[0][1]
    assert lifecycle["toolId"] == "files.write"
    assert lifecycle["step"] == 2
    assert lifecycle["callId"] == "call-1"
    assert lifecycle["native"] is True
    assert lifecycle["argumentsDigested"] is True
    assert lifecycle["arguments"]["content"] == {"chars": len(body), "omitted": True}
    # The full body survives on the debug-tier event, which the writer gates.
    assert recorded[1][1]["arguments"]["content"] == body


def test_trace_tool_requested_is_a_no_op_without_a_recorder() -> None:
    trace_tool_requested(
        None,
        tool_id="files.read",
        arguments={"path": "a.py"},
        step=1,
        call_id="call-1",
        flags={"native": False},
    )
