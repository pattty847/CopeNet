"""Market-only delivery outbox; no market-data calls or alert re-evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import time
from typing import Callable
from urllib.parse import quote, urlsplit
from uuid import uuid4

from .market_outbox import MarketOutbox
from .store import MessagingConfigRecord
from .telegram_delivery import TelegramReceipt, send_telegram_message, telegram_transport_configured

ConfigLoader = Callable[[], MessagingConfigRecord]
RuleActive = Callable[[str, int], bool]
Transport = Callable[[str, str], TelegramReceipt]
PENDING = {"queued", "approval_required", "failed", "uncertain", "sending"}


def _timestamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _ticker_link(symbol: str) -> str:
    # Do not derive a public link from an incoming Host header or include auth tokens.
    base = os.environ.get("COPNET_PUBLIC_URL", "").strip().rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return f"Open Market → {symbol}"
    return f"{base}/market/{quote(symbol, safe='')}"


def market_event_message(event: dict) -> str:
    text = (
        f"CopeNet · {event['symbol']} · {event['timeframe']}\n"
        f"{event['condition']}\n"
        f"Observed: {event['leftValue']} / {event['rightValue']}\n"
        f"Candle closed: {event['candleCloseAt']}\n"
        f"Evaluated: {event['evaluatedAt']}\n"
        f"{_ticker_link(event['symbol'])}"
    )
    if len(text.encode("utf-16-le")) // 2 > 4096:
        raise ValueError("Alert evidence exceeds Telegram's message limit")
    return text


def enqueue_market_event(root: Path, event: dict, destination_ids: list[str], authorized: bool = False) -> list[dict]:
    """Persist an immutable message once per event/destination. Never send here."""
    outbox = MarketOutbox(root)
    text = market_event_message(event)
    return [_public(outbox.insert(_row(
        event["eventId"], event["alertId"], event["revision"], destination_id, text, authorized,
    ))) for destination_id in dict.fromkeys(destination_ids)]


def _row(event_id: str, alert_id: str | None, revision: int, destination_id: str, text: str, authorized: bool) -> dict:
    now = time.time()
    return {
        "id": sha256(f"{event_id}\0{destination_id}".encode()).hexdigest(),
        "eventId": event_id, "alertId": alert_id, "revision": revision,
        "destinationId": destination_id, "text": text,
        "authorized": authorized, "approvedAt": None,
        "status": "queued" if authorized else "approval_required",
        "createdAt": _timestamp(now), "updatedAt": _timestamp(now),
        "attempts": [], "nextAttemptAt": None, "sentAt": None,
        "messageId": None, "error": None,
    }


def _public(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in {"authorized", "targetFingerprint"}}


def _destination(config: MessagingConfigRecord, destination_id: str):
    return next((item for item in config.destinations if item.id == destination_id), None)


def _blocked(config: MessagingConfigRecord, destination) -> bool:
    identities = {destination.id.casefold(), destination.target.casefold(), f"telegram:{destination.target}".casefold()}
    return bool(identities.intersection(item.strip().casefold() for item in config.approval_policy.hardline_blocklist))


def market_notifications_state(root: Path, config_loader: ConfigLoader) -> dict:
    config = config_loader()
    destinations = []
    for item in config.destinations:
        if item.platform != "telegram":
            continue
        destinations.append({
            "id": item.id,
            "displayName": item.display_name if item.display_name != item.target else "Telegram destination",
            "status": "blocked" if _blocked(config, item) else item.status,
            "requiresApproval": config.approval_policy.require_approval_by_default or item.requires_approval,
        })
    return {
        "transportConfigured": telegram_transport_configured(),
        "destinations": destinations,
        "deliveries": [_public(row) for row in MarketOutbox(root).rows()[:200]],
    }


def _cancel_invalid(outbox: MarketOutbox, row: dict, config: MessagingConfigRecord, rule_active: RuleActive) -> bool:
    destination = _destination(config, row["destinationId"])
    reason = None
    if row["alertId"] and not rule_active(row["alertId"], row["revision"]):
        reason = "Alert was paused, removed, or revised before delivery."
    elif not destination or destination.platform != "telegram" or destination.status != "configured":
        reason = "Destination is unavailable or disabled."
    elif _blocked(config, destination):
        reason = "Destination is blocked by messaging policy."
    if reason:
        row.update(status="cancelled", error=reason, nextAttemptAt=None, updatedAt=_timestamp(time.time()))
        outbox.save(row)
        return True
    return False


def process_market_deliveries(
    root: Path, config_loader: ConfigLoader, rule_active: RuleActive,
    *, transport: Transport = send_telegram_message, now: float | None = None,
    only_delivery_id: str | None = None,
) -> list[dict]:
    """One bounded batch; a host scheduler may invoke this independently of scans."""
    outbox = MarketOutbox(root)
    clock = time.time() if now is None else now
    with outbox.sender_lock(blocking=False) as acquired:
        if not acquired:
            return []
        rows = list(reversed(outbox.rows()))
        retry_gate = max((datetime.fromisoformat(row["nextAttemptAt"]).timestamp()
                          for row in rows if row["status"] == "queued" and row["nextAttemptAt"]), default=0)
        sent_this_batch = 0
        for row in rows:
            if row["status"] not in PENDING:
                continue
            config = config_loader()
            if _cancel_invalid(outbox, row, config, rule_active):
                continue
            if row["status"] == "sending":
                row.update(status="uncertain", error="Sender stopped before saving a receipt. Check the chat before retrying.")
                if row["attempts"]:
                    row["attempts"][-1].update(status="uncertain", error=row["error"])
                outbox.save(row)
                continue
            if only_delivery_id and row["id"] != only_delivery_id:
                continue
            if row["status"] not in {"queued", "approval_required"}:
                continue
            destination = _destination(config, row["destinationId"])
            # A permissive global default is not consent to automate a new alert.
            # A per-rule grant or one-message approval satisfies approval defaults.
            if not (row["authorized"] or row["approvedAt"]):
                row["status"] = "approval_required"
                outbox.save(row)
                continue
            if row["nextAttemptAt"] and datetime.fromisoformat(row["nextAttemptAt"]).timestamp() > clock:
                continue
            if retry_gate > clock:
                continue
            if sent_this_batch >= 10:
                break
            fingerprint = sha256(destination.target.encode()).hexdigest()
            if row.get("targetFingerprint") and row["targetFingerprint"] != fingerprint:
                row.update(status="cancelled", error="Destination changed after the first attempt. Create a new alert or test.")
                outbox.save(row)
                continue
            row.update(status="sending", updatedAt=_timestamp(clock), targetFingerprint=fingerprint)
            attempt = {"startedAt": _timestamp(clock), "status": "sending", "error": None}
            row["attempts"].append(attempt)
            outbox.save(row)  # Commit before the network write, so crashes never cause automatic duplicates.
            try:
                receipt = transport(destination.target, row["text"])
            except Exception:
                receipt = TelegramReceipt("uncertain", error="Sender failed without a confirmed receipt. Check the chat before retrying.")
            sent_this_batch += 1
            attempt.update(status=receipt.status, error=receipt.error)
            row.update(status=receipt.status, error=receipt.error, updatedAt=_timestamp(clock), nextAttemptAt=None)
            if receipt.status == "sent":
                row.update(messageId=receipt.message_id, sentAt=_timestamp(clock))
            elif receipt.status == "queued":
                if len(row["attempts"]) >= 5:
                    row.update(status="failed", error="Telegram rate-limit retry budget exhausted; retry manually.")
                else:
                    row["nextAttemptAt"] = _timestamp(clock + max(receipt.retry_after or 1, 2 ** len(row["attempts"])))
            outbox.save(row)
            if receipt.status == "queued":
                break  # Telegram flood control applies to the bot, not just this event.
    return [_public(row) for row in outbox.rows()[:200]]


def market_delivery_action(root: Path, delivery_id: str, action: str, *, acknowledge_duplicate_risk: bool = False) -> dict:
    outbox = MarketOutbox(root)
    with outbox.sender_lock():
        row = next((item for item in outbox.rows() if item["id"] == delivery_id), None)
        if row is None:
            raise ValueError("Delivery not found")
        if action == "cancel" and row["status"] in PENDING:
            row.update(status="cancelled", nextAttemptAt=None, error="Cancelled by operator.")
        elif action == "approve" and row["status"] == "approval_required":
            row.update(status="queued", approvedAt=_timestamp(time.time()), error=None)
        elif action == "retry" and row["status"] in {"failed", "uncertain"}:
            if row["status"] == "uncertain" and not acknowledge_duplicate_risk:
                raise ValueError("Confirm you checked the chat; retrying an uncertain delivery can duplicate the message")
            row.update(status="queued", approvedAt=_timestamp(time.time()), nextAttemptAt=None, error=None)
        else:
            raise ValueError("This action is not available for the delivery's current state")
        row["updatedAt"] = _timestamp(time.time())
        outbox.save(row)
        return _public(row)


def enqueue_market_test(root: Path, destination_id: str) -> dict:
    """Explicit operator Test authorizes this fixed message, not future alerts."""
    return _public(MarketOutbox(root).insert(_row(
        f"test-{uuid4()}", None, 0, destination_id,
        "CopeNet · Telegram delivery test\nThis confirms delivery only; no scan was run and no alert was evaluated.", True,
    )))


def cancel_market_rule_deliveries(root: Path, alert_id: str) -> None:
    outbox = MarketOutbox(root)
    with outbox.sender_lock():
        for row in outbox.rows():
            if row["alertId"] == alert_id and row["status"] in PENDING:
                row.update(status="cancelled", nextAttemptAt=None, error="Alert changed or was disabled by operator.")
                outbox.save(row)
