"""Model-aware provider-input budget.

The transcript view sent to a provider is bounded; durable transcript storage is
never touched. The old fixed 48K assumption was text-only and could not see
images, reasoning, tool schemas, or instructions, so raising it would only have
hidden overflow for longer. Measurement is fixed first (see
`orchestrator/messages._item_text_length`), then the target moves to 100K.
"""

from __future__ import annotations

from dataclasses import dataclass

# Normal target for the provider-bound input view. Not a context-window size — a
# deliberate ceiling that leaves room for output and reasoning.
CONTEXT_INPUT_TARGET_TOKENS = 100_000

# Fraction of a model's usable window held back for output + reasoning. Frontier
# reasoning models can spend tens of thousands of tokens before emitting text.
OUTPUT_HEADROOM_RATIO = 0.25

# Never trim below this, regardless of a small local model's advertised window;
# a budget under this is more likely a bad metadata read than a real limit.
MIN_INPUT_BUDGET_TOKENS = 8_000

# Conservative per-provider fallback windows, used only when model metadata does
# not report one. Deliberately pessimistic: assuming a 200K window we do not have
# produces silent overflow, while assuming too little only trims older turns.
_PROVIDER_FALLBACK_CONTEXT_TOKENS: dict[str, int] = {
    "claude-cli": 200_000,
    "openai-codex": 200_000,
    "lm-studio": 32_000,
    "ollama": 32_000,
}
_UNKNOWN_PROVIDER_CONTEXT_TOKENS = 32_000


@dataclass(frozen=True)
class ContextBudget:
    """Resolved input budget for one provider call, plus how it was derived."""

    input_tokens: int
    model_context_tokens: int
    reserved_output_tokens: int
    source: str

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "inputTokenBudget": self.input_tokens,
            "modelContextTokens": self.model_context_tokens,
            "reservedOutputTokens": self.reserved_output_tokens,
            "budgetSource": self.source,
        }


def resolve_context_budget(
    *,
    provider: str,
    model_context_tokens: int | None = None,
) -> ContextBudget:
    """Smallest of: the 100K target, or the model's window minus output headroom.

    `model_context_tokens` should come from provider model metadata when the
    provider reports it. Without it, a conservative per-provider fallback applies
    rather than an optimistic guess.
    """
    if model_context_tokens and model_context_tokens > 0:
        window = int(model_context_tokens)
        source = "model_metadata"
    else:
        window = _PROVIDER_FALLBACK_CONTEXT_TOKENS.get(provider, _UNKNOWN_PROVIDER_CONTEXT_TOKENS)
        source = "provider_fallback"

    usable = int(window * (1.0 - OUTPUT_HEADROOM_RATIO))
    budget = min(CONTEXT_INPUT_TARGET_TOKENS, usable)
    if budget < MIN_INPUT_BUDGET_TOKENS:
        budget = MIN_INPUT_BUDGET_TOKENS
        source = f"{source}_floored"
    return ContextBudget(
        input_tokens=budget,
        model_context_tokens=window,
        reserved_output_tokens=window - usable,
        source=source,
    )
