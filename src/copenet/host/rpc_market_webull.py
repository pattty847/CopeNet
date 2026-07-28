"""Webull broker RPC handlers — auth, account selection, portfolio sync, fill history, P&L,
and watchlist import. Read-only: no handler in this module places, modifies, or cancels an order.

Extracted from rpc_market.py (which was past the module size threshold) when the fill-history
and watchlist lanes landed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from copenet.core.market.runtime import resolve_market_runtime
from copenet.host.rpc_schema import ResponseFrame, make_response_frame

logger = logging.getLogger(__name__)

SendJson = Callable[[dict[str, Any]], Awaitable[None]]

# Background lanes (auth approval polling, portfolio sync) can't answer inline, so their failures
# used to vanish into a discarded task. Keep the last one per lane and report it in status.
_LAST_ERRORS: dict[str, str] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _config():
    from copenet.core.market.webull.config import load_webull_config

    config = load_webull_config()
    if config is None:
        raise ValueError("Webull is not configured — set WEBULL_KEY and WEBULL_SECRET in .env")
    return config


def _account_id() -> str:
    from copenet.core.market.webull.client import selected_account

    account = selected_account()
    if account is None:
        raise ValueError("No Webull account selected — call market.webull.accounts then market.webull.account.select")
    return account["accountId"]


def _track_background(orchestrator, lane: str, coro) -> None:
    """Run a background lane, recording any failure so market.webull.status can surface it."""

    async def _guarded() -> None:
        try:
            await coro
            _LAST_ERRORS.pop(lane, None)
        except Exception as exc:  # noqa: BLE001 — the operator needs the reason, not a stack trace
            _LAST_ERRORS[lane] = f"{type(exc).__name__}: {exc}"
            logger.exception("Webull %s lane failed", lane)

    task = asyncio.create_task(_guarded())
    background_tasks = getattr(orchestrator, "_background_tasks", None)
    if isinstance(background_tasks, set):
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)


async def handle_market_webull_status(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params, orchestrator
    from copenet.core.market.webull.client import auth_status, selected_account
    from copenet.core.market.webull.config import include_portfolio_context_enabled, load_webull_config
    from copenet.core.market.webull.orders import load_fills
    from copenet.core.market.webull.sync import load_snapshot

    config = load_webull_config()
    snapshot = load_snapshot()
    orders = load_fills()
    account = selected_account()
    payload = {
        "configured": config is not None,
        "env": config.env if config else None,
        "auth": auth_status(),
        "account": {"accountId": account["accountId"], "nickname": account.get("nickname", "")} if account else None,
        "lastSync": snapshot.get("synced_at") if snapshot else None,
        "positionCount": len(snapshot.get("positions", [])) if snapshot else 0,
        "portfolioContextEnabled": include_portfolio_context_enabled(),
        "ordersSyncedAt": orders.get("synced_at") if orders else None,
        "fillCount": len(orders.get("fills", [])) if orders else 0,
        "lastErrors": dict(_LAST_ERRORS),
    }
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


async def handle_market_webull_auth(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """Kick the auth flow in the background. First-time auth requires the operator to APPROVE the
    request in their Webull mobile app while the SDK polls (up to ~5 minutes)."""
    del params
    from copenet.core.market.webull.client import build_trade_client, reset_clients

    config = _config()
    reset_clients()  # a fresh approval must not reuse a half-authorized cached client
    _track_background(orchestrator, "auth", asyncio.to_thread(build_trade_client, config))
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"startedAt": _now_iso(), "instruction": "Open the Webull app on your phone and approve the API access request."},
            )
        )
    )


async def handle_market_webull_accounts(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params, orchestrator
    from copenet.core.market.webull.client import trade_client
    from copenet.core.market.webull.sync import list_accounts

    config = _config()
    accounts = await asyncio.to_thread(lambda: list_accounts(trade_client(config)))
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"accounts": accounts})))


async def handle_market_webull_account_select(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del orchestrator
    from copenet.core.market.webull.client import select_account

    raw = params or {}
    account_id = str(raw.get("accountId") or "").strip()
    if not account_id:
        raise ValueError("accountId is required")
    payload = select_account(account_id, nickname=str(raw.get("nickname") or ""))
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


async def handle_market_webull_sync(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params
    from copenet.core.market.webull.client import trade_client
    from copenet.core.market.webull.sync import fetch_snapshot

    config = _config()
    account_id = _account_id()
    runtime = resolve_market_runtime(orchestrator)

    def _sync_then_refresh() -> None:
        fetch_snapshot(trade_client(config), account_id)
        runtime.refresh(scope="signals")  # rebuild the dashboard so the portfolio panel reflects the broker

    _track_background(orchestrator, "portfolio-sync", asyncio.to_thread(_sync_then_refresh))
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"startedAt": _now_iso()})))


async def handle_market_webull_orders_sync(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """Pull every fill back to account open, then answer with the rebuilt all-time ledger.

    Runs inline (in a thread) rather than as a background task: the walk is a handful of paginated
    requests, and the operator asked a question that deserves an answer in the same round trip."""
    del orchestrator
    from copenet.core.market.webull.client import trade_client
    from copenet.core.market.webull.orders import HISTORY_START_DATE, sync_fills
    from copenet.core.market.webull.pnl import build_ledger
    from copenet.core.market.webull.sync import load_snapshot

    raw = params or {}
    start_date = str(raw.get("startDate") or "").strip() or HISTORY_START_DATE
    config = _config()
    account_id = _account_id()

    orders = await asyncio.to_thread(lambda: sync_fills(trade_client(config), account_id, start_date=start_date))
    ledger = build_ledger(orders, load_snapshot())
    payload = {"ledger": ledger.to_wire() if ledger else None, "syncedAt": orders.get("synced_at")}
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


async def handle_market_webull_pnl_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """The stored ledger — no network. Null until the first orders sync."""
    del params, orchestrator
    from copenet.core.market.webull.orders import load_fills
    from copenet.core.market.webull.pnl import build_ledger
    from copenet.core.market.webull.sync import load_snapshot

    ledger = build_ledger(load_fills(), load_snapshot())
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"ledger": ledger.to_wire() if ledger else None})))


async def handle_market_webull_watchlists_import(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """Re-pull the operator's Webull lists into the CopeNet watchlist store (replace by name)."""
    del params
    from copenet.core.market.webull.client import data_client
    from copenet.core.market.webull.watchlists import fetch_watchlists, import_into_store
    from copenet.host.rpc_market_watchlist import watchlist_store

    config = _config()
    store = watchlist_store(orchestrator)
    lists = await asyncio.to_thread(lambda: fetch_watchlists(data_client(config)))
    result = await asyncio.to_thread(import_into_store, store, lists)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={**result, "state": store.state()})))
