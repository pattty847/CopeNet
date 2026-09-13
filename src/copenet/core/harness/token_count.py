"""Real token counts for model-facing text.

One counter for every budget in the process. Before this existed the harness,
the chart projection and the tool loops all divided character counts by four.
Numeric CSV tokenizes at roughly 2.2 characters per token, so a chart packet
that "estimated" at 17.6K tokens actually cost 32K — every budget built on that
number was blind by almost 2x.

`o200k_base` is the encoding for every current OpenAI model (gpt-4o, gpt-4.1,
gpt-5.x, o-series). Claude and local runtimes use their own tokenizers, so for
them this is a close proxy rather than an exact count — still far closer than
a character quotient, and the same number everywhere.
"""

from __future__ import annotations

import functools

import tiktoken

TOKEN_ENCODING = "o200k_base"


@functools.lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(TOKEN_ENCODING)


@functools.lru_cache(maxsize=64)
def count_text_tokens(text: str) -> int:
    """Return the token count of one string.

    Cached on the string itself: budget fitting re-measures the same large
    packet many times while it searches for the row count that fits.
    """
    if not text:
        return 0
    return len(_encoding().encode(text, disallowed_special=()))
