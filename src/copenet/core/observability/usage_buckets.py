"""Accumulators behind the usage rollup: one bucket per grouping dimension.

Split out of `usage_rollup.py` so that module stays the grouping pass. The
honesty rules these shapes encode are documented there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, tzinfo
from typing import Any

from copenet.core.runtime.runs import RunRecord

ERROR_STATUSES = frozenset({"error", "failed"})
# `policy_for_task_mode` refused or deferred the call; the model asked, nothing ran.
BLOCKED_POLICY_DECISIONS = frozenset({"write_blocked", "unsafe_unknown", "approval_required"})

TOKEN_KEYS = ("inputTokens", "cachedInputTokens", "outputTokens", "reasoningTokens")


def parse_timestamp(value: str | None, tz: tzinfo) -> datetime | None:
    """Parse one stored ISO timestamp into `tz`, or None when it is unusable."""
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(tz)


def whole_int(value: Any) -> int:
    """A stored count as an int; anything else (None, str, bool) counts as zero."""
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def ratio(numerator: int, denominator: int) -> float | None:
    """A rate, or None when nothing was measured — never 0.0 standing in for unknown."""
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


@dataclass
class TokenBucket:
    """Token sums plus the run counts that give them a denominator."""

    runs: int = 0
    runs_with_usage: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    error_runs: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    peak_input_tokens: int = 0
    session_keys: set[str] = field(default_factory=set)

    def add(self, record: RunRecord, usage: dict[str, Any] | None) -> None:
        self.runs += 1
        self.tool_calls += len(record.tool_steps)
        self.session_keys.add(record.session_key)
        if record.status in ERROR_STATUSES or record.error:
            self.error_runs += 1
        if not usage:
            return
        self.runs_with_usage += 1
        self.model_calls += whole_int(usage.get("modelCalls"))
        self.input_tokens += whole_int(usage.get("inputTokens"))
        self.cached_input_tokens += whole_int(usage.get("cachedInputTokens"))
        self.output_tokens += whole_int(usage.get("outputTokens"))
        self.reasoning_tokens += whole_int(usage.get("reasoningTokens"))
        self.peak_input_tokens = max(self.peak_input_tokens, whole_int(usage.get("peakInputTokens")))

    @property
    def total_tokens(self) -> int:
        """Input plus output. Cached input is inside input; reasoning is inside output."""
        return self.input_tokens + self.output_tokens

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "runsWithUsage": self.runs_with_usage,
            "modelCalls": self.model_calls,
            "toolCalls": self.tool_calls,
            "errorRuns": self.error_runs,
            "errorRate": ratio(self.error_runs, self.runs),
            "inputTokens": self.input_tokens,
            "cachedInputTokens": self.cached_input_tokens,
            "freshInputTokens": self.input_tokens - self.cached_input_tokens,
            "outputTokens": self.output_tokens,
            "reasoningTokens": self.reasoning_tokens,
            "peakInputTokens": self.peak_input_tokens,
            "totalTokens": self.total_tokens,
            "cacheHitRate": ratio(self.cached_input_tokens, self.input_tokens),
            "sessions": len(self.session_keys),
        }


@dataclass
class CodingBucket:
    """The coding-habit counters CopeNet records that a token dashboard cannot see."""

    runs_with_metrics: int = 0
    tool_calls: int = 0
    distinct_files_read: int = 0
    redundant_reads: int = 0
    reads_after_own_edit: int = 0
    searches: int = 0
    search_dumps: int = 0
    edits: int = 0
    stale_edits: int = 0
    exact_repeats: int = 0
    failures: int = 0
    blocked: int = 0
    blind_retries: int = 0
    verification_commands: int = 0
    verification_tests: int = 0
    runs_with_edits: int = 0
    runs_verified_after_last_edit: int = 0
    failed_verifications_after_edit: int = 0
    edits_after_failed_verification: int = 0

    def add(self, metrics: dict[str, Any]) -> None:
        def section(name: str) -> dict[str, Any]:
            value = metrics.get(name)
            return value if isinstance(value, dict) else {}

        reads = section("reads")
        searches = section("searches")
        edits = section("edits")
        failures = section("failures")
        verification = section("verification")
        recovery = section("recovery")

        self.runs_with_metrics += 1
        self.tool_calls += whole_int(metrics.get("toolCalls"))
        self.distinct_files_read += whole_int(reads.get("distinctFiles"))
        self.redundant_reads += whole_int(reads.get("redundant"))
        self.reads_after_own_edit += whole_int(reads.get("afterOwnEdit"))
        self.searches += whole_int(searches.get("count"))
        self.search_dumps += whole_int(searches.get("overCap"))
        self.edits += whole_int(edits.get("count"))
        self.stale_edits += whole_int(edits.get("staleErrors"))
        self.exact_repeats += whole_int(metrics.get("exactRepeats"))
        self.failures += whole_int(failures.get("count"))
        self.blocked += whole_int(failures.get("blocked"))
        self.blind_retries += whole_int(failures.get("blindRetries"))
        self.verification_commands += whole_int(verification.get("commands"))
        self.verification_tests += whole_int(verification.get("tests"))
        self.failed_verifications_after_edit += whole_int(recovery.get("failedVerificationsAfterEdit"))
        self.edits_after_failed_verification += whole_int(recovery.get("editsAfterFailedVerification"))

        # `afterLastEdit` is None when the run made no edit — there was nothing to
        # verify after, so that run stays outside the rate's denominator entirely.
        after_last_edit = verification.get("afterLastEdit")
        if isinstance(after_last_edit, bool):
            self.runs_with_edits += 1
            if after_last_edit:
                self.runs_verified_after_last_edit += 1

    def to_day_dict(self) -> dict[str, Any]:
        """The per-day slice the habits chart plots."""
        return {
            "runsWithMetrics": self.runs_with_metrics,
            "toolCalls": self.tool_calls,
            "redundantReads": self.redundant_reads,
            "blindRetries": self.blind_retries,
            "edits": self.edits,
            "runsWithEdits": self.runs_with_edits,
            "runsVerifiedAfterLastEdit": self.runs_verified_after_last_edit,
            "verifiedAfterEditRate": ratio(self.runs_verified_after_last_edit, self.runs_with_edits),
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "runsWithMetrics": self.runs_with_metrics,
            "toolCalls": self.tool_calls,
            "distinctFilesRead": self.distinct_files_read,
            "redundantReads": self.redundant_reads,
            "readsAfterOwnEdit": self.reads_after_own_edit,
            "searches": self.searches,
            "searchDumps": self.search_dumps,
            "edits": self.edits,
            "staleEdits": self.stale_edits,
            "exactRepeats": self.exact_repeats,
            "failures": self.failures,
            "blocked": self.blocked,
            "blindRetries": self.blind_retries,
            "verificationCommands": self.verification_commands,
            "verificationTests": self.verification_tests,
            "runsWithEdits": self.runs_with_edits,
            "runsVerifiedAfterLastEdit": self.runs_verified_after_last_edit,
            "verifiedAfterEditRate": ratio(self.runs_verified_after_last_edit, self.runs_with_edits),
            "failedVerificationsAfterEdit": self.failed_verifications_after_edit,
            "editsAfterFailedVerification": self.edits_after_failed_verification,
        }


@dataclass
class ToolBucket:
    """One tool id's call volume, failures and blocked attempts."""

    calls: int = 0
    failures: int = 0
    blocked: int = 0
    runs: set[str] = field(default_factory=set)

    def add(self, run_id: str, step: dict[str, Any]) -> None:
        self.calls += 1
        self.runs.add(run_id)
        if step.get("ok") is False:
            self.failures += 1
        if str(step.get("policyDecision") or "") in BLOCKED_POLICY_DECISIONS:
            self.blocked += 1

    def to_public_dict(self, tool_id: str) -> dict[str, Any]:
        return {
            "toolId": tool_id,
            "calls": self.calls,
            "failures": self.failures,
            "blocked": self.blocked,
            "runs": len(self.runs),
            "failureRate": ratio(self.failures, self.calls),
        }
