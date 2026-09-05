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
    return 30000
