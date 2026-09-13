"""Shared model-facing tool response budget."""
import os


def model_facing_result_char_limit() -> int:
    """Body character limit; providers may add their own envelope overhead."""
    raw = os.environ.get("COPNET_MODEL_TOOL_RESULT_CHARS", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if value > 0:
            return value
    # Standard shell results can contain 30K of stdout and 30K of stderr. Keep
    # both streams intact; this backstop is for genuinely exceptional payloads.
    return 80000
