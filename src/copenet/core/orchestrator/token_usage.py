"""Sum provider-reported token usage across one run's model calls."""

from __future__ import annotations

from typing import Any


def summarize_token_usage(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the run-level usage record, or None when no provider reported usage.

    `inputTokens` is the billed sum across model calls: every tool step re-sends
    the whole context. `peakInputTokens` is the largest single call — the number
    that says how big the context actually was.
    """
    if not steps:
        return None

    def total(key: str) -> int | None:
        values = [step[key] for step in steps if step.get(key) is not None]
        return sum(values) if values else None

    inputs = [step["inputTokens"] for step in steps if step.get("inputTokens") is not None]
    return {
        "source": "provider",
        "modelCalls": len(steps),
        "inputTokens": total("inputTokens"),
        "peakInputTokens": max(inputs) if inputs else None,
        "cachedInputTokens": total("cachedInputTokens"),
        "outputTokens": total("outputTokens"),
        "reasoningTokens": total("reasoningTokens"),
        "steps": [dict(step) for step in steps],
    }
