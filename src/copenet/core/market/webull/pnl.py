"""All-time profit and loss, replayed FIFO from the Webull fill history.

The question this answers: *is the account green since it opened?* Two halves —

- **realized**: FIFO-matched round trips from `orders.py` fills (options at 100x)
- **unrealized**: taken from the live position snapshot (`sync.py`), where Webull's own avg cost
  is authoritative

What this CANNOT see, and therefore reports as caveats rather than silently absorbing:

- dividends and interest — the open API exposes no cash-transaction endpoint
- fees and commissions — every fill returns `fees: []` and `commission: {}`
- share counts changed by corporate actions (splits, delistings, transfers) never appear as an
  order, so a replayed open quantity can drift from the broker's. `reconcile()` surfaces every
  such drift instead of hiding it, and the snapshot always wins for what is held *now*.
- long option lots that were never sold are assumed expired worthless (broken out separately as
  `expired_option_pl`, never folded silently into the round-trip total)
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ..models import _to_wire

_UNREALIZED_SOURCE = "webull snapshot"


@dataclass
class RealizedTrade:
    """One FIFO-matched round trip: a closing fill against one opening lot."""

    contract_key: str
    symbol: str
    instrument_type: str
    direction: str  # long | short
    quantity: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float | None
    opened_at: str
    closed_at: str
    holding_days: int | None


@dataclass
class OpenLot:
    contract_key: str
    symbol: str
    instrument_type: str
    quantity: float  # signed: positive long, negative short
    price: float
    opened_at: str


@dataclass
class SymbolPnl:
    symbol: str
    realized_pnl: float
    unrealized_pnl: float | None
    total_pnl: float
    trade_count: int
    win_count: int


@dataclass
class PositionReconciliation:
    symbol: str
    replayed_quantity: float
    broker_quantity: float | None
    note: str


@dataclass
class TradeLedger:
    synced_at: str
    history_start: str
    fill_count: int
    realized_pnl: float
    expired_option_pl: float
    unrealized_pnl: float | None
    all_time_pnl: float
    trade_count: int
    win_count: int
    win_rate_pct: float | None
    best_trade: RealizedTrade | None
    worst_trade: RealizedTrade | None
    first_fill_at: str | None
    last_fill_at: str | None
    by_symbol: list[SymbolPnl] = field(default_factory=list)
    trades: list[RealizedTrade] = field(default_factory=list)
    open_lots: list[OpenLot] = field(default_factory=list)
    reconciliation: list[PositionReconciliation] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_wire(self) -> dict[str, Any]:
        return _to_wire(self)


def _holding_days(opened_at: str, closed_at: str) -> int | None:
    try:
        start = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max((end - start).days, 0)


def _expired(fill: dict[str, Any], today: date) -> bool:
    expire = fill.get("option_expire_date")
    if not expire:
        return False
    try:
        return date.fromisoformat(str(expire)) < today
    except ValueError:
        return False


def replay(fills: list[dict[str, Any]]) -> tuple[list[RealizedTrade], list[OpenLot], list[str]]:
    """FIFO-match fills oldest-first. A closing fill consumes opening lots in order; leftovers
    open a new lot (negative quantity when the leftover is a short)."""
    ordered = sorted(fills, key=lambda f: str(f.get("filled_at") or ""))
    lots: dict[str, deque[list[Any]]] = defaultdict(deque)  # key -> [signed_qty, price, opened_at]
    meta: dict[str, dict[str, Any]] = {}
    trades: list[RealizedTrade] = []
    unpriced: list[str] = []

    for fill in ordered:
        key = str(fill.get("contract_key") or fill.get("symbol") or "")
        price = fill.get("price")
        quantity = fill.get("quantity")
        if not key or not quantity or price is None:
            if key:
                unpriced.append(key)
            continue
        price = float(price)
        remaining = float(quantity)
        multiplier = float(fill.get("multiplier") or 1.0)
        sign = 1 if str(fill.get("side")).upper() == "BUY" else -1
        meta.setdefault(key, fill)
        book = lots[key]

        while remaining > 1e-9 and book and (book[0][0] > 0) != (sign > 0):
            lot = book[0]
            long_lot = lot[0] > 0
            matched = min(remaining, abs(lot[0]))
            entry, exit_ = (lot[1], price) if long_lot else (price, lot[1])
            pnl = (exit_ - entry) * matched * multiplier
            trades.append(
                RealizedTrade(
                    contract_key=key,
                    symbol=str(fill.get("symbol") or key),
                    instrument_type=str(fill.get("instrument_type") or "EQUITY"),
                    direction="long" if long_lot else "short",
                    quantity=round(matched, 6),
                    entry_price=entry,
                    exit_price=exit_,
                    pnl=round(pnl, 2),
                    pnl_pct=round((exit_ / entry - 1) * 100, 2) if entry else None,
                    opened_at=str(lot[2]),
                    closed_at=str(fill.get("filled_at") or ""),
                    holding_days=_holding_days(str(lot[2]), str(fill.get("filled_at") or "")),
                )
            )
            lot[0] -= matched if long_lot else -matched
            remaining -= matched
            if abs(lot[0]) < 1e-9:
                book.popleft()

        if remaining > 1e-9:
            book.append([remaining * sign, price, str(fill.get("filled_at") or "")])

    open_lots = [
        OpenLot(
            contract_key=key,
            symbol=str(meta.get(key, {}).get("symbol") or key),
            instrument_type=str(meta.get(key, {}).get("instrument_type") or "EQUITY"),
            quantity=round(lot[0], 6),
            price=lot[1],
            opened_at=lot[2],
        )
        for key, book in lots.items()
        for lot in book
        if abs(lot[0]) > 1e-9
    ]
    warnings: list[str] = []
    if unpriced:
        symbols = sorted(set(unpriced))
        warnings.append(
            f"{len(unpriced)} fill(s) had no execution price and were excluded "
            f"({', '.join(symbols[:6])}{'…' if len(symbols) > 6 else ''})"
        )
    return trades, open_lots, warnings


def _settle_expired_options(open_lots: list[OpenLot], fills: list[dict[str, Any]], today: date) -> tuple[float, list[OpenLot], int]:
    """A long option lot with no closing fill and an expiry in the past died worthless: the whole
    premium is a loss. Returns (loss, still-open lots, expired count)."""
    expiry_by_key = {
        str(f.get("contract_key")): f
        for f in fills
        if str(f.get("instrument_type")).upper() == "OPTION"
    }
    loss = 0.0
    survivors: list[OpenLot] = []
    expired_count = 0
    for lot in open_lots:
        source = expiry_by_key.get(lot.contract_key)
        if lot.instrument_type == "OPTION" and source and _expired(source, today):
            multiplier = float(source.get("multiplier") or 1.0)
            loss -= lot.quantity * lot.price * multiplier
            expired_count += 1
            continue
        survivors.append(lot)
    return round(loss, 2), survivors, expired_count


def reconcile(open_lots: list[OpenLot], snapshot: dict[str, Any] | None) -> list[PositionReconciliation]:
    """Compare replayed open quantity against what the broker actually reports."""
    if snapshot is None:
        return []
    broker = {
        str(p.get("symbol")).upper(): float(p.get("quantity") or 0)
        for p in snapshot.get("positions", [])
        if isinstance(p, dict) and p.get("symbol")
    }
    replayed: dict[str, float] = defaultdict(float)
    for lot in open_lots:
        if lot.instrument_type == "EQUITY":
            replayed[lot.symbol] += lot.quantity

    rows: list[PositionReconciliation] = []
    for symbol in sorted(set(replayed) | set(broker)):
        mine = round(replayed.get(symbol, 0.0), 5)
        theirs = broker.get(symbol)
        if theirs is not None and abs(mine - theirs) < 1e-4:
            continue
        if theirs is None:
            note = "left the account without a sell order — split, transfer, or delisting"
        elif mine == 0:
            note = "held at the broker but no opening fill in the order history"
        else:
            note = "quantity drift — most likely a stock split, which the order feed never reports"
        rows.append(PositionReconciliation(symbol=symbol, replayed_quantity=mine, broker_quantity=theirs, note=note))
    return rows


def _summarize_by_symbol(trades: list[RealizedTrade], snapshot: dict[str, Any] | None) -> list[SymbolPnl]:
    realized: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    wins: dict[str, int] = defaultdict(int)
    for trade in trades:
        realized[trade.symbol] += trade.pnl
        counts[trade.symbol] += 1
        if trade.pnl > 0:
            wins[trade.symbol] += 1

    unrealized: dict[str, float] = {}
    if snapshot:
        for position in snapshot.get("positions", []):
            if isinstance(position, dict) and position.get("symbol") and position.get("unrealized_pl") is not None:
                unrealized[str(position["symbol"]).upper()] = float(position["unrealized_pl"])

    rows = [
        SymbolPnl(
            symbol=symbol,
            realized_pnl=round(realized.get(symbol, 0.0), 2),
            unrealized_pnl=unrealized.get(symbol),
            total_pnl=round(realized.get(symbol, 0.0) + (unrealized.get(symbol) or 0.0), 2),
            trade_count=counts.get(symbol, 0),
            win_count=wins.get(symbol, 0),
        )
        for symbol in set(realized) | set(unrealized)
    ]
    return sorted(rows, key=lambda row: -row.total_pnl)


def build_ledger(
    orders_payload: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
    *,
    today: date | None = None,
) -> TradeLedger | None:
    """Assemble the all-time ledger. Returns None when no fill history has been synced yet."""
    if not orders_payload or not orders_payload.get("fills"):
        return None
    today = today or datetime.now().date()
    fills = [f for f in orders_payload["fills"] if isinstance(f, dict)]

    trades, open_lots, warnings = replay(fills)
    expired_pl, open_lots, expired_count = _settle_expired_options(open_lots, fills, today)
    realized = round(sum(trade.pnl for trade in trades), 2)
    unrealized = (
        round(sum(float(p.get("unrealized_pl") or 0) for p in snapshot.get("positions", [])), 2)
        if snapshot and snapshot.get("positions")
        else None
    )
    wins = sum(1 for trade in trades if trade.pnl > 0)
    fill_times = [str(f.get("filled_at")) for f in fills if f.get("filled_at")]

    caveats = list(warnings)
    if expired_count:
        caveats.append(
            f"{expired_count} option lot(s) expired without a closing trade and are counted as a "
            f"total loss of premium (${abs(expired_pl):,.2f})"
        )
    caveats.append("dividends and interest are not included — the Webull open API exposes no cash-transaction endpoint")
    caveats.append("fees and commissions are not included — the API returns them empty on every fill")
    if unrealized is not None:
        caveats.append(f"unrealized P&L comes from the {_UNREALIZED_SOURCE}, using Webull's own average cost")

    return TradeLedger(
        synced_at=str(orders_payload.get("synced_at") or ""),
        history_start=str(orders_payload.get("history_start") or ""),
        fill_count=len(fills),
        realized_pnl=realized,
        expired_option_pl=expired_pl,
        unrealized_pnl=unrealized,
        all_time_pnl=round(realized + expired_pl + (unrealized or 0.0), 2),
        trade_count=len(trades),
        win_count=wins,
        win_rate_pct=round(wins / len(trades) * 100, 1) if trades else None,
        best_trade=max(trades, key=lambda t: t.pnl) if trades else None,
        worst_trade=min(trades, key=lambda t: t.pnl) if trades else None,
        first_fill_at=min(fill_times) if fill_times else None,
        last_fill_at=max(fill_times) if fill_times else None,
        by_symbol=_summarize_by_symbol(trades, snapshot),
        trades=sorted(trades, key=lambda t: t.closed_at, reverse=True),
        open_lots=open_lots,
        reconciliation=reconcile(open_lots, snapshot),
        caveats=caveats,
    )
