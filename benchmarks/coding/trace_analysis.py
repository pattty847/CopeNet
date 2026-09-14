"""Read one CopeNet run trace and answer the coding-agent questions.

Works on any `~/.copenet/logs/runs/<run-id>.jsonl`, benchmark or not:

    uv run python -m benchmarks.coding.trace_analysis <run-id-or-path> [--json]

Everything here is derived from the lifecycle tier; the debug tier (full tool
arguments and result bodies) sharpens the token attribution when present.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from copenet._paths import default_run_logs_dir  # noqa: E402
from copenet.core.harness.token_count import count_text_tokens  # noqa: E402

MUTATING_TOOLS = {"files.edit", "files.write"}
READ_TOOL = "files.read"
SEARCH_TOOL = "files.rg"
SHELL_TOOL = "shell.exec"
INTERPRETED_EVENTS = {"responses_turn_interpreted", "provider_response_interpreted", "prompted_tool_response_interpreted"}
VERIFY_PATTERN = re.compile(
    r"(unittest|pytest|scripts/check\.py|check\.py|npm (test|run (lint|build|test))|tsc\b|ruff|flake8|mypy|make\b|py_compile|"
    r"python3? -m ledgerly|python3? -c )"
)
CHECK_SCRIPT_PATTERN = re.compile(r"check\.py")
RUNTIME_PATTERN = re.compile(r"python3? -m ledgerly\.cli|ledgerly\.cli")
TEST_PATTERN = re.compile(r"unittest|pytest")


def load_rows(source: str | Path) -> list[dict[str, Any]]:
    path = Path(source)
    if not path.exists():
        path = default_run_logs_dir() / f"{source}.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _shell_command(args: dict[str, Any]) -> str:
    command = args.get("command")
    if isinstance(command, dict):  # digested away
        return f"<{command.get('chars', '?')} chars>"
    return str(command or "")


def _read_range(args: dict[str, Any]) -> tuple[int, int]:
    start = args.get("start_line")
    end = args.get("end_line")
    if start is None and end is None:
        if args.get("offset") or args.get("limit"):
            return (0, 0)  # char-paged read; treat as partial
        return (1, 10**9)
    return (int(start or 1), int(end or 10**9))


def _covered(existing: list[tuple[int, int]], candidate: tuple[int, int]) -> bool:
    start, end = candidate
    if candidate == (0, 0):
        return False
    return any(s <= start and end <= e for s, e in existing)


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    full_arguments: dict[str, dict[str, Any]] = {}
    result_bodies: dict[str, Any] = {}
    input_estimates: list[dict[str, Any]] = []
    usage_steps: list[dict[str, Any]] = []
    model_calls = 0
    reasoning_chars = 0
    terminal_reason = None
    run_status = None
    error = None
    header: dict[str, Any] = {}
    persisted = 0
    trimmed_events = 0
    ledger: dict[str, Any] = {"injected": False}

    for row in rows:
        event = row.get("event")
        payload = row.get("payload") or {}
        if event == "run_started":
            header["workdir"] = payload.get("workdir")
            header["taskMode"] = payload.get("taskMode")
            header["profile"] = payload.get("profile")
            header["provider"] = row.get("provider")
            header["model"] = row.get("model")
        elif event == "harness_planned":
            header["toolExecutionMode"] = payload.get("toolExecutionMode")
            header["availableTools"] = payload.get("availableToolIds")
        elif event == "chat_messages_built":
            header["historyTurns"] = payload.get("historyTurns")
            header["initialInputTokenEstimate"] = payload.get("prePlanInputTokenEstimate")
            header["fixedInputTokenEstimate"] = payload.get("fixedInputTokenEstimate")
            header["inputTokenBudget"] = payload.get("inputTokenBudget")
        elif event == "prompt_context_assembled":
            header["systemPromptChars"] = payload.get("combinedSystemPromptChars")
            header["toolSchemaChars"] = payload.get("toolSchemaChars")
            header["toolCount"] = payload.get("toolCount")
            header["personaChars"] = payload.get("personaChars")
        elif event == "model_resolved":
            header["model"] = payload.get("resolvedModel") or header.get("model")
        elif event in INTERPRETED_EVENTS:
            model_calls += 1
        elif event == "tool_loop_input_prepared":
            input_estimates.append({"step": payload.get("step"), "tokens": payload.get("providerInputTokenEstimate"), "omitted": payload.get("omittedItemCount")})
        elif event == "tool_loop_input_trimmed":
            trimmed_events += 1
        elif event == "provider_usage_reported":
            usage_steps.append(dict(payload))
        elif event == "reasoning_delta":
            reasoning_chars += int(payload.get("chars") or 0)
        elif event == "tool_requested":
            call = {
                "index": len(calls) + len(pending),
                "step": payload.get("step"),
                "toolId": payload.get("toolId"),
                "callId": payload.get("callId"),
                "arguments": payload.get("arguments") or {},
                "ok": None,
                "summary": None,
                "error": None,
                "blocked": False,
            }
            pending.append(call)
        elif event == "tool_arguments":
            call_id = payload.get("callId")
            if call_id:
                full_arguments[call_id] = payload.get("arguments") or {}
        elif event in {"tool_executed", "tool_blocked"}:
            if pending:
                call = pending.pop(0)
                call["ok"] = payload.get("ok") if event == "tool_executed" else False
                call["summary"] = payload.get("summary") or payload.get("reason")
                call["error"] = payload.get("error") or (payload.get("reason") if event == "tool_blocked" else None)
                call["blocked"] = event == "tool_blocked"
                calls.append(call)
        elif event == "tool_result_body":
            call_id = payload.get("callId")
            if call_id:
                result_bodies[call_id] = payload
        elif event == "tool_result_persisted":
            persisted += 1
        elif event == "change_ledger_injected":
            ledger = {"injected": True, **payload}
        elif event == "turn_completed":
            terminal_reason = payload.get("terminalReason")
        elif event == "run_completed":
            run_status = payload.get("status")
        elif event == "run_failed":
            run_status = payload.get("status") or "error"
            error = payload.get("error")
    calls.extend(pending)  # requested but never executed (aborted mid-flight)

    for call in calls:
        if call["callId"] in full_arguments:
            call["arguments"] = full_arguments[call["callId"]]
        body = result_bodies.get(call["callId"])
        if body is not None:
            call["resultTokens"] = count_text_tokens(json.dumps(body.get("body"), ensure_ascii=False))
        else:
            call["resultTokens"] = None

    # --- token attribution -------------------------------------------------
    steps_tokens: dict[int, int] = {}
    previous = None
    for entry in input_estimates:
        if previous is not None and entry["tokens"] is not None and previous["tokens"] is not None:
            steps_tokens[int(previous["step"])] = int(entry["tokens"]) - int(previous["tokens"])
        previous = entry
    by_tool_tokens: Counter = Counter()
    by_step_calls: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        if call["step"] is not None:
            by_step_calls[int(call["step"])].append(call)
    for step, growth in steps_tokens.items():
        members = by_step_calls.get(step) or []
        if not members:
            continue
        known = [c for c in members if c["resultTokens"] is not None]
        if len(known) == len(members):
            for call in members:
                by_tool_tokens[call["toolId"]] += call["resultTokens"]
        else:
            share = max(growth, 0) // len(members)
            for call in members:
                by_tool_tokens[call["toolId"]] += share
    if not steps_tokens:
        for call in calls:
            if call["resultTokens"] is not None:
                by_tool_tokens[call["toolId"]] += call["resultTokens"]

    # --- repeats and redundant reads ----------------------------------------
    signatures: Counter = Counter()
    exact_repeats: list[dict[str, Any]] = []
    coverage: dict[str, list[tuple[int, int]]] = defaultdict(list)
    last_touch: dict[str, str] = {}
    redundant_reads: list[dict[str, Any]] = []
    reads_after_own_edit = 0
    stale_digest_errors = 0
    search_dumps: list[dict[str, Any]] = []
    for call in calls:
        signature = json.dumps({"t": call["toolId"], "a": call["arguments"]}, sort_keys=True, ensure_ascii=False)
        # Lifecycle-tier arguments are digested: a 1,100-char edit body becomes
        # {"chars": 1100, "omitted": true}, so two different edits can look identical.
        # Only count a repeat when the arguments are fully known.
        if '"omitted": true' not in signature:
            signatures[signature] += 1
            if signatures[signature] > 1:
                exact_repeats.append({"step": call["step"], "toolId": call["toolId"], "arguments": call["arguments"]})
        path = call["arguments"].get("path") if isinstance(call["arguments"].get("path"), str) else None
        if call["toolId"] == READ_TOOL and path:
            rng = _read_range(call["arguments"])
            if last_touch.get(path) in MUTATING_TOOLS:
                reads_after_own_edit += 1
            elif _covered(coverage[path], rng):
                redundant_reads.append({"step": call["step"], "path": path, "range": list(rng)})
            if call["ok"]:
                coverage[path].append(rng)
            last_touch[path] = READ_TOOL
        elif call["toolId"] in MUTATING_TOOLS and path:
            if call["ok"]:
                coverage[path] = []
            last_touch[path] = call["toolId"]
            if call["error"] and "stale read detected" in str(call["error"]):
                stale_digest_errors += 1
        elif call["toolId"] == SEARCH_TOOL:
            match = re.search(r"Found (\d+) matches", str(call["summary"] or ""))
            total = int(match.group(1)) if match else None
            requested_limit = call["arguments"].get("limit")
            if (total or 0) > 200:
                search_dumps.append({"step": call["step"], "pattern": call["arguments"].get("pattern"), "totalMatches": total, "requestedLimit": requested_limit, "resultTokens": call["resultTokens"]})

    # --- failures and recovery -----------------------------------------------
    failures = [c for c in calls if c["ok"] is False]
    mutation_indexes = [c["index"] for c in calls if c["toolId"] in MUTATING_TOOLS and c["ok"]]
    blind_retries = 0
    for failed in failures:
        later = [c for c in calls if c["index"] > failed["index"] and c["toolId"] == failed["toolId"]]
        if not later or json.dumps(later[0]["arguments"], sort_keys=True) != json.dumps(failed["arguments"], sort_keys=True):
            continue
        # Re-running a failed test command after an edit is verification, not a
        # blind retry. Only an identical re-issue with nothing changed in between counts.
        if any(failed["index"] < index < later[0]["index"] for index in mutation_indexes):
            continue
        blind_retries += 1

    # --- verification ----------------------------------------------------------
    verification_calls: list[dict[str, Any]] = []
    for call in calls:
        if call["toolId"] != SHELL_TOOL:
            continue
        command = _shell_command(call["arguments"])
        if VERIFY_PATTERN.search(command):
            verification_calls.append({"index": call["index"], "step": call["step"], "command": command[:200], "ok": call["ok"], "isTest": bool(TEST_PATTERN.search(command)), "isCheck": bool(CHECK_SCRIPT_PATTERN.search(command)), "isRuntime": bool(RUNTIME_PATTERN.search(command))})
    last_mutation = max(mutation_indexes) if mutation_indexes else None
    after_last_mutation = any(v["index"] > last_mutation for v in verification_calls) if last_mutation is not None else bool(verification_calls)
    failed_verifications = [v for v in verification_calls if v["ok"] is False]
    # A verification that fails BEFORE any edit is diagnosis (running the suite to
    # see the failure). Recovery means: the agent edited, verified, saw it fail,
    # and edited again — a failed verification with a mutation on both sides.
    failed_after_edit = [v for v in failed_verifications if any(index < v["index"] for index in mutation_indexes)]
    edits_after_failed_verification = sum(
        1 for v in failed_after_edit if any(index > v["index"] for index in mutation_indexes)
    )
    failed_then_edit = edits_after_failed_verification > 0

    # --- timing -----------------------------------------------------------------
    stamps = [row.get("timestamp") for row in rows if row.get("timestamp")]
    elapsed = None
    if len(stamps) >= 2:
        try:
            elapsed = (datetime.fromisoformat(stamps[-1]) - datetime.fromisoformat(stamps[0])).total_seconds()
        except ValueError:
            elapsed = None

    usage_inputs = [s.get("inputTokens") for s in usage_steps if s.get("inputTokens") is not None]
    usage_cached = [s.get("cachedInputTokens") for s in usage_steps if s.get("cachedInputTokens") is not None]
    timeline = [
        {
            "step": c["step"],
            "toolId": c["toolId"],
            "target": (c["arguments"].get("path") or c["arguments"].get("pattern") or _shell_command(c["arguments"]) or "")[:120] if isinstance(c["arguments"], dict) else "",
            "ok": c["ok"],
            "summary": (c["summary"] or "")[:140],
            "resultTokens": c["resultTokens"],
        }
        for c in calls
    ]
    return {
        "header": header,
        "outcome": {"runStatus": run_status, "terminalReason": terminal_reason, "error": error, "elapsedSec": round(elapsed, 1) if elapsed is not None else None},
        "modelCalls": model_calls,
        "toolCalls": len(calls),
        "toolCallsByTool": dict(Counter(c["toolId"] for c in calls)),
        "tokens": {
            "inputEstimatePerStep": input_estimates,
            "peakInputEstimate": max((e["tokens"] or 0) for e in input_estimates) if input_estimates else None,
            "providerReported": {
                "modelCalls": len(usage_steps),
                "inputTokensTotal": sum(usage_inputs) if usage_inputs else None,
                "peakInputTokens": max(usage_inputs) if usage_inputs else None,
                "cachedInputTokensTotal": sum(usage_cached) if usage_cached else None,
                "outputTokensTotal": sum(s.get("outputTokens") or 0 for s in usage_steps) or None,
                "reasoningTokensTotal": sum(s.get("reasoningTokens") or 0 for s in usage_steps) or None,
            },
            "attributedToToolResults": dict(by_tool_tokens.most_common()),
            "largestToolResults": sorted(
                [{"step": c["step"], "toolId": c["toolId"], "target": (c["arguments"].get("path") or c["arguments"].get("pattern") or "")[:80], "tokens": c["resultTokens"]} for c in calls if c["resultTokens"]],
                key=lambda item: -item["tokens"],
            )[:5],
            "persistedAsArtifact": persisted,
            "trimEvents": trimmed_events,
            "reasoningSummaryChars": reasoning_chars,
        },
        "reads": {
            "redundantReads": redundant_reads,
            "redundantReadCount": len(redundant_reads),
            "readsAfterOwnEdit": reads_after_own_edit,
            "distinctFilesRead": len({c["arguments"].get("path") for c in calls if c["toolId"] == READ_TOOL and isinstance(c["arguments"].get("path"), str)}),
            "searchDumps": search_dumps,
        },
        "changeLedger": ledger,
        "edits": {
            "mutations": len(mutation_indexes),
            "filesEdited": sorted({c["arguments"].get("path") for c in calls if c["toolId"] in MUTATING_TOOLS and c["ok"] and isinstance(c["arguments"].get("path"), str)}),
            "staleDigestErrors": stale_digest_errors,
        },
        "repeats": {"exactRepeatCount": len(exact_repeats), "exactRepeats": exact_repeats[:10]},
        "failures": {
            "failedToolCalls": [{"step": c["step"], "toolId": c["toolId"], "error": (c["error"] or "")[:160], "blocked": c["blocked"]} for c in failures],
            "blindRetries": blind_retries,
        },
        "verification": {
            "commands": verification_calls,
            "commandCount": len(verification_calls),
            "afterLastMutation": after_last_mutation,
            "checkScriptRuns": sum(1 for v in verification_calls if v["isCheck"]),
            "testRuns": sum(1 for v in verification_calls if v["isTest"]),
            "runtimeCommandRuns": sum(1 for v in verification_calls if v["isRuntime"]),
        },
        "recovery": {
            "failedVerificationCount": len(failed_verifications),
            "failedVerificationAfterEditCount": len(failed_after_edit),
            "editsAfterFailedVerification": edits_after_failed_verification,
            "failedVerificationThenEdit": failed_then_edit,
        },
        "timeline": timeline,
    }


def render_markdown(analysis: dict[str, Any]) -> str:
    header = analysis["header"]
    tokens = analysis["tokens"]
    reported = tokens["providerReported"]
    lines = [
        f"- provider/model: {header.get('provider')} / {header.get('model')} ({header.get('toolExecutionMode')}), access: {header.get('taskMode')}",
        f"- outcome: {analysis['outcome']}",
        f"- model calls: {analysis['modelCalls']}, tool calls: {analysis['toolCalls']} {analysis['toolCallsByTool']}",
        f"- system prompt chars: {header.get('systemPromptChars')}, tool schema chars: {header.get('toolSchemaChars')} ({header.get('toolCount')} tools), history turns replayed: {header.get('historyTurns')}",
        f"- tokens (provider-reported): total input {reported['inputTokensTotal']}, peak input {reported['peakInputTokens']}, cached {reported['cachedInputTokensTotal']}, output {reported['outputTokensTotal']}, reasoning {reported['reasoningTokensTotal']}",
        f"- tokens (harness estimate): peak input {tokens['peakInputEstimate']}, attributed to tool results {tokens['attributedToToolResults']}",
        f"- largest tool results: {tokens['largestToolResults']}",
        f"- reads: {analysis['reads']['distinctFilesRead']} files, redundant {analysis['reads']['redundantReadCount']}, after-own-edit {analysis['reads']['readsAfterOwnEdit']}, search dumps {len(analysis['reads']['searchDumps'])}",
        f"- edits: {analysis['edits']}",
        f"- change ledger on this turn: {analysis['changeLedger']}",
        f"- exact repeats: {analysis['repeats']['exactRepeatCount']}",
        f"- failures: {len(analysis['failures']['failedToolCalls'])} (blind retries {analysis['failures']['blindRetries']})",
        f"- verification: {analysis['verification']['commandCount']} commands, after last edit: {analysis['verification']['afterLastMutation']}, test runs {analysis['verification']['testRuns']}, check runs {analysis['verification']['checkScriptRuns']}, runtime runs {analysis['verification']['runtimeCommandRuns']}",
        f"- recovery: {analysis['recovery']}",
        "",
        "| step | tool | target | ok | result tokens | summary |",
        "|---|---|---|---|---|---|",
    ]
    for row in analysis["timeline"]:
        target = str(row["target"]).replace("|", "\\|").replace("\n", " ")
        summary = str(row["summary"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['step']} | {row['toolId']} | `{target}` | {row['ok']} | {row['resultTokens'] if row['resultTokens'] is not None else ''} | {summary} |")
    if tokens["inputEstimatePerStep"]:
        lines.append("")
        lines.append("input estimate per model call: " + ", ".join(f"{e['step']}:{e['tokens']}" for e in tokens["inputEstimatePerStep"]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze one CopeNet run trace as a coding-agent run")
    parser.add_argument("run", help="run id or path to a trace .jsonl")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    analysis = analyze(load_rows(args.run))
    if args.json:
        print(json.dumps(analysis, indent=2))
    else:
        print(render_markdown(analysis))
    return 0


if __name__ == "__main__":
    sys.exit(main())
