"""Old turns replay read-only tool bodies as receipts; edits, failures, and the newest turn stay verbatim."""

from __future__ import annotations

import json

from copenet.core.harness.replay_receipts import MUTATION_TOOL_IDS, is_verbatim, replay_output
from copenet.core.harness.responses_items import transcript_to_input_array


def _execution(tool_id: str, body: dict, *, ok: bool = True, arguments: dict | None = None, error: str | None = None) -> dict:
    execution = {
        "toolId": tool_id,
        "ok": ok,
        "summary": f"{tool_id} summary",
        "callId": "call-1",
        "arguments": arguments or {},
        "replayOutput": json.dumps(body, indent=2),
    }
    if error:
        execution["error"] = error
    return execution


POLICY = {"target": "app.py", "workspaceRoot": "/tmp/ws", "scope": "inside_workspace", "accessAction": "read", "policyDecision": "allowed", "policySummary": "fine"}


def test_verbatim_replay_carries_the_live_envelope_without_policy_bookkeeping() -> None:
    execution = _execution("files.read", {"path": "app.py", "content": "VALUE = 1\n", "digest": "abcd", **POLICY})
    envelope = json.loads(replay_output(execution, receipt=False, turn_number=2))
    assert envelope["toolId"] == "files.read" and envelope["ok"] is True and envelope["summary"] == "files.read summary"
    assert envelope["body"]["content"] == "VALUE = 1\n"
    assert "workspaceRoot" not in envelope["body"] and "policySummary" not in envelope["body"]


def test_file_read_receipt_keeps_path_range_digest_and_drops_content() -> None:
    execution = _execution(
        "files.read",
        {"path": "app.py", "content": "SECRET" * 100, "digest": "abcd1234", "startLine": 1, "endLine": 40, "totalLines": 120, **POLICY},
        arguments={"path": "app.py", "start_line": 1, "end_line": 40},
    )
    envelope = json.loads(replay_output(execution, receipt=True, turn_number=1))
    body = envelope["body"]
    assert body["path"] == "app.py" and body["lines"] == "1-40 of 120" and body["digest"] == "abcd1234"
    assert "SECRET" not in json.dumps(envelope)
    assert "turn 1" in body["elided"] and "files.read again" in body["elided"]


def test_search_receipt_keeps_pattern_count_and_first_locations() -> None:
    matches = [{"path": f"m{i}.py", "line": i, "column": 1, "text": "needle here"} for i in range(8)]
    execution = _execution("files.rg", {"matches": matches, "totalMatches": 8, **POLICY}, arguments={"pattern": "needle", "path": "."})
    body = json.loads(replay_output(execution, receipt=True, turn_number=1))["body"]
    assert body["pattern"] == "needle" and body["totalMatches"] == 8
    assert body["matches"][:2] == ["m0.py:0", "m1.py:1"] and body["matches"][-1] == "… 3 more"
    assert "needle here" not in json.dumps(body)


def test_shell_receipt_keeps_command_exit_code_and_head_tail() -> None:
    stdout = "\n".join(f"line {i} of a long verbose build log" for i in range(200))
    execution = _execution("shell.exec", {"command": "python -m unittest", "exitCode": 0, "stdout": stdout, "stderr": "Ran 35 tests\n\nOK", **POLICY})
    body = json.loads(replay_output(execution, receipt=True, turn_number=3))["body"]
    assert body["command"] == "python -m unittest" and body["exitCode"] == 0
    assert body["stdout"]["firstLines"][0] == "line 0 of a long verbose build log" and body["stdout"]["lastLines"][-1].startswith("line 199")
    assert body["stdout"]["lineCount"] == 200
    assert body["stderr"]["lines"] == ["Ran 35 tests", "OK"]
    assert "line 100 " not in json.dumps(body)


def test_edits_and_failures_never_become_receipts() -> None:
    edit = _execution("files.edit", {"path": "app.py", "diff": "--- a\n+++ b\n-VALUE = 1\n+VALUE = 2", "replacements": 1, **POLICY})
    failed = _execution("shell.exec", {"command": "pytest", "exitCode": 1, "stdout": "FAILED test_x", "stderr": ""}, ok=False, error="command failed with exit 1")
    for execution in (edit, failed):
        assert is_verbatim(execution)
    assert "+VALUE = 2" in json.loads(replay_output(edit, receipt=True, turn_number=1))["body"]["diff"]
    replayed_failure = json.loads(replay_output(failed, receipt=True, turn_number=1))
    assert replayed_failure["ok"] is False and replayed_failure["error"] == "command failed with exit 1"
    assert replayed_failure["body"]["stdout"] == "FAILED test_x"
    assert MUTATION_TOOL_IDS == {"files.edit", "files.write"}


def test_a_receipt_that_would_not_be_smaller_is_not_used() -> None:
    execution = _execution("shell.exec", {"command": "true", "exitCode": 0, "stdout": "", "stderr": ""})
    envelope = json.loads(replay_output(execution, receipt=True, turn_number=1))
    assert "elided" not in json.dumps(envelope) and envelope["body"]["command"] == "true"


def test_plan_receipt_is_the_summary_alone() -> None:
    execution = _execution("plan.write", {"items": [{"content": "step", "status": "completed"}], "total": 1, "completed": 1})
    envelope = json.loads(replay_output(execution, receipt=True, turn_number=1))
    assert envelope["body"] is None and envelope["summary"] == "plan.write summary"


def _turn(run_id: str, tool_id: str, body: dict, call_id: str) -> dict:
    return {
        "role": "assistant",
        "run_id": run_id,
        "content": "done",
        "parts": [
            {"kind": "tool_call", "toolCall": {"callId": call_id, "toolId": tool_id, "arguments": {"path": "app.py"}}},
            {"kind": "tool_result", "toolExecution": {"callId": call_id, "toolId": tool_id, "ok": True, "summary": "s", "replayOutput": json.dumps(body)}},
            {"kind": "text", "text": "done"},
        ],
    }


def test_only_turns_older_than_the_newest_one_are_receipted() -> None:
    transcript = [
        {"role": "user", "content": "first"},
        _turn("r1", "files.read", {"path": "app.py", "content": "OLD CONTENT\n" * 40, "digest": "d1"}, "c1"),
        {"role": "user", "content": "second"},
        _turn("r2", "files.read", {"path": "app.py", "content": "NEW CONTENT\n" * 40, "digest": "d2"}, "c2"),
    ]
    stats: dict[str, int] = {}
    items = transcript_to_input_array(transcript_messages=transcript, current_user_message="third", replay_stats=stats)
    outputs = [json.loads(item["output"]) for item in items if item.get("type") == "function_call_output"]
    assert "OLD CONTENT" not in json.dumps(outputs[0]) and outputs[0]["body"]["digest"] == "d1"
    assert outputs[1]["body"]["content"] == "NEW CONTENT\n" * 40
    assert stats["receiptTurns"] == 1 and stats["verbatimTurns"] == 1 and stats["receiptedOutputs"] == 1
    assert stats["replayedChars"] < stats["verbatimChars"]
