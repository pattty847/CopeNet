"""Bounded Telegram sendMessage adapter; credentials never cross its boundary."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class TelegramReceipt:
    status: str
    message_id: int | None = None
    error: str | None = None
    retry_after: int | None = None


def telegram_transport_configured() -> bool:
    return bool(os.environ.get("COPNET_TELEGRAM_BOT_TOKEN", "").strip())


def send_telegram_message(target: str, text: str) -> TelegramReceipt:
    """Never retry an ambiguous write. Only a successful API receipt proves sent.

    API contract: https://core.telegram.org/bots/api#sendmessage and
    https://core.telegram.org/bots/api#responseparameters.
    """
    if not text or len(text.encode("utf-16-le")) // 2 > 4096:
        return TelegramReceipt("failed", error="Telegram message exceeds the 4096-character limit.")
    return _send(target, "sendMessage", json.dumps({
        "chat_id": target, "text": text, "link_preview_options": {"is_disabled": True},
    }).encode(), "application/json")


def send_telegram_photo(target: str, caption: str, photo: bytes) -> TelegramReceipt:
    """Upload one frozen PNG and caption as one write/receipt (Bot API sendPhoto)."""
    if len(caption.encode("utf-16-le")) // 2 > 1024:
        return TelegramReceipt("failed", error="Telegram photo caption exceeds the 1024-character limit.")
    if not photo.startswith(b"\x89PNG\r\n\x1a\n") or len(photo) > 10 * 1024 * 1024:
        return TelegramReceipt("failed", error="Chart must be a PNG of at most 10 MiB.")
    boundary = "copenet-" + uuid4().hex
    parts = []
    for name, value in (("chat_id", target), ("caption", caption)):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="chart.png"\r\nContent-Type: image/png\r\n\r\n'.encode() + photo + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return _send(target, "sendPhoto", b"".join(parts), f"multipart/form-data; boundary={boundary}")


def _send(target: str, method: str, data: bytes, content_type: str) -> TelegramReceipt:
    token = os.environ.get("COPNET_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return TelegramReceipt("failed", error="Telegram transport is not configured on this host.")
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
        return TelegramReceipt("failed", error="Telegram bot credential has an invalid format.")
    if not re.fullmatch(r"(?:-?[0-9]+|@[A-Za-z0-9_]+)", target):
        return TelegramReceipt("failed", error="Telegram destination must be a chat ID or @username.")
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}", data=data,
        headers={"Content-Type": content_type}, method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read(65537)
    except HTTPError as exc:
        body = exc.read(65537)
    except (URLError, TimeoutError, OSError):
        # Exception strings often include the credential-bearing URL. Never retain them.
        return TelegramReceipt("uncertain", error="Telegram delivery could not be confirmed. Check the chat before retrying.")
    try:
        if len(body) > 65536:
            raise ValueError("oversized response")
        payload = json.loads(body)
        if not isinstance(payload, dict) or type(payload.get("ok")) is not bool:
            raise ValueError("invalid response")
        if payload["ok"]:
            result = payload.get("result")
            if not isinstance(result, dict) or type(result.get("message_id")) is not int:
                raise ValueError("missing receipt")
            return TelegramReceipt("sent", message_id=result["message_id"])
        code = payload.get("error_code")
        parameters = payload.get("parameters", {})
        delay = parameters.get("retry_after") if isinstance(parameters, dict) else None
        if code == 429 and type(delay) is int and delay > 0:
            return TelegramReceipt("queued", error="Telegram rate limit; waiting before retry.", retry_after=delay)
        # Avoid reflecting Telegram descriptions, which can contain target identifiers.
        if code in {400, 401, 403, 404}:
            return TelegramReceipt("failed", error=f"Telegram rejected the request ({code}). Check bot access and destination.")
        return TelegramReceipt("uncertain", error="Telegram returned an unconfirmed result. Check the chat before retrying.")
    except (ValueError, UnicodeError):
        return TelegramReceipt("uncertain", error="Telegram returned an unreadable receipt. Check the chat before retrying.")
