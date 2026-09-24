"""Chat attachment storage for CopeNet.

A lightweight, disk-backed store for images and text files attached to chat
messages. Separate from the media library (`core/media/`), which is a
transcription/ingestion lane with its own asset model; a media asset's
transcript becomes a text attachment here when the operator discusses it.

Flow:
- The composer uploads an image to `POST /api/v1/chat/attachments`, or a media
  asset is turned into a text attachment by
  `POST /api/v1/media/assets/{id}/chat-attachment`. Both call
  `ChatAttachmentStore.save(...)` and return an attachment id + metadata.
- `chat.send` carries `attachmentIds`. The orchestrator resolves each id to a
  content part (`core/orchestrator/attachment_parts.py`): an image becomes an
  `input_image` part carrying a base64 data URL, a text file an `input_text`
  part carrying its contents.
- The user transcript message persists the attachment metadata so later turns can
  re-inline the same attachments (multi-turn vision, and a transcript that stays
  in context for every follow-up).

Bytes live on disk under `<root>/<id>.<ext>`; a `<id>.json` sidecar holds the
metadata. Nothing here mutates session state, so it sidesteps session-semantics
locking entirely.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from copenet._paths import default_chat_attachments_dir


# The codex/Responses backend accepts images as `input_image` content parts.
SUPPORTED_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}

# Text rides into the model input verbatim as an `input_text` part.
SUPPORTED_TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
}

# Hard cap on a single attachment. Inlined images ride inside the request body to
# the model, so keep this conservative to avoid oversized payloads.
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
# Text is re-sent on every turn of the session, so its cap is about context
# budget, not transport: ~400 KB is roughly 100k tokens, several hours of speech.
MAX_TEXT_ATTACHMENT_BYTES = 400 * 1024


class ChatAttachmentError(ValueError):
    """Raised when an attachment is rejected (unsupported type, too large, ...)."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ext_for_mime(mime_type: str, filename: str) -> str:
    guessed = mimetypes.guess_extension(mime_type or "")
    if guessed:
        return guessed
    suffix = Path(filename or "").suffix
    return suffix or ".bin"


@dataclass(frozen=True)
class ChatAttachment:
    """One stored chat attachment (metadata only; bytes live alongside on disk)."""

    attachment_id: str
    mime_type: str
    filename: str
    size_bytes: int
    created_at: str
    path: Path

    @property
    def is_text(self) -> bool:
        return self.mime_type in SUPPORTED_TEXT_MIME_TYPES

    def to_public_dict(self) -> dict[str, Any]:
        """Wire shape returned to the UI (camelCase, no local path)."""
        return {
            "attachmentId": self.attachment_id,
            "mimeType": self.mime_type,
            "filename": self.filename,
            "sizeBytes": self.size_bytes,
            "createdAt": self.created_at,
        }

    def to_transcript_ref(self) -> dict[str, Any]:
        """Minimal reference persisted on a transcript message for replay."""
        return {
            "attachmentId": self.attachment_id,
            "mimeType": self.mime_type,
            "filename": self.filename,
        }


class ChatAttachmentStore:
    """File-backed store for chat image and text attachments."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir if root_dir is not None else default_chat_attachments_dir()
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _meta_path(self, attachment_id: str) -> Path:
        return self._root_dir / f"{self._safe_id(attachment_id)}.json"

    @staticmethod
    def _safe_id(attachment_id: str) -> str:
        safe = "".join(ch for ch in attachment_id if ch.isalnum() or ch in ("-", "_")).strip()
        if not safe:
            raise ChatAttachmentError("invalid attachment id")
        return safe

    def save(self, *, data: bytes, mime_type: str, filename: str) -> ChatAttachment:
        """Persist one image or text attachment and return its metadata.

        Raises ChatAttachmentError for unsupported types or oversized payloads.
        """
        normalized_mime = (mime_type or "").split(";")[0].strip().lower()
        supported = SUPPORTED_IMAGE_MIME_TYPES | SUPPORTED_TEXT_MIME_TYPES
        if normalized_mime not in supported:
            raise ChatAttachmentError(
                f"unsupported attachment type: {normalized_mime or 'unknown'} "
                f"(supported: {', '.join(sorted(supported))})"
            )
        if not data:
            raise ChatAttachmentError("attachment is empty")
        limit = MAX_TEXT_ATTACHMENT_BYTES if normalized_mime in SUPPORTED_TEXT_MIME_TYPES else MAX_ATTACHMENT_BYTES
        if len(data) > limit:
            raise ChatAttachmentError(
                f"attachment too large: {len(data)} bytes (limit {limit})"
            )

        attachment_id = uuid4().hex
        safe_name = (filename or "image").strip() or "image"
        ext = _ext_for_mime(normalized_mime, safe_name)
        blob_path = self._root_dir / f"{attachment_id}{ext}"
        attachment = ChatAttachment(
            attachment_id=attachment_id,
            mime_type=normalized_mime,
            filename=safe_name,
            size_bytes=len(data),
            created_at=_utc_now_iso(),
            path=blob_path,
        )
        with self._lock:
            blob_path.write_bytes(data)
            meta = {
                **attachment.to_public_dict(),
                "blobName": blob_path.name,
            }
            self._meta_path(attachment_id).write_text(
                json.dumps(meta, ensure_ascii=False), encoding="utf-8"
            )
        return attachment

    def get(self, attachment_id: str) -> ChatAttachment | None:
        """Resolve stored metadata for an attachment id, or None if absent."""
        meta_path = self._meta_path(attachment_id)
        if not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(meta, dict):
            return None
        blob_name = str(meta.get("blobName") or "")
        blob_path = self._root_dir / blob_name if blob_name else None
        if blob_path is None or not blob_path.exists():
            return None
        return ChatAttachment(
            attachment_id=str(meta.get("attachmentId") or attachment_id),
            mime_type=str(meta.get("mimeType") or "application/octet-stream"),
            filename=str(meta.get("filename") or blob_name),
            size_bytes=int(meta.get("sizeBytes") or blob_path.stat().st_size),
            created_at=str(meta.get("createdAt") or _utc_now_iso()),
            path=blob_path,
        )

    def read_bytes(self, attachment_id: str) -> bytes | None:
        """Return the raw bytes for an attachment, or None if missing."""
        attachment = self.get(attachment_id)
        if attachment is None:
            return None
        try:
            return attachment.path.read_bytes()
        except OSError:
            return None

    def read_text(self, attachment_id: str) -> str | None:
        """Return a text attachment's contents, or None if missing or not text."""
        attachment = self.get(attachment_id)
        if attachment is None or not attachment.is_text:
            return None
        raw = self.read_bytes(attachment_id)
        if raw is None:
            return None
        return raw.decode("utf-8", errors="replace")

    def data_url(self, attachment_id: str) -> str | None:
        """Return a base64 data URL (`data:<mime>;base64,<...>`) for the image.

        This is the exact form the Responses/codex backend accepts in an
        `input_image` content part's `image_url` field.
        """
        attachment = self.get(attachment_id)
        if attachment is None:
            return None
        raw = self.read_bytes(attachment_id)
        if raw is None:
            return None
        encoded = base64.b64encode(raw).decode("ascii")
        return f"data:{attachment.mime_type};base64,{encoded}"


__all__ = [
    "ChatAttachment",
    "ChatAttachmentError",
    "ChatAttachmentStore",
    "MAX_ATTACHMENT_BYTES",
    "MAX_TEXT_ATTACHMENT_BYTES",
    "SUPPORTED_IMAGE_MIME_TYPES",
    "SUPPORTED_TEXT_MIME_TYPES",
]
