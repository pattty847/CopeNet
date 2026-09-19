"""Coding-behavior metrics: one rule set for the run record and the benchmark analyzer."""

from __future__ import annotations

from copenet.core.harness.coding_metrics import analyze_tool_calls, calls_from_tool_steps, summarize_coding_metrics
from copenet.core.runtime.runs import RunRecord


def _step(tool_id: str, arguments: dict, *, ok: bool = True, summary: str = "", error: str | None = None, **extra) -> dict:
    step = {"toolId": tool_id, "ok": ok, "summary": summary, "arguments": arguments}
    if error:
        step["error"] = error
    step.update(extra)
    return step


def test_redundant_read_is_a_range_already_read_with_no_edit_between() -> None:
    steps = [
        _step("files.read", {"path": "a.py", "start_line": 1, "end_line": 80}),
        _step("files.read", {"path": "a.py", "start_line": 10, "end_line": 40}),  # inside 1-80: redundant
        _step("files.read", {"path": "a.py", "start_line": 60, "end_line": 120}),  # extends past 80: not redundant
        _step("files.edit", {"path": "a.py", "old_text": "x", "new_text": "y"}),
        _step("files.read", {"path": "a.py", "start_line": 10, "end_line": 40}),  # after own edit: counted separately
    ]
    behavior = analyze_tool_calls(calls_from_tool_steps(steps))
    assert [r["index"] for r in behavior.redundant_reads] == [1]
    assert behavior.reads_after_own_edit == 1
    assert behavior.distinct_files_read == 1
    assert behavior.files_edited == ["a.py"]


def test_search_dump_stale_edit_and_exact_repeat_are_counted() -> None:
    steps = [
        _step("files.rg", {"pattern": "lock", "path": "src"}, summary="Found 1153 matches for pattern via ripgrep; returning 200."),
        _step("files.rg", {"pattern": "assert_session_binding", "path": "src"}, summary="Found 4 matches for pattern via ripgrep; returning 4."),
        _step("files.rg", {"pattern": "assert_session_binding", "path": "src"}, summary="Found 4 matches for pattern via ripgrep; returning 4."),
        _step("files.edit", {"path": "b.py", "old_text": "1", "new_text": "2"}, ok=False, error="b.py changed on disk since you last read it in this run (digest a then, b now); read it again before editing"),
        # A clipped write body must not count as a repeat of another clipped write.
        _step("files.write", {"path": "big.py", "content": "x" * 10}, argumentsTruncated={"content": 90_000}),
        _step("files.write", {"path": "big.py", "content": "x" * 10}, argumentsTruncated={"content": 90_000}),
    ]
    behavior = analyze_tool_calls(calls_from_tool_steps(steps))
    assert [d["totalMatches"] for d in behavior.search_dumps] == [1153]
    assert behavior.stale_edit_errors == 1
    assert [r["index"] for r in behavior.exact_repeats] == [2]


def test_verification_after_last_edit_and_recovery() -> None:
    steps = [
        _step("shell.exec", {"command": "python -m pytest tests/unit/test_x.py"}, ok=False, summary="exit 1"),  # diagnosis, before any edit
        _step("files.edit", {"path": "x.py", "old_text": "a", "new_text": "b"}),
        _step("shell.exec", {"command": "python -m pytest tests/unit/test_x.py"}, ok=False, summary="exit 1"),  # failed after an edit
        _step("files.edit", {"path": "x.py", "old_text": "b", "new_text": "c"}),  # recovery edit
        _step("shell.exec", {"command": "python -m pytest tests/unit/test_x.py"}, ok=True, summary="exit 0"),
    ]
    behavior = analyze_tool_calls(calls_from_tool_steps(steps))
    assert behavior.verified_after_last_edit is True
    assert len(behavior.verification_calls) == 3 and all(v["isTest"] for v in behavior.verification_calls)
    assert behavior.failed_verifications_after_edit == 1 and behavior.edits_after_failed_verification == 1
    # The identical re-run at index 2 is verification after an edit, not a blind retry.
    assert behavior.blind_retries == 0

    unverified = analyze_tool_calls(calls_from_tool_steps(steps[:2]))
    assert unverified.verified_after_last_edit is False
    read_only = analyze_tool_calls(calls_from_tool_steps([_step("files.read", {"path": "x.py"})]))
    assert read_only.verified_after_last_edit is None


def test_blind_retry_is_the_same_failed_call_reissued_unchanged() -> None:
    steps = [
        _step("shell.exec", {"command": "ls nowhere"}, ok=False, error="exit 1"),
        _step("shell.exec", {"command": "ls nowhere"}, ok=False, error="exit 1"),
        _step("shell.exec", {"command": "ls ."}, ok=True),
    ]
    behavior = analyze_tool_calls(calls_from_tool_steps(steps))
    assert behavior.blind_retries == 1
    assert [f["toolId"] for f in behavior.failed_calls] == ["shell.exec", "shell.exec"]


def test_summary_shape_and_none_for_chat_only_turns() -> None:
    assert summarize_coding_metrics([]) is None
    steps = [
        _step("files.read", {"path": "a.py"}),
        _step("files.read", {"path": "a.py"}),
        _step("files.edit", {"path": "a.py", "old_text": "1", "new_text": "2"}),
        _step("shell.exec", {"command": "npm run lint"}, ok=True),
        _step("shell.exec", {"command": "rm -rf build"}, ok=False, policyDecision="approval_required", summary="blocked"),
    ]
    summary = summarize_coding_metrics(steps)
    assert summary == {
        "toolCalls": 5,
        "reads": {"distinctFiles": 1, "redundant": 1, "afterOwnEdit": 0},
        "searches": {"count": 0, "overCap": 0, "cap": 200},
        "edits": {"count": 1, "files": 1, "staleErrors": 0},
        "exactRepeats": 1,
        "failures": {"count": 1, "blocked": 1, "blindRetries": 0},
        "verification": {"commands": 1, "tests": 0, "afterLastEdit": True, "lastFailed": False},
        "recovery": {"failedVerificationsAfterEdit": 0, "editsAfterFailedVerification": 0},
    }


def test_run_record_round_trips_coding_metrics_and_exposes_them_publicly() -> None:
    metrics = summarize_coding_metrics([_step("files.read", {"path": "a.py"})])
    record = RunRecord(
        run_id="r", session_key="s", provider="openai-codex", model="gpt-5.5", status="ok",
        user_message="m", tool_execution_mode="responses", will_attempt_tool_loop=True,
        coding_metrics=metrics,
    )
    restored = RunRecord.from_json(record.to_json())
    assert restored.coding_metrics == metrics
    assert restored.to_public_dict()["codingMetrics"]["reads"]["distinctFiles"] == 1
    assert RunRecord.from_json({**record.to_json(), "coding_metrics": None}).to_public_dict()["codingMetrics"] is None


def test_coverage_is_the_returned_range_not_the_requested_one() -> None:
    steps = [
        _step("files.read", {"path": "a.py", "start_line": 1, "end_line": 90, "limit": 1}, summary="Read file a.py lines 1-1."),
        _step("files.read", {"path": "a.py", "start_line": 1, "end_line": 90}, summary="Read file a.py lines 1-90."),
        _step("files.read", {"path": "a.py", "start_line": 1, "end_line": 90}, summary="Read file a.py lines 1-90."),
    ]
    behavior = analyze_tool_calls(calls_from_tool_steps(steps))
    assert [r["index"] for r in behavior.redundant_reads] == [2]
