"""Coding-behavior metrics for one run, derived from its tool calls.

These are the questions the coding-harness audit asked of every trace by hand:
did the agent re-read a range it had already read, did it edit and then never
run anything, did it retry a failed call unchanged, did a search come back with
more matches than anyone can use. `benchmarks/coding/trace_analysis.py` asks
them of a trace after the fact; run finalization asks them of the run's own
tool steps and stamps the answers on the run record (`codingMetrics`), so
every real session is a sample and the Observability inspector can show a
regression on real work instead of only on the benchmark fixture.

One rule set, two callers. The analyzer's richer output (per-call lists, token
attribution) is built on top of `analyze_tool_calls`; the run record keeps the
compact `summarize_coding_metrics` shape.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import json
import re
from typing import Any

from copenet.core.harness.replay_receipts import MUTATION_TOOL_IDS
from copenet.core.tools.handlers.files import SEARCH_RESULT_HARD_CAP

READ_TOOL = "files.read"
SEARCH_TOOL = "files.rg"
SHELL_TOOL = "shell.exec"

# A "verification command" is a test, lint, type-check, build or compile step.
# Runtime probes (running the program itself) are task-specific; the benchmark
# passes its own pattern for those.
VERIFICATION_COMMAND = re.compile(
    r"(?<![\w./-])(?:pytest|unittest|py_compile|npm (?:test|run (?:lint|build|test|typecheck|check))|"
    r"pnpm (?:test|lint|build)|yarn (?:test|lint|build)|tsc|ruff|flake8|mypy|pyright|eslint|vitest|jest|"
    r"make|cargo (?:test|check|build|clippy)|go (?:test|vet|build))(?![\w-])|check\.py"
)
TEST_COMMAND = re.compile(r"pytest|unittest|vitest|jest|cargo test|go test|npm test")
STALE_EDIT_ERROR = re.compile(r"stale read detected|changed on disk since you last read")
BLOCKED_POLICY_DECISIONS = frozenset({"write_blocked", "unsafe_unknown", "approval_required"})


@dataclass
class CodingBehavior:
    """Everything the rules found, with indexes so a caller can point at the call."""

    tool_calls: int = 0
    by_tool: dict[str, int] = field(default_factory=dict)
    redundant_reads: list[dict[str, Any]] = field(default_factory=list)
    reads_after_own_edit: int = 0
    distinct_files_read: int = 0
    search_dumps: list[dict[str, Any]] = field(default_factory=list)
    exact_repeats: list[dict[str, Any]] = field(default_factory=list)
    mutation_indexes: list[int] = field(default_factory=list)
    files_edited: list[str] = field(default_factory=list)
    stale_edit_errors: int = 0
    failed_calls: list[dict[str, Any]] = field(default_factory=list)
    blind_retries: int = 0
    verification_calls: list[dict[str, Any]] = field(default_factory=list)
    # None when the run made no edit: there was nothing to verify after.
    verified_after_last_edit: bool | None = None
    failed_verifications_after_edit: int = 0
    edits_after_failed_verification: int = 0


def calls_from_tool_steps(tool_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize run-record tool steps into the call shape the rules read."""
    calls: list[dict[str, Any]] = []
    for index, step in enumerate(tool_steps):
        arguments = step.get("arguments") if isinstance(step.get("arguments"), dict) else {}
        truncated = step.get("argumentsTruncated")
        calls.append(
            {
                "index": index,
                "step": step.get("step"),
                "toolId": str(step.get("toolId") or ""),
                "arguments": arguments,
                "ok": step.get("ok"),
                "error": step.get("error"),
                "summary": step.get("summary"),
                "blocked": step.get("policyDecision") in BLOCKED_POLICY_DECISIONS,
                # A clipped write body can make two different edits look identical.
                "argumentsComplete": not (isinstance(truncated, dict) and truncated),
            }
        )
    return calls


def shell_command(arguments: dict[str, Any]) -> str:
    command = arguments.get("command")
    if isinstance(command, dict):  # digested away in a lifecycle trace
        return f"<{command.get('chars', '?')} chars>"
    return str(command or "")


READ_SUMMARY_RANGE = re.compile(r"lines (\d+)-(\d+)")


def returned_range(summary: str | None, arguments: dict[str, Any]) -> tuple[int, int]:
    """The range the tool actually returned: the summary says so; fall back to the request."""
    match = READ_SUMMARY_RANGE.search(str(summary or ""))
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return read_range(arguments)


def read_range(arguments: dict[str, Any]) -> tuple[int, int]:
    start = arguments.get("start_line")
    end = arguments.get("end_line")
    if start is None and end is None:
        if arguments.get("offset") or arguments.get("limit"):
            return (0, 0)  # char-paged read; treat as partial
        return (1, 10**9)
    return (int(start or 1), int(end or 10**9))


def _covered(existing: list[tuple[int, int]], candidate: tuple[int, int]) -> bool:
    start, end = candidate
    if candidate == (0, 0):
        return False
    return any(s <= start and end <= e for s, e in existing)


def analyze_tool_calls(calls: list[dict[str, Any]], *, extra_verification: re.Pattern[str] | None = None) -> CodingBehavior:
    """Apply the coding rules to calls in execution order.

    Each call: `index`, `toolId`, `arguments`, `ok`, `error`, `summary`, optional
    `step`, `blocked`, `argumentsComplete`.
    """
    behavior = CodingBehavior(tool_calls=len(calls), by_tool=dict(Counter(c["toolId"] for c in calls)))

    signatures: Counter = Counter()
    coverage: dict[str, list[tuple[int, int]]] = defaultdict(list)
    last_touch: dict[str, str] = {}
    files_read: set[str] = set()
    files_edited: set[str] = set()
    for call in calls:
        arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
        tool_id = call["toolId"]
        if call.get("argumentsComplete", True):
            signature = json.dumps({"t": tool_id, "a": arguments}, sort_keys=True, ensure_ascii=False, default=str)
            signatures[signature] += 1
            if signatures[signature] > 1:
                behavior.exact_repeats.append({"index": call["index"], "step": call.get("step"), "toolId": tool_id, "arguments": arguments})
        path = arguments.get("path") if isinstance(arguments.get("path"), str) else None
        if tool_id == READ_TOOL and path:
            files_read.add(path)
            rng = read_range(arguments)
            if last_touch.get(path) in MUTATION_TOOL_IDS:
                behavior.reads_after_own_edit += 1
            elif _covered(coverage[path], rng):
                behavior.redundant_reads.append({"index": call["index"], "step": call.get("step"), "path": path, "range": list(rng)})
            if call.get("ok"):
                # Coverage is what came back, not what was asked: a read clipped by
                # the char cap (or a one-line result) leaves the rest unread.
                coverage[path].append(returned_range(call.get("summary"), arguments))
            last_touch[path] = READ_TOOL
        elif tool_id in MUTATION_TOOL_IDS and path:
            if call.get("ok"):
                coverage[path] = []
                behavior.mutation_indexes.append(call["index"])
                files_edited.add(path)
            last_touch[path] = tool_id
            if call.get("error") and STALE_EDIT_ERROR.search(str(call["error"])):
                behavior.stale_edit_errors += 1
        elif tool_id == SEARCH_TOOL:
            match = re.search(r"Found (\d+) matches", str(call.get("summary") or ""))
            total = int(match.group(1)) if match else None
            if (total or 0) > SEARCH_RESULT_HARD_CAP:
                behavior.search_dumps.append(
                    {"index": call["index"], "step": call.get("step"), "pattern": arguments.get("pattern"), "totalMatches": total, "requestedLimit": arguments.get("limit")}
                )
    behavior.distinct_files_read = len(files_read)
    behavior.files_edited = sorted(files_edited)

    # --- failures: a blind retry is the same call re-issued with nothing changed between ---
    failures = [c for c in calls if c.get("ok") is False]
    behavior.failed_calls = [
        {"index": c["index"], "step": c.get("step"), "toolId": c["toolId"], "error": str(c.get("error") or "")[:160], "blocked": bool(c.get("blocked"))}
        for c in failures
    ]
    for failed in failures:
        later = [c for c in calls if c["index"] > failed["index"] and c["toolId"] == failed["toolId"]]
        if not later:
            continue
        same = json.dumps(later[0].get("arguments"), sort_keys=True, default=str) == json.dumps(failed.get("arguments"), sort_keys=True, default=str)
        if not same:
            continue
        # Re-running a failed test command after an edit is verification, not a retry.
        if any(failed["index"] < index < later[0]["index"] for index in behavior.mutation_indexes):
            continue
        behavior.blind_retries += 1

    # --- verification and recovery ---
    for call in calls:
        if call["toolId"] != SHELL_TOOL:
            continue
        command = shell_command(call.get("arguments") or {})
        if VERIFICATION_COMMAND.search(command) or (extra_verification is not None and extra_verification.search(command)):
            behavior.verification_calls.append(
                {"index": call["index"], "step": call.get("step"), "command": command[:200], "ok": call.get("ok"), "isTest": bool(TEST_COMMAND.search(command))}
            )
    if behavior.mutation_indexes:
        last_mutation = max(behavior.mutation_indexes)
        behavior.verified_after_last_edit = any(v["index"] > last_mutation for v in behavior.verification_calls)
    # A verification that fails BEFORE any edit is diagnosis. Recovery means the
    # agent edited, verified, saw it fail, and edited again.
    failed_after_edit = [
        v for v in behavior.verification_calls if v["ok"] is False and any(index < v["index"] for index in behavior.mutation_indexes)
    ]
    behavior.failed_verifications_after_edit = len(failed_after_edit)
    behavior.edits_after_failed_verification = sum(
        1 for v in failed_after_edit if any(index > v["index"] for index in behavior.mutation_indexes)
    )
    return behavior


def summarize_coding_metrics(tool_steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The compact block stamped on a run record. None when the run called no tools."""
    if not tool_steps:
        return None
    behavior = analyze_tool_calls(calls_from_tool_steps(tool_steps))
    return {
        "toolCalls": behavior.tool_calls,
        "reads": {
            "distinctFiles": behavior.distinct_files_read,
            "redundant": len(behavior.redundant_reads),
            "afterOwnEdit": behavior.reads_after_own_edit,
        },
        "searches": {
            "count": behavior.by_tool.get(SEARCH_TOOL, 0),
            "overCap": len(behavior.search_dumps),
            "cap": SEARCH_RESULT_HARD_CAP,
        },
        "edits": {
            "count": len(behavior.mutation_indexes),
            "files": len(behavior.files_edited),
            "staleErrors": behavior.stale_edit_errors,
        },
        "exactRepeats": len(behavior.exact_repeats),
        "failures": {
            "count": len(behavior.failed_calls),
            "blocked": sum(1 for f in behavior.failed_calls if f["blocked"]),
            "blindRetries": behavior.blind_retries,
        },
        "verification": {
            "commands": len(behavior.verification_calls),
            "tests": sum(1 for v in behavior.verification_calls if v["isTest"]),
            "afterLastEdit": behavior.verified_after_last_edit,
            # Did the run stop with the suite failing? The session list titles that row
            # "red" off this one fact — an exit code, not an interpretation.
            "lastFailed": behavior.verification_calls[-1]["ok"] is False if behavior.verification_calls else False,
        },
        "recovery": {
            "failedVerificationsAfterEdit": behavior.failed_verifications_after_edit,
            "editsAfterFailedVerification": behavior.edits_after_failed_verification,
        },
    }
