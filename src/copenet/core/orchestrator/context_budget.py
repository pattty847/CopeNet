"""Model-aware provider-input budget."""

from __future__ import annotations

from dataclasses import dataclass

# Absolute product ceiling for one provider-bound input. A model's own window can
# lower this further; a larger advertised window never raises it.
CONTEXT_INPUT_TARGET_TOKENS = 168_000

# Only this fraction of the advertised context window may be accumulated as input.
# The remainder belongs to output, reasoning and provider-side envelope variance.
INPUT_WINDOW_RATIO = 0.60

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
    """Use at most 60% of the model window, bounded by the product ceiling.

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

    usable = max(int(window * INPUT_WINDOW_RATIO), 1)
    budget = min(CONTEXT_INPUT_TARGET_TOKENS, usable)
    return ContextBudget(
        input_tokens=budget,
        model_context_tokens=window,
        reserved_output_tokens=window - budget,
        source=source,
    )


async def discover_model_context_tokens(provider, model: str | None) -> int | None:
    """Read a selected model's declared window without trusting malformed metadata."""
    try:
        models = await provider.list_models()
    except Exception:
        return None
    chat_models = [item for item in models if getattr(item, "kind", None) == "chat"]
    selected = next((item for item in chat_models if item.id == model), None)
    if selected is None and model is None and len(chat_models) == 1:
        selected = chat_models[0]
    metadata = getattr(selected, "metadata", None) if selected is not None else None
    raw = metadata.get("maxContextLength") if isinstance(metadata, dict) else None
    if type(raw) is int and raw > 0:
        return raw
    if isinstance(raw, str) and raw.isdigit() and int(raw) > 0:
        return int(raw)
    return None
