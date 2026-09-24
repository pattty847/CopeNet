"""Resolve a stored chat attachment into one model-input content part."""

from __future__ import annotations

from typing import Any

from copenet.core.attachments import ChatAttachmentStore
from copenet.core.harness.responses_items import image_content_part, text_attachment_part


def attachment_content_part(attachment_store: ChatAttachmentStore, attachment_id: str) -> dict[str, Any] | None:
    """An image becomes `input_image`, a text file `input_text`; missing ids resolve to None."""
    attachment = attachment_store.get(attachment_id)
    if attachment is None:
        return None
    if attachment.is_text:
        text = attachment_store.read_text(attachment_id)
        return text_attachment_part(attachment.filename, text) if text is not None else None
    data_url = attachment_store.data_url(attachment_id)
    return image_content_part(data_url) if data_url else None
