"""The one transcript timestamp format: `[HH:MM:SS] text`, one line per cue.

Captions and Whisper both write it, so a transcript reads the same whichever
path produced it, and the model can cite when something was said.
"""

from __future__ import annotations

import re

TIMESTAMP_PATTERN = re.compile(r"\[\d{2}:\d{2}:\d{2}\]\s*")


def format_timestamp(seconds: float) -> str:
    total = max(int(seconds), 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def timestamped_line(seconds: float, text: str) -> str:
    return f"[{format_timestamp(seconds)}] {text}"


def has_timestamps(transcript: str) -> bool:
    return TIMESTAMP_PATTERN.search(transcript) is not None


def strip_timestamps(transcript: str) -> str:
    return TIMESTAMP_PATTERN.sub("", transcript)
