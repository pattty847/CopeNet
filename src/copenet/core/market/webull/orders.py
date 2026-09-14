"""Read-only Webull fill history — every executed order back to account open.

The SDK 3.0.0 cursor protocol returns {data, pagination_key}. We consume every page and
fail closed on a malformed page or a stalled cursor so a partial sync never replaces history.
Each record is the aggregate executed quantity/average price for an order, not an execution tape.

Only whitelisted fields survive into `Fill`; everything else is dropped at this boundary, the same
sanitization discipline `sync.py` uses for positions.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import account_fingerprint, mask_account_id, webull_data_dir

logger = logging.getLogger(__name__)

# Webull US predates any CopeNet account; a fixed floor keeps the walk deterministic.
HISTORY_START_DATE = "2018-05-21"
_PAGE_PAUSE_SECONDS = 1.5
_MAX_PAGES = 1000  # Vendor controls page size; never silently truncate at this backstop.
_MAX_RETRIES = 4
_RETRY_BASE_SECONDS = 5.0
OPTION_CONTRACT_MULTIPLIER = 100.0


@dataclass
class Fill:
    """One executed order leg. `contract_key` is the P&L identity: the symbol for equities, the
    full contract for options (two different strikes are two different instruments)."""

    order_id: str
    symbol: str
    contract_key: str
    side: str
    instrument_type: str
    quantity: float
    price: float | None
    multiplier: float
    filled_at: str
    order_type: str
    price_source: str = "fill"  # fill | limit (estimated)
    option_type: str | None = None
    option_expire_date: str | None = None
    strike_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _orders_file() -> Path:
    return webull_data_dir() / "orders.json"


def save_fills(payload: dict[str, Any]) -> None:
    _orders_file().write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_fills() -> dict[str, Any] | None:
    path = _orders_file()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and isinstance(payload.get("fills"), list) else None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(str(value).replace(",", ""))
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _contract_identity(leg: dict[str, Any], symbol: str) -> tuple[str, dict[str, Any]]:
    """Option legs nest under `legs[0]`. Returns (contract_key, option field dict)."""
    option_type = str(leg.get("option_type") or "") or None
    expire = str(leg.get("option_expire_date") or "") or None
    strike = _num(leg.get("strike_price"))
    if not option_type or not expire or strike is None:
        return symbol, {}
    key = f"{symbol} {expire} {strike:g}{option_type[:1].upper()}"
    return key, {"option_type": option_type, "option_expire_date": expire, "strike_price": strike}


def normalize_fills(combos: list[dict[str, Any]]) -> tuple[list[Fill], list[str]]:
    """Flatten combo envelopes into executed legs, oldest-first."""
    fills: list[Fill] = []
    warnings: list[str] = []
    seen_orders: set[str] = set()
    for combo in combos:
        if not isinstance(combo, dict):
            continue
        for order in combo.get("orders") or []:
            if not isinstance(order, dict):
                continue
            order_id = str(order.get("order_id") or order.get("client_order_id") or "")
            if order_id in seen_orders:
                continue
            if not order_id:
                warnings.append("skipped an order with no identity")
                continue
            seen_orders.add(order_id)
            symbol = str(order.get("symbol") or "").upper()
            quantity = _num(order.get("filled_quantity"))
            if quantity is None or quantity <= 0:
                if order.get("status") in {"FILLED", "PARTIAL_FILLED"}:
                    warnings.append("skipped an executed order with invalid quantity")
                continue
            if not symbol or not order.get("filled_time_at"):
                warnings.append("skipped an executed order with no symbol/execution time")
                continue
            instrument_type = str(order.get("instrument_type") or "").upper()
            if instrument_type not in {"EQUITY", "OPTION"}:
                warnings.append("skipped an unsupported executed instrument type")
                continue
            is_option = str(order.get("instrument_type") or "").upper() == "OPTION"
            legs = order.get("legs") or []
            leg = legs[0] if legs and isinstance(legs[0], dict) else {}
            if is_option and len(legs) != 1:
                warnings.append("skipped a multi-leg option order: per-leg execution prices unavailable")
                continue
            contract_key, option_fields = _contract_identity(leg, symbol) if is_option else (symbol, {})
            if is_option and not option_fields:
                warnings.append("skipped an option order with incomplete contract identity")
                continue
            # 2020-era option fills come back with no filled_price. Every one is a LIMIT order, and
            # a limit order fills at its limit or better, so the limit is a usable estimate — it can
            # only understate the result, never flatter it. Flagged so the estimate stays visible.
            price = _num(order.get("filled_price"))
            price_source = "fill"
            if price is None:
                price = _num(order.get("limit_price"))
                price_source = "limit" if price is not None else "fill"
            fills.append(
                Fill(
                    order_id=str(order.get("order_id") or order.get("client_order_id") or ""),
                    symbol=symbol,
                    contract_key=contract_key,
                    side=str(order.get("side") or "").upper(),
                    instrument_type="OPTION" if is_option else "EQUITY",
                    quantity=quantity,
                    price=price,
                    price_source=price_source,
                    multiplier=OPTION_CONTRACT_MULTIPLIER if is_option else 1.0,
                    filled_at=str(order["filled_time_at"]),
                    order_type=str(order.get("order_type") or ""),
                    **option_fields,
                )
            )
    fills.sort(key=lambda f: f.filled_at)
    return fills, warnings


def _get_page_with_backoff(trade_client, account_id: str, kwargs: dict[str, Any]) -> Any:
    """The endpoint 429s when a sync follows close behind another call. A partial history would
    silently distort P&L, so back off and retry rather than return half the account."""
    delay = _RETRY_BASE_SECONDS
    for attempt in range(_MAX_RETRIES):
        try:
            return trade_client.order_v3.list_order_history(account_id, **kwargs).json()
        except Exception as exc:  # noqa: BLE001 — the SDK raises a vendor ServerException
            if "TOO_MANY_REQUESTS" not in str(exc) or attempt == _MAX_RETRIES - 1:
                raise
            logger.info("Webull order history rate-limited; retrying in %ss", delay)
            time.sleep(delay)
            delay *= 2
    return []


def fetch_order_history(trade_client, account_id: str, *, start_date: str = HISTORY_START_DATE) -> list[dict[str, Any]]:
    """Walk every history page back to `start_date`. Newest-first from the API; raw combos out."""
    start_time = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if start_date < HISTORY_START_DATE:
        raise ValueError(f"Webull history starts at {HISTORY_START_DATE}")
    end_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    combos: list[dict[str, Any]] = []
    cursors: set[str] = set()
    cursor: str | None = None

    for page in range(_MAX_PAGES):
        if page:
            time.sleep(_PAGE_PAUSE_SECONDS)
        kwargs: dict[str, Any] = {
            "start_time": start_time.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "end_time": end_time,
        }
        if cursor:
            kwargs["pagination_key"] = cursor
        payload = _get_page_with_backoff(trade_client, account_id, kwargs)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("Webull history returned an invalid page; previous history retained")
        rows = payload["data"]
        if any(not isinstance(row, dict) or not isinstance(row.get("orders"), list) for row in rows):
            raise ValueError("Webull history returned invalid orders; previous history retained")
        combos.extend(rows)
        cursor = payload.get("pagination_key")
        if cursor is None or cursor == "":
            break
        if not isinstance(cursor, str) or cursor in cursors:
            raise ValueError("Webull history cursor stalled; previous history retained")
        cursors.add(cursor)
    else:
        raise ValueError("Webull history exceeded the page limit; previous history retained")

    logger.info("Fetched %d Webull order(s) since %s", len(combos), start_date)
    return combos


def fetch_split_history(symbols: list[str]) -> tuple[dict[str, list[list[Any]]], list[str]]:
    """Corporate actions for every traded equity — the fills alone cannot reconstruct share counts.

    Stored with the fills (not re-fetched at read time) so P&L stays a pure function of the sync.
    Delisted tickers return nothing from Yahoo; those symbols are named, not silently assumed
    split-free, because an unknown split is exactly what corrupts a replay."""
    from ..data_sources import fetch_splits

    splits: dict[str, list[list[Any]]] = {}
    unavailable: list[str] = []
    for symbol in sorted(set(symbols)):
        rows = fetch_splits(symbol)
        if rows:
            splits[symbol] = [[date, ratio] for date, ratio in rows]
        elif not _resolvable(symbol):
            unavailable.append(symbol)
    return splits, unavailable


def _resolvable(symbol: str) -> bool:
    """True when Yahoo still serves the ticker (so an empty split list means 'no splits', not
    'no data'). Delisted names are the ones we cannot vouch for."""
    from ..data_sources import fetch_ohlcv

    try:
        frame = fetch_ohlcv(symbol, interval="1d", period="5d", auto_adjust=True)
    except Exception:
        return False
    return frame is not None and not frame.empty


def sync_fills(trade_client, account_id: str, *, start_date: str = HISTORY_START_DATE) -> dict[str, Any]:
    """Fetch → normalize → persist. Returns the stored payload."""
    combos = fetch_order_history(trade_client, account_id, start_date=start_date)
    fills, warnings = normalize_fills(combos)
    equities = [fill.symbol for fill in fills if fill.instrument_type == "EQUITY"]
    splits, unavailable = fetch_split_history(equities)
    payload = {
        "account_id_masked": mask_account_id(account_id),
        "account_fingerprint": account_fingerprint(account_id),
        "synced_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "history_start": start_date,
        "order_count": len(combos),
        "fills": [fill.to_dict() for fill in fills],
        "splits": splits,
        "split_data_unavailable": unavailable,
        "warnings": warnings,
    }
    save_fills(payload)
    logger.info("Stored %d Webull fill(s); %d warning(s)", len(fills), len(warnings))
    return payload
