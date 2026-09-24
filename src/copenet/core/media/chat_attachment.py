"""Render a media asset's transcript as a chat attachment."""

from __future__ import annotations

from typing import Any

# Display names ride in the chat UI chip; keep them short and filesystem-safe.
_MAX_FILENAME_TITLE_CHARS = 80
_UNSAFE_FILENAME_CHARS = '/\\:*?"<>|'


def render_transcript_attachment(asset: dict[str, Any]) -> tuple[str, str]:
    """Return `(filename, text)` for one asset detail payload.

    The text leads with where the transcript came from so the model can cite
    the video and weigh caption-vs-Whisper accuracy, then carries every word.
    """
    title = str(asset.get("title") or "").strip() or "Untitled media"
    header = [f'Transcript of "{title}"']
    if asset.get("sourceUrl"):
        header.append(f"Source: {asset['sourceUrl']}")
    if asset.get("transcriptSource"):
        header.append(f"Transcribed from: {asset['transcriptSource']}")
    duration = asset.get("durationSeconds")
    if duration:
        minutes, seconds = divmod(int(duration), 60)
        header.append(f"Length: {minutes}:{seconds:02d}")
    transcript = str(asset.get("transcriptContent") or "").strip() or "(No transcript text was saved for this asset.)"
    safe_title = "".join("-" if ch in _UNSAFE_FILENAME_CHARS else ch for ch in title)
    filename = f"{safe_title[:_MAX_FILENAME_TITLE_CHARS].strip()}.txt"
    return filename, "\n".join(header) + "\n\n" + transcript
