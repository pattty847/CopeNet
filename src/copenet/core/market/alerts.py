"""Durable one-shot price alerts evaluated against split-adjusted daily closes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import logging
import math
import threading
from typing import Any, Literal
from uuid import uuid4

from copenet.core._json_store import append_jsonl, read_json, write_json_atomic
from copenet.core.pulse import PulseRecord

from .price_history import daily_close_available_at


AlertDirection = Literal["above", "below"]
AlertStatus = Literal["active", "triggered", "cancelled"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PriceAlert:
    alert_id: str
    symbol: str
    direction: AlertDirection
    threshold: float
    status: AlertStatus
    evaluation_basis: Literal["daily_close"]
    created_at: str
    updated_at: str
    last_observed_price: float
    last_evaluated_at: str | None = None
    triggered_at: str | None = None
    trigger_price: float | None = None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "PriceAlert":
        direction = str(raw.get("direction") or "")
        status = str(raw.get("status") or "")
        if direction not in {"above", "below"}:
            raise ValueError("alert direction must be above or below")
        if status not in {"active", "triggered", "cancelled"}:
            raise ValueError("alert status is invalid")
        return cls(
            alert_id=str(raw["alert_id"]),
            symbol=str(raw["symbol"]).strip().upper(),
            direction=direction,
            threshold=float(raw["threshold"]),
            status=status,
            evaluation_basis="daily_close",
            created_at=str(raw["created_at"]),
            updated_at=str(raw["updated_at"]),
            last_observed_price=float(raw["last_observed_price"]),
            last_evaluated_at=_optional_text(raw.get("last_evaluated_at")),
            triggered_at=_optional_text(raw.get("triggered_at")),
            trigger_price=_optional_float(raw.get("trigger_price")),
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "alertId": self.alert_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "threshold": self.threshold,
            "status": self.status,
            "evaluationBasis": self.evaluation_basis,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "lastObservedPrice": self.last_observed_price,
            "lastEvaluatedAt": self.last_evaluated_at,
            "triggeredAt": self.triggered_at,
            "triggerPrice": self.trigger_price,
        }


class PriceAlertStore:
    """Thread-safe alert rule store with an append-only trigger-event log."""

    def __init__(self, market_root: Path) -> None:
        self._path = market_root / "alerts" / "rules.json"
        self._events_path = market_root / "alerts" / "events.jsonl"
        self._lock = threading.RLock()

    def list(self, *, symbol: str | None = None, status: AlertStatus | None = None) -> list[PriceAlert]:
        with self._lock:
            alerts = self._load()
        if symbol:
            normalized = symbol.strip().upper()
            alerts = [alert for alert in alerts if alert.symbol == normalized]
        if status:
            alerts = [alert for alert in alerts if alert.status == status]
        return sorted(alerts, key=lambda alert: alert.created_at, reverse=True)

    def create(
        self,
        *,
        symbol: str,
        direction: AlertDirection,
        threshold: float,
        reference_price: float,
    ) -> PriceAlert:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        if direction not in {"above", "below"}:
            raise ValueError("direction must be above or below")
        if (
            not math.isfinite(threshold)
            or not math.isfinite(reference_price)
            or threshold <= 0
            or reference_price <= 0
        ):
            raise ValueError("threshold and referencePrice must be positive")
        now = _now_iso()
        alert = PriceAlert(
            alert_id=f"price-alert-{uuid4().hex[:12]}",
            symbol=normalized,
            direction=direction,
            threshold=round(float(threshold), 6),
            status="active",
            evaluation_basis="daily_close",
            created_at=now,
            updated_at=now,
            last_observed_price=float(reference_price),
        )
        with self._lock:
            alerts = self._load()
            alerts.append(alert)
            self._save(alerts)
        return alert

    def cancel(self, alert_id: str) -> PriceAlert:
        with self._lock:
            alerts = self._load()
            for index, alert in enumerate(alerts):
                if alert.alert_id == alert_id.strip():
                    if alert.status == "triggered":
                        raise ValueError("a triggered alert cannot be cancelled")
                    updated = replace(alert, status="cancelled", updated_at=_now_iso())
                    alerts[index] = updated
                    self._save(alerts)
                    return updated
        raise ValueError(f"no alert found: {alert_id}")

    def evaluate(self, prices: dict[str, float], *, close_times: dict[str, datetime] | None = None) -> list[PriceAlert]:
        """Evaluate every active rule atomically and return newly triggered rules."""
        now = _now_iso()
        triggered: list[PriceAlert] = []
        with self._lock:
            alerts = self._load()
            updated_alerts: list[PriceAlert] = []
            for alert in alerts:
                current = prices.get(alert.symbol)
                if alert.status != "active" or current is None or current <= 0:
                    updated_alerts.append(alert)
                    continue
                # A rule armed intraday must not fire backwards against yesterday's close.
                if close_times is not None and close_times[alert.symbol] <= datetime.fromisoformat(alert.created_at):
                    updated_alerts.append(alert)
                    continue
                crossed = (
                    alert.last_observed_price < alert.threshold <= current
                    if alert.direction == "above"
                    else alert.last_observed_price > alert.threshold >= current
                )
                updated = replace(
                    alert,
                    status="triggered" if crossed else "active",
                    updated_at=now,
                    last_observed_price=current,
                    last_evaluated_at=now,
                    triggered_at=now if crossed else None,
                    trigger_price=current if crossed else None,
                )
                updated_alerts.append(updated)
                if crossed:
                    triggered.append(updated)
            for alert in triggered:
                append_jsonl(
                    self._events_path,
                    {
                        # Stable identity makes a rare append-before-save retry deduplicable.
                        "eventId": f"market-alert-event-{alert.alert_id}",
                        "type": "price_crossed",
                        "occurredAt": now,
                        "alert": alert.to_wire(),
                    },
                )
            # Persist status only after every canonical event is durable. If event append
            # fails, the active rule safely retries next sweep instead of losing its event.
            if updated_alerts != alerts:
                self._save(updated_alerts)
        return triggered

    def _load(self) -> list[PriceAlert]:
        payload = read_json(self._path, {"alerts": []})
        rows = payload.get("alerts") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("market alert store must contain an alerts list")
        return [PriceAlert.from_json(row) for row in rows if isinstance(row, dict)]

    def _save(self, alerts: list[PriceAlert]) -> None:
        write_json_atomic(self._path, {"alerts": [asdict(alert) for alert in alerts]})


def evaluate_price_alerts(runtime, pulse_store=None) -> list[PriceAlert]:
    """Evaluate armed symbols from the canonical split-adjusted daily cache."""
    store = resolve_price_alert_store(runtime)
    active = store.list(status="active")
    prices: dict[str, float] = {}
    close_times: dict[str, datetime] = {}
    for symbol in {alert.symbol for alert in active}:
        try:
            # A chart alert may target a ticker outside the dashboard scan universe. Refresh
            # every explicitly armed symbol, while the short freshness window avoids a second
            # vendor request when the full market sweep just refreshed it moments earlier.
            history = runtime.prices.refresh(symbol, max_age_seconds=60)
            if history is None:
                continue
            fetched_at = datetime.fromisoformat(history.updated_at)
            if fetched_at.tzinfo is None:
                continue  # unknown provenance cannot establish a finalized candle
            available_at = min(datetime.now(timezone.utc), fetched_at)
            # A pre-close cache stays provisional even after the wall clock passes 16:00.
            completed = [bar for bar in history.bars if daily_close_available_at(bar) <= available_at]
        except Exception:
            logging.warning("market alerts: %s daily close unavailable", symbol, exc_info=True)
            continue
        if completed:
            latest = max(completed, key=lambda bar: bar.t)
            if math.isfinite(latest.c) and latest.c > 0:
                prices[symbol] = float(latest.c)
                close_times[symbol] = daily_close_available_at(latest)
    triggered = store.evaluate(prices, close_times=close_times)
    if pulse_store is not None:
        for alert in triggered:
            _publish_pulse(pulse_store, alert)
    return triggered


def resolve_price_alert_store(runtime) -> PriceAlertStore:
    """One read-modify-write lock per MarketRuntime, shared by RPC and scheduler lanes."""
    store = getattr(runtime, "_price_alert_store", None)
    if isinstance(store, PriceAlertStore):
        return store
    store = PriceAlertStore(runtime.store.root_dir)
    setattr(runtime, "_price_alert_store", store)
    return store


def _publish_pulse(pulse_store, alert: PriceAlert) -> None:
    relation = "above" if alert.direction == "above" else "below"
    now = _now_iso()
    record = PulseRecord(
        pulse_id=f"market-{alert.alert_id}",
        status="new",
        title=f"{alert.symbol} crossed {relation} ${alert.threshold:,.2f}",
        summary=f"Daily close ${alert.trigger_price:,.2f} triggered your one-shot price alert.",
        why_now="The deterministic daily-close rule crossed its armed price level during the latest market sweep.",
        source_session_keys=["market-sentinel"],
        source_run_ids=[],
        created_at=now,
        updated_at=now,
    )
    if pulse_store.get(record.pulse_id) is None:
        pulse_store.create(record)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
