"""Market Monitor RPC handlers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

from copenet.core.market import MarketRuntime, MarketStore
from copenet.core.market.runtime import default_market_dir
from copenet.host.rpc_schema import ResponseFrame, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_market_dashboard_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params
    runtime = _runtime(orchestrator)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=runtime.dashboard().to_wire())))


async def handle_market_ticker_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    symbol = str(raw.get("symbol") or "").strip()
    if not symbol:
        raise ValueError("symbol is required")
    runtime = _runtime(orchestrator)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=runtime.ticker(symbol).to_wire())))


async def handle_market_universe_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params
    runtime = _runtime(orchestrator)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=runtime.universe())))


async def handle_market_refresh(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    scope = str(raw.get("scope") or "all").strip() or "all"
    if scope not in {"all", "macro", "signals", "edgar"}:
        raise ValueError("scope must be one of: all, macro, signals, edgar")
    runtime = _runtime(orchestrator)
    started_at = _now_iso()
    run_id = f"market-refresh-{uuid4().hex[:12]}"
    provider = _interpret_provider(orchestrator)

    async def _refresh_then_interpret() -> None:
        await asyncio.to_thread(runtime.refresh, scope=scope)
        # Default lane: one automatic whole-market model read per refresh (operator design).
        if provider is not None and scope in {"all", "signals"}:
            try:
                await runtime.interpret(provider, target="market")
            except Exception:
                pass  # the deterministic briefing still stands; the read stays stale

    _track_task(orchestrator, asyncio.create_task(_refresh_then_interpret()))
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"startedAt": started_at, "runId": run_id})))


async def handle_market_interpret(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    target = str(raw.get("target") or "market").strip() or "market"
    runtime = _runtime(orchestrator)
    provider = _interpret_provider(orchestrator)
    if provider is None:
        raise ValueError("openai-codex provider unavailable — model reads need it configured")
    started_at = _now_iso()
    run_id = f"market-interpret-{uuid4().hex[:12]}"
    _track_task(orchestrator, asyncio.create_task(runtime.interpret(provider, target=target)))
    await send_json(
        make_response_frame(
            ResponseFrame(id=request_id, ok=True, payload={"startedAt": started_at, "runId": run_id, "target": target})
        )
    )


async def handle_market_read_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    target = str(raw.get("target") or "market").strip() or "market"
    runtime = _runtime(orchestrator)
    read = runtime.store.load_market_read() if target == "market" else runtime.store.load_ticker_read(target)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"target": target, "read": read})))


async def handle_market_webull_status(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params, orchestrator
    from copenet.core.market.webull.client import auth_status, selected_account
    from copenet.core.market.webull.config import include_portfolio_context_enabled, load_webull_config
    from copenet.core.market.webull.sync import load_snapshot

    config = load_webull_config()
    snapshot = load_snapshot()
    account = selected_account()
    payload = {
        "configured": config is not None,
        "env": config.env if config else None,
        "auth": auth_status(),
        "account": {"accountId": account["accountId"], "nickname": account.get("nickname", "")} if account else None,
        "lastSync": snapshot.get("synced_at") if snapshot else None,
        "positionCount": len(snapshot.get("positions", [])) if snapshot else 0,
        "portfolioContextEnabled": include_portfolio_context_enabled(),
    }
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


async def handle_market_webull_auth(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """Kick the auth flow in the background. First-time auth requires the operator to APPROVE the
    request in their Webull mobile app while the SDK polls (up to ~5 minutes)."""
    del params
    from copenet.core.market.webull.client import build_trade_client
    from copenet.core.market.webull.config import load_webull_config

    config = load_webull_config()
    if config is None:
        raise ValueError("Webull is not configured — set WEBULL_KEY and WEBULL_SECRET in .env")
    _track_task(orchestrator, asyncio.create_task(asyncio.to_thread(build_trade_client, config)))
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
    from copenet.core.market.webull.client import build_trade_client
    from copenet.core.market.webull.config import load_webull_config
    from copenet.core.market.webull.sync import list_accounts

    config = load_webull_config()
    if config is None:
        raise ValueError("Webull is not configured — set WEBULL_KEY and WEBULL_SECRET in .env")
    accounts = await asyncio.to_thread(lambda: list_accounts(build_trade_client(config)))
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
    from copenet.core.market.webull.client import build_trade_client, selected_account
    from copenet.core.market.webull.config import load_webull_config
    from copenet.core.market.webull.sync import fetch_snapshot

    config = load_webull_config()
    if config is None:
        raise ValueError("Webull is not configured — set WEBULL_KEY and WEBULL_SECRET in .env")
    account = selected_account()
    if account is None:
        raise ValueError("No Webull account selected — call market.webull.accounts then market.webull.account.select")
    runtime = _runtime(orchestrator)

    def _sync_then_refresh() -> None:
        fetch_snapshot(build_trade_client(config), account["accountId"])
        runtime.refresh(scope="signals")  # rebuild the dashboard so the portfolio panel reflects the broker

    _track_task(orchestrator, asyncio.create_task(asyncio.to_thread(_sync_then_refresh)))
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"startedAt": _now_iso()})))


def _interpret_provider(orchestrator):
    providers = getattr(orchestrator, "_providers", None)
    if isinstance(providers, dict):
        return providers.get("openai-codex")
    return None


def _track_task(orchestrator, task: asyncio.Task) -> None:
    background_tasks = getattr(orchestrator, "_background_tasks", None)
    if isinstance(background_tasks, set):
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)


def _runtime(orchestrator) -> MarketRuntime:
    runtime = getattr(orchestrator, "_market_runtime", None)
    if isinstance(runtime, MarketRuntime):
        return runtime
    store = getattr(orchestrator, "market_store", None)
    if not isinstance(store, MarketStore):
        store = MarketStore(default_market_dir())
    runtime = MarketRuntime(store=store)
    try:
        setattr(orchestrator, "_market_runtime", runtime)
    except Exception:
        pass
    return runtime


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
