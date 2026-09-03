"""Explicit operator Market notification actions; never triggers market acquisition."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any, Awaitable, Callable

from copenet.core.market.alerts import delivery_rule_active
from copenet.core.market.runtime import resolve_market_runtime
from copenet.core.messaging.market_delivery import (
    enqueue_market_test, market_delivery_action, market_notifications_state,
    process_market_deliveries,
)
from copenet.host.rpc_schema import ResponseFrame, make_response_frame

SendJson = Callable[[dict[str, Any]], Awaitable[None]]


def _root(orchestrator):
    return resolve_market_runtime(orchestrator).store.root_dir


def _required_text(params: dict, key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f"{key} is required")
    return value.strip()


async def _send_state(request_id: str, send_json: SendJson, orchestrator) -> None:
    payload = await asyncio.to_thread(market_notifications_state, _root(orchestrator), orchestrator._messaging_store.load)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


async def handle_market_notifications_get(request_id: str, params: dict | None, send_json: SendJson, orchestrator) -> None:
    await _send_state(request_id, send_json, orchestrator)


async def handle_market_notifications_test(request_id: str, params: dict | None, send_json: SendJson, orchestrator) -> None:
    destination_id = _required_text(params or {}, "destinationId")
    config = orchestrator._messaging_store.load()
    if not any(item.id == destination_id and item.platform == "telegram" for item in config.destinations):
        raise ValueError("Choose an existing Telegram destination")
    root = _root(orchestrator)
    row = await asyncio.to_thread(enqueue_market_test, root, destination_id)
    await asyncio.to_thread(
        process_market_deliveries, root, orchestrator._messaging_store.load,
        partial(delivery_rule_active, root), only_delivery_id=row["id"],
    )
    await _send_state(request_id, send_json, orchestrator)


async def handle_market_notifications_action(request_id: str, params: dict | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    delivery_id = _required_text(raw, "deliveryId")
    action = _required_text(raw, "action")
    acknowledge = raw.get("acknowledgeDuplicateRisk", False)
    if type(acknowledge) is not bool:
        raise ValueError("acknowledgeDuplicateRisk must be a boolean")
    root = _root(orchestrator)
    await asyncio.to_thread(market_delivery_action, root, delivery_id, action, acknowledge_duplicate_risk=acknowledge)
    if action != "cancel":
        await asyncio.to_thread(
            process_market_deliveries, root, orchestrator._messaging_store.load,
            partial(delivery_rule_active, root), only_delivery_id=delivery_id,
        )
    await _send_state(request_id, send_json, orchestrator)
