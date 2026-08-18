"""Market price-alert RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.core.market.alerts import PriceAlertStore, resolve_price_alert_store
from copenet.core.market.runtime import resolve_market_runtime
from copenet.host.rpc_schema import ResponseFrame, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_market_alerts_list(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    store = _store(orchestrator)
    alerts = store.list(symbol=_optional_text(raw.get("symbol")), status="active")
    await _send(request_id, send_json, alerts)


async def handle_market_alerts_create(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    store = _store(orchestrator)
    alert = store.create(
        symbol=str(raw.get("symbol") or ""),
        direction=str(raw.get("direction") or ""),
        threshold=float(raw.get("threshold") or 0),
        reference_price=float(raw.get("referencePrice") or 0),
    )
    await _send(request_id, send_json, store.list(symbol=alert.symbol, status="active"))


async def handle_market_alerts_cancel(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    alert_id = str(raw.get("alertId") or "").strip()
    if not alert_id:
        raise ValueError("alertId is required")
    _store(orchestrator).cancel(alert_id)
    alerts = _store(orchestrator).list(symbol=_optional_text(raw.get("symbol")), status="active")
    await _send(request_id, send_json, alerts)


def _store(orchestrator) -> PriceAlertStore:
    return resolve_price_alert_store(resolve_market_runtime(orchestrator))


async def _send(request_id: str, send_json: SendJson, alerts) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(id=request_id, ok=True, payload={"alerts": [alert.to_wire() for alert in alerts]})
        )
    )


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
