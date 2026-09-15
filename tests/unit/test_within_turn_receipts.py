"""Within-turn receipts: old read-only results shrink in the live array; edits, failures, and the last steps stay."""

from __future__ import annotations

import json

from copenet.core.harness.responses_items import function_call_item, function_call_output_item
from copenet.core.harness.within_turn_receipts import LiveToolResult, apply_within_turn_receipts, remember_result


def _read_body(path: str, start: int) -> str:
    return json.dumps({"toolId": "files.read", "ok": True, "summary": f"Read file {path} lines {start}-{start + 199}.", "body": {"path": path, "startLine": start, "endLine": start + 199, "totalLines": 2000, "digest": "d1", "content": ("x = 1\n" * 200)}})


def _array() -> tuple[list[dict], dict[str, LiveToolResult]]:
    messages: list[dict] = []
    results: dict[str, LiveToolResult] = {}

    def add(step: int, tool_id: str, arguments: dict, output: str, *, ok: bool = True, error: str | None = None) -> None:
        call_id = f"c{step}"
        messages.append(function_call_item(item_id=f"fc_{call_id}", call_id=call_id, name=tool_id, arguments=arguments))
        messages.append(function_call_output_item(call_id=call_id, output=output))
        remember_result(results, call_id=call_id, step=step, tool_id=tool_id, ok=ok, summary="s", error=error, artifact_id=None, arguments=arguments, output=output)

    add(1, "files.read", {"path": "app.py", "start_line": 1, "end_line": 200}, _read_body("app.py", 1))
    add(2, "files.edit", {"path": "app.py", "old_text": "a", "new_text": "b"}, json.dumps({"toolId": "files.edit", "ok": True, "summary": "edited", "body": {"path": "app.py", "diff": "-a\n+b\n" * 50}}))
    add(3, "shell.exec", {"command": "pytest"}, json.dumps({"toolId": "shell.exec", "ok": False, "summary": "exit 1", "error": "failed", "body": {"command": "pytest", "exitCode": 1, "stdout": "FAILED x\n" * 80, "stderr": ""}}), ok=False, error="failed")
    add(4, "files.read", {"path": "app.py", "start_line": 201, "end_line": 400}, _read_body("app.py", 201))
    add(5, "files.read", {"path": "app.py", "start_line": 401, "end_line": 600}, _read_body("app.py", 401))
    add(6, "files.read", {"path": "app.py", "start_line": 601, "end_line": 800}, _read_body("app.py", 601))
    return messages, results


def _outputs(messages: list[dict]) -> dict[str, str]:
    return {item["call_id"]: item["output"] for item in messages if item.get("type") == "function_call_output"}


def test_pass_receipts_old_reads_and_keeps_edits_failures_and_recent_steps() -> None:
    messages, results = _array()
    stats = apply_within_turn_receipts(messages, results, current_step=7, request_tokens=50_000, trigger_tokens=32_000, keep_recent_steps=3, min_freed_tokens=10)
    assert stats is not None and stats["itemsReceipted"] == 2 and stats["freedTokens"] > 0
    assert [row["step"] for row in stats["receipted"]] == [1, 4]
    outputs = _outputs(messages)
    assert "elided" in outputs["c1"] and "step 1 of this turn" in outputs["c1"] and "x = 1" not in outputs["c1"]
    assert "elided" in outputs["c4"]
    assert "+b" in outputs["c2"]                      # edit stays verbatim
    assert "FAILED x" in outputs["c3"]                # failure stays verbatim
    assert "x = 1" in outputs["c5"] and "x = 1" in outputs["c6"]  # the last three steps stay
    assert stats["requestTokensAfter"] == 50_000 - stats["freedTokens"]
    # a second pass at the same step has nothing left to do
    assert apply_within_turn_receipts(messages, results, current_step=7, request_tokens=50_000, trigger_tokens=32_000, keep_recent_steps=3, min_freed_tokens=10) is None
    # one step later, step 5 has aged past the keep window and goes too; 6 still stays
    later = apply_within_turn_receipts(messages, results, current_step=8, request_tokens=50_000, trigger_tokens=32_000, keep_recent_steps=3, min_freed_tokens=10)
    assert later is not None and [row["step"] for row in later["receipted"]] == [5]
    assert "x = 1" in _outputs(messages)["c6"]


def test_pass_does_nothing_below_the_trigger_or_when_too_little_would_be_freed() -> None:
    messages, results = _array()
    assert apply_within_turn_receipts(messages, results, current_step=7, request_tokens=20_000, trigger_tokens=32_000) is None
    assert apply_within_turn_receipts(messages, results, current_step=7, request_tokens=50_000, trigger_tokens=32_000, min_freed_tokens=1_000_000) is None
    assert all("x = 1" in output for call_id, output in _outputs(messages).items() if call_id in {"c1", "c4", "c5", "c6"})
