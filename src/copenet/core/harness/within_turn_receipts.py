"""Within-turn receipts: shrink old read-only results in the live tool loop's array.

Every step of the Responses loop re-sends the whole input[] array. A file read
at step 3 is still in full at step 20, on every request in between, and a
large-repo turn reaches 40–80K tokens of context that way. Cross-turn replay
already solved this for *earlier* turns (`replay_receipts.py`); this applies the
same receipt shapes inside the turn that is running.

Rules, in this order:

- Nothing happens until the request estimate crosses `RECEIPT_TRIGGER_TOKENS`.
  Small turns are never touched: a receipt there saves nothing and can cost a read.
- The most recent `KEEP_RECENT_STEPS` steps stay verbatim. The model is working
  from them right now (Claude Code keeps 3 as well).
- `files.edit` / `files.write` results and any failed call stay verbatim at any
  age — exactly the cross-turn rule. Chart tool results too.
- A pass rewrites every eligible older result at once, and only when it would
  free at least `MIN_FREED_TOKENS`. Rewriting the front of the array breaks the
  provider's prefix cache for every later step, so passes must be rare and
  large, never one item per step.
- The durable transcript keeps the full body; only the copy handed to the model
  on later steps shrinks. `files.read` (or `artifact.read`) brings it back.

The prompted lane (claude-cli) is not touched: with `--resume` the provider
holds the thread and there is no array to rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from copenet.core.harness.replay_receipts import is_verbatim, replay_output
from copenet.core.harness.token_count import count_text_tokens

RECEIPT_TRIGGER_TOKENS = 32_000
KEEP_RECENT_STEPS = 3
MIN_FREED_TOKENS = 8_000


@dataclass
class LiveToolResult:
    """What the loop knows about one function_call_output it appended."""

    call_id: str
    step: int
    tool_execution: dict[str, Any]
    receipted: bool = False


def remember_result(
    results: dict[str, LiveToolResult],
    *,
    call_id: str,
    step: int,
    tool_id: str,
    ok: bool,
    summary: str | None,
    error: str | None,
    artifact_id: str | None,
    arguments: dict[str, Any],
    output: str,
) -> None:
    results[call_id] = LiveToolResult(
        call_id=call_id,
        step=step,
        tool_execution={
            "toolId": tool_id,
            "ok": ok,
            "summary": summary,
            "error": error,
            "artifactId": artifact_id,
            "arguments": dict(arguments),
            "replayOutput": output,
        },
    )


def apply_within_turn_receipts(
    working_messages: list[dict[str, Any]],
    results: dict[str, LiveToolResult],
    *,
    current_step: int,
    request_tokens: int,
    trigger_tokens: int | None = None,
    keep_recent_steps: int | None = None,
    min_freed_tokens: int | None = None,
) -> dict[str, Any] | None:
    """Receipt every eligible old result in place. Returns the pass stats, or None when nothing changed."""
    trigger = RECEIPT_TRIGGER_TOKENS if trigger_tokens is None else trigger_tokens
    keep = KEEP_RECENT_STEPS if keep_recent_steps is None else keep_recent_steps
    min_freed = MIN_FREED_TOKENS if min_freed_tokens is None else min_freed_tokens
    if request_tokens <= trigger:
        return None
    newest_eligible_step = current_step - keep
    planned: list[tuple[dict[str, Any], LiveToolResult, str, int, int]] = []
    for item in working_messages:
        if item.get("type") != "function_call_output":
            continue
        entry = results.get(str(item.get("call_id") or ""))
        if entry is None or entry.receipted or entry.step > newest_eligible_step:
            continue
        if is_verbatim(entry.tool_execution):
            continue
        current = str(item.get("output") or "")
        receipt = replay_output(entry.tool_execution, receipt=True, where=f"step {entry.step} of this turn")
        if len(receipt) >= len(current):
            continue
        before = count_text_tokens(current)
        after = count_text_tokens(receipt)
        planned.append((item, entry, receipt, before, after))
    freed = sum(before - after for _, _, _, before, after in planned)
    if not planned or freed < min_freed:
        return None
    receipted: list[dict[str, Any]] = []
    for item, entry, receipt, before, after in planned:
        item["output"] = receipt
        entry.receipted = True
        arguments = entry.tool_execution.get("arguments") or {}
        receipted.append(
            {
                "callId": entry.call_id,
                "step": entry.step,
                "toolId": entry.tool_execution.get("toolId"),
                "target": str(arguments.get("path") or arguments.get("pattern") or arguments.get("command") or arguments.get("url") or "")[:120],
                "tokensBefore": before,
                "tokensAfter": after,
            }
        )
    return {
        "step": current_step,
        "requestTokensBefore": request_tokens,
        "requestTokensAfter": request_tokens - freed,
        "freedTokens": freed,
        "itemsReceipted": len(receipted),
        "keepRecentSteps": keep,
        "triggerTokens": trigger,
        "receipted": receipted,
    }
