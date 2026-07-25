"""One model-facing tool-result shape, identical on every tool loop.

Phase 3 of docs/plans/CONTEXT_CONVEYOR_NEXT_STEPS.md. Before this, the native and
Responses loops sent only `result.body`, so a policy-blocked call carrying an
explicit reason reached the model as literally `{}` — indistinguishable from a
successful empty result, and typically retried verbatim.
"""

from __future__ import annotations

import json

import pytest

from copenet.core.harness.tool_loop_common import (
    _compact_tool_output_text,
    _native_tool_message_content,
)
from copenet.core.tools import ToolExecutionResult

BLOCKED = ToolExecutionResult(
    tool_id="shell.exec",
    call_id="call-1",
    ok=False,
    summary="blocked",
    error="approval required (ask mode): rm -rf /",
    output={},
)
SUCCEEDED = ToolExecutionResult(
    tool_id="files.read",
    call_id="call-2",
    ok=True,
    summary="Read foo.txt",
    body="Hello, world!",
)
EMPTY_SUCCESS = ToolExecutionResult(
    tool_id="files.rg",
    call_id="call-3",
    ok=True,
    summary="No matches",
    body={},
)


def _native(result: ToolExecutionResult) -> dict:
    return json.loads(_native_tool_message_content(result))


def _prompted(result: ToolExecutionResult) -> dict:
    return json.loads(result.to_prompt_payload())


@pytest.mark.parametrize("result", [BLOCKED, SUCCEEDED, EMPTY_SUCCESS])
def test_prompted_and_native_loops_send_the_same_envelope(result: ToolExecutionResult) -> None:
    assert _native(result) == _prompted(result) == result.to_model_payload()


def test_a_blocked_call_reaches_the_model_with_its_reason() -> None:
    envelope = _native(BLOCKED)

    assert envelope["ok"] is False
    assert envelope["error"] == "approval required (ask mode): rm -rf /"
    assert envelope["summary"] == "blocked"


def test_failure_is_distinguishable_from_a_successful_empty_result() -> None:
    """The exact confusion the old native envelope created: both used to be `{}`."""
    assert _native(BLOCKED) != _native(EMPTY_SUCCESS)
    assert _native(EMPTY_SUCCESS)["ok"] is True
    assert "error" not in _native(EMPTY_SUCCESS)


def test_successful_body_is_preserved_intact() -> None:
    assert _native(SUCCEEDED)["body"] == "Hello, world!"


def test_compaction_keeps_the_actionable_envelope_and_shrinks_only_the_body() -> None:
    fetched = ToolExecutionResult(
        tool_id="web.fetch",
        call_id="call-4",
        ok=True,
        summary="Fetched example.com",
        body={"url": "https://example.com", "title": "Example", "wordCount": 900, "text": "y" * 5000},
    )

    compacted = json.loads(_compact_tool_output_text(_native_tool_message_content(fetched)))

    assert compacted["ok"] is True
    assert compacted["summary"] == "Fetched example.com"
    assert compacted["toolId"] == "web.fetch"
    assert compacted["body"]["url"] == "https://example.com"
    assert len(compacted["body"]["excerpt"]) <= 280
    assert "y" * 5000 not in json.dumps(compacted)


def test_compaction_shrinks_an_unrecognized_body_rather_than_passing_it_through() -> None:
    bulky = ToolExecutionResult(
        tool_id="market.dashboard",
        call_id="call-5",
        ok=True,
        summary="Dashboard",
        body={"rows": ["z" * 100 for _ in range(200)]},
    )

    compacted = json.loads(_compact_tool_output_text(_native_tool_message_content(bulky)))

    assert compacted["ok"] is True
    assert len(json.dumps(compacted)) < 4000
