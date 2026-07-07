"""Read-only Webull portfolio sync: accounts → balance + positions → sanitized snapshot.

Only three SDK calls are used, all reads: account_v2.get_account_list / get_account_balance /
get_account_position. Vendor payload keys vary, so extraction is tolerant (multiple spellings) and
ONLY whitelisted fields survive into the snapshot — everything else is dropped at this boundary.
Prices are enriched via yfinance (Webull market data is a separate paid subscription).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import mask_account_id, webull_data_dir

logger = logging.getLogger(__name__)


@dataclass
class WebullPosition:
    symbol: str
    quantity: float
    avg_cost: float | None = None
    last_price: float | None = None
    prev_close: float | None = None
    market_value: float | None = None
    unrealized_pl: float | None = None
    unrealized_pl_pct: float | None = None
    day_change_pct: float | None = None
    allocation_pct: float | None = None
    asset_type: str | None = None
    price_source: str = "webull"
    warnings: list[str] = field(default_factory=list)


@dataclass
class WebullSnapshot:
    account_id_masked: str
    synced_at: str
    total_equity: float | None
    cash: float | None
    buying_power: float | None
    currency: str | None
    positions: list[WebullPosition]
    account_source: str = "webull"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _snapshot_file() -> Path:
    return webull_data_dir() / "portfolio.json"


def save_snapshot(snapshot: WebullSnapshot) -> None:
    _snapshot_file().write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")


def load_snapshot() -> dict[str, Any] | None:
    path = _snapshot_file()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and payload.get("positions") is not None else None


def _pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _rows(payload: Any) -> list[dict[str, Any]]:
    """Vendor responses arrive as a list, or wrapped under data/list/positions/items."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "list", "positions", "items", "accounts"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [row for row in inner if isinstance(row, dict)]
        return [payload]
    return []


def list_accounts(trade_client) -> list[dict[str, Any]]:
    response = trade_client.account_v2.get_account_list()
    rows = _rows(response.json())
    accounts: list[dict[str, Any]] = []
    for row in rows:
        account_id = _pick(row, "account_id", "accountId", "sec_account_id", "secAccountId")
        if account_id is None:
            continue
        accounts.append(
            {
                "accountId": str(account_id),
                "accountIdMasked": mask_account_id(str(account_id)),
                "accountType": str(_pick(row, "account_type", "accountType", "register_type") or ""),
                "brokerName": str(_pick(row, "broker_name", "brokerName") or ""),
                "currency": str(_pick(row, "currency") or ""),
            }
        )
    logger.info("Webull account discovery: %d account(s)", len(accounts))
    return accounts


def normalize_positions(payload: Any) -> tuple[list[WebullPosition], list[str]]:
    positions: list[WebullPosition] = []
    warnings: list[str] = []
    for row in _rows(payload):
        # position rows sometimes nest the instrument
        instrument = row.get("instrument") if isinstance(row.get("instrument"), dict) else {}
        symbol = _pick(row, "symbol", "ticker", "disSymbol") or _pick(instrument, "symbol", "ticker")
        quantity = _num(_pick(row, "quantity", "qty", "position", "total_quantity", "totalQuantity"))
        if not symbol or quantity is None:
            warnings.append("skipped a position row with no symbol/quantity")
            continue
        # Webull returns the P&L *rate* as a decimal fraction (0.205 == +20.5%) — verified against a
        # live account on 2026-07-01. Convert to percent here so every downstream consumer sees %.
        pl_rate = _num(_pick(row, "unrealized_profit_loss_rate", "unrealizedProfitLossRate"))
        position = WebullPosition(
            symbol=str(symbol).upper(),
            quantity=quantity,
            avg_cost=_num(_pick(row, "cost_price", "costPrice", "avg_cost", "avgCost", "average_cost", "unit_cost")),
            last_price=_num(_pick(row, "last_price", "lastPrice", "market_price", "price")),
            market_value=_num(_pick(row, "market_value", "marketValue")),
            unrealized_pl=_num(_pick(row, "unrealized_profit_loss", "unrealizedProfitLoss", "unrealized_pl", "unrealizedProfitLossBase")),
            unrealized_pl_pct=round(pl_rate * 100, 2) if pl_rate is not None else None,
            asset_type=(str(_pick(row, "instrument_type", "instrumentType", "asset_type", "security_type") or "") or None),
        )
        if position.avg_cost is None:
            position.warnings.append("avg cost unavailable from Webull")
        positions.append(position)
    return positions, warnings


def normalize_balance(payload: Any) -> dict[str, Any]:
    """Live payload shape (verified 2026-07-01): top level carries total_* fields, per-currency
    detail (cash, buying power) nests under account_currency_assets[0]."""
    rows = _rows(payload)
    row = rows[0] if rows else {}
    assets = row.get("account_currency_assets")
    detail = assets[0] if isinstance(assets, list) and assets and isinstance(assets[0], dict) else {}
    return {
        "total_equity": _num(
            _pick(row, "total_net_liquidation_value", "net_liquidation_value", "netLiquidationValue", "total_asset", "totalAsset", "account_value", "total_market_value")
        ),
        "cash": _num(_pick(row, "total_cash_balance", "cash_balance", "cashBalance", "cash") or _pick(detail, "cash_balance", "settled_cash")),
        "buying_power": _num(_pick(row, "buying_power", "buyingPower") or _pick(detail, "buying_power", "day_buying_power")),
        "currency": (str(_pick(row, "total_asset_currency", "currency") or _pick(detail, "currency") or "") or None),
    }


def enrich_with_yfinance(positions: list[WebullPosition]) -> None:
    """Fill price gaps from yfinance daily bars; label the source. Webull values win when present."""
    from ..data_sources import fetch_ohlcv

    for position in positions:
        try:
            frame = fetch_ohlcv(position.symbol, interval="1d", period="5d", auto_adjust=True)
        except Exception:
            frame = None
        if frame is None or frame.empty:
            if position.last_price is None:
                position.warnings.append("no price available (webull + yfinance both missing)")
            continue
        closes = frame["close"].dropna()
        yf_last = float(closes.iloc[-1]) if len(closes) else None
        yf_prev = float(closes.iloc[-2]) if len(closes) > 1 else None
        if position.last_price is None and yf_last is not None:
            position.last_price = yf_last
            position.price_source = "yfinance"
        if position.prev_close is None and yf_prev is not None:
            position.prev_close = yf_prev
        if position.day_change_pct is None and position.last_price is not None and yf_prev:
            position.day_change_pct = round((position.last_price / yf_prev - 1) * 100, 2)


def finalize(positions: list[WebullPosition], total_equity: float | None) -> None:
    """Derive market value / P&L / allocation from whatever facts exist."""
    for position in positions:
        if position.market_value is None and position.last_price is not None:
            position.market_value = round(position.quantity * position.last_price, 2)
        if position.unrealized_pl is None and position.avg_cost and position.last_price is not None:
            position.unrealized_pl = round((position.last_price - position.avg_cost) * position.quantity, 2)
        if position.unrealized_pl_pct is None and position.avg_cost and position.last_price is not None:
            position.unrealized_pl_pct = round((position.last_price / position.avg_cost - 1) * 100, 2)
    market_total = sum(p.market_value for p in positions if p.market_value is not None)
    basis_total = total_equity if total_equity else market_total
    if basis_total:
        for position in positions:
            if position.market_value is not None:
                position.allocation_pct = round(position.market_value / basis_total * 100, 2)


def fetch_snapshot(trade_client, account_id: str) -> WebullSnapshot:
    """The read-only sync: balance + positions → normalized, enriched, sanitized snapshot."""
    balance_raw = trade_client.account_v2.get_account_balance(account_id).json()
    positions_raw = trade_client.account_v2.get_account_position(account_id).json()
    balance = normalize_balance(balance_raw)
    positions, warnings = normalize_positions(positions_raw)
    enrich_with_yfinance(positions)
    finalize(positions, balance.get("total_equity"))
    snapshot = WebullSnapshot(
        account_id_masked=mask_account_id(account_id),
        synced_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        total_equity=balance.get("total_equity"),
        cash=balance.get("cash"),
        buying_power=balance.get("buying_power"),
        currency=balance.get("currency"),
        positions=positions,
        warnings=warnings,
    )
    logger.info("Fetched %d Webull position(s); %d warning(s)", len(positions), len(warnings))
    save_snapshot(snapshot)
    return snapshot
