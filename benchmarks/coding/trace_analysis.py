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
from copenet.core.harness.coding_metrics import READ_TOOL, analyze_tool_calls, shell_command  # noqa: E402
from copenet.core.harness.replay_receipts import MUTATION_TOOL_IDS  # noqa: E402
from copenet.core.harness.token_count import count_text_tokens  # noqa: E402

MUTATING_TOOLS = MUTATION_TOOL_IDS
INTERPRETED_EVENTS = {"responses_turn_interpreted", "provider_response_interpreted", "prompted_tool_response_interpreted"}
# Fixture-specific verification on top of the harness's generic test/lint/build rule:
# running the ledgerly CLI or an inline python check is how the fixture tasks get verified.
BENCH_EXTRA_VERIFY_PATTERN = re.compile(r"python3? -m ledgerly|python3? -c ")
CHECK_SCRIPT_PATTERN = re.compile(r"check\.py")
RUNTIME_PATTERN = re.compile(r"python3? -m ledgerly\.cli|ledgerly\.cli")


def load_rows(source: str | Path) -> list[dict[str, Any]]:
    path = Path(source)
    if not path.exists():
        path = default_run_logs_dir() / f"{source}.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


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
        elif event == "replay_receipts_applied":
            header["replayReceipts"] = dict(payload)
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

    # --- the coding rules (shared with run finalization) ---------------------
    for call in calls:
        # Lifecycle-tier arguments are digested: a 1,100-char edit body becomes
        # {"chars": 1100, "omitted": true}, so two different edits can look identical.
        call["argumentsComplete"] = '"omitted": true' not in json.dumps(call["arguments"], ensure_ascii=False)
    behavior = analyze_tool_calls(calls, extra_verification=BENCH_EXTRA_VERIFY_PATTERN)
    tokens_by_index = {c["index"]: c["resultTokens"] for c in calls}
    redundant_reads = [{"step": r["step"], "path": r["path"], "range": r["range"]} for r in behavior.redundant_reads]
    reads_after_own_edit = behavior.reads_after_own_edit
    stale_digest_errors = behavior.stale_edit_errors
    search_dumps = [{**d, "resultTokens": tokens_by_index.get(d["index"])} for d in behavior.search_dumps]
    exact_repeats = [{"step": r["step"], "toolId": r["toolId"], "arguments": r["arguments"]} for r in behavior.exact_repeats]
    failures = [c for c in calls if c["ok"] is False]
    mutation_indexes = behavior.mutation_indexes
    blind_retries = behavior.blind_retries
    verification_calls = [
        {**v, "isCheck": bool(CHECK_SCRIPT_PATTERN.search(v["command"])), "isRuntime": bool(RUNTIME_PATTERN.search(v["command"]))}
        for v in behavior.verification_calls
    ]
    # With no edit at all, "verified" means a verification command ran at some point.
    after_last_mutation = behavior.verified_after_last_edit if behavior.verified_after_last_edit is not None else bool(verification_calls)
    failed_verifications = [v for v in verification_calls if v["ok"] is False]
    failed_after_edit = [v for v in failed_verifications if any(index < v["index"] for index in mutation_indexes)]
    edits_after_failed_verification = behavior.edits_after_failed_verification
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
            "target": (c["arguments"].get("path") or c["arguments"].get("pattern") or shell_command(c["arguments"]) or "")[:120] if isinstance(c["arguments"], dict) else "",
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
