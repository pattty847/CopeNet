"""All-time profit and loss, replayed FIFO from the Webull fill history.

The question this answers: *is the account green since it opened?* Two halves —

- **realized**: FIFO-matched round trips from `orders.py` fills (options at 100x)
- **unrealized**: taken from the live position snapshot (`sync.py`), where Webull's own avg cost
  is authoritative

What this CANNOT see, and therefore reports as caveats rather than silently absorbing:

- dividends and interest — the open API exposes no cash-transaction endpoint
- fees and commissions — every fill returns `fees: []` and `commission: {}`
- share counts changed by corporate actions never appear as an order. Splits ARE corrected for,
  from stored yfinance split history (`orders.py` saves it with the fills), because getting this
  wrong is not a rounding error: an unadjusted 1-for-20 reverse split turned a real $1,273 loss
  into a phantom $241 gain on this account. Delistings and transfers still cannot be seen, so a
  symbol that vanished from the broker has its remaining basis written off (`unaccounted_position_pl`)
  and `reconcile()` shows the raw drift.
- long option lots that were never sold are assumed expired worthless. That premium counts inside
  `realized_pnl` (an expiry IS a realized loss), with `expired_option_pl` kept as a memo so the
  composition stays traceable.

Every assumption above is a separate line item and a caveat string — the headline number is never
allowed to quietly absorb one.
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
    open_position: bool = False  # the broker still holds it — drives holdings vs history split


@dataclass
class PositionReconciliation:
    symbol: str
    replayed_quantity: float
    broker_quantity: float | None
    note: str


@dataclass
class CurvePoint:
    """One step of the cumulative P&L curve. `realized` is closed P&L to that date; `total` adds
    today's open P&L, and only differs from `realized` on the final point."""

    date: str
    realized: float
    total: float


@dataclass
class TradeLedger:
    synced_at: str
    history_start: str
    fill_count: int
    realized_pnl: float
    expired_option_pl: float
    unaccounted_position_pl: float
    unrealized_pnl: float | None
    all_time_pnl: float
    trade_count: int
    win_count: int
    win_rate_pct: float | None
    best_trade: RealizedTrade | None
    worst_trade: RealizedTrade | None
    first_fill_at: str | None
    last_fill_at: str | None
    curve: list[CurvePoint] = field(default_factory=list)
    by_symbol: list[SymbolPnl] = field(default_factory=list)
    trades: list[RealizedTrade] = field(default_factory=list)
    open_lots: list[OpenLot] = field(default_factory=list)
    reconciliation: list[PositionReconciliation] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_wire(self) -> dict[str, Any]:
        return _to_wire(self)


def _holding_days(opened_at: str, closed_at: str) -> int | None:
    """Lot open dates are day strings, fill timestamps are full ISO — compare on the date alone
    so the two never mix naive and tz-aware values."""
    try:
        start = date.fromisoformat(opened_at[:10])
        end = date.fromisoformat(closed_at[:10])
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


def _apply_splits(book: deque[list[Any]], split_rows: list[Any], today: str) -> None:
    """Restate open lots for every split whose ex-date falls after the lot opened and on or before
    the fill being processed. A lot opened ON the ex-date already traded post-split, so the bound is
    strict — getting this wrong doubles positions bought the day of a split.

    Lot layout: [signed_qty, price, opened_day, applied_ex_dates]."""
    for lot in book:
        for row in split_rows:
            ex_date, ratio = str(row[0]), float(row[1])
            if lot[2] < ex_date <= today and ex_date not in lot[3]:
                lot[0] *= ratio
                lot[1] /= ratio
                lot[3].add(ex_date)


def replay(
    fills: list[dict[str, Any]],
    splits: dict[str, list[Any]] | None = None,
) -> tuple[list[RealizedTrade], list[OpenLot], list[str]]:
    """FIFO-match fills oldest-first. A closing fill consumes opening lots in order; leftovers
    open a new lot (negative quantity when the leftover is a short).

    Fill quantities are as-of-trade-day, so open lots are restated across splits before matching.
    Without that, a 1-for-20 reverse split makes 8 post-split shares match against a pre-split cost
    basis — which turned a real $1,273 loss into a phantom $241 gain on a live account before this
    existed."""
    ordered = sorted(fills, key=lambda f: str(f.get("filled_at") or ""))
    splits = splits or {}
    lots: dict[str, deque[list[Any]]] = defaultdict(deque)
    meta: dict[str, dict[str, Any]] = {}
    trades: list[RealizedTrade] = []
    unpriced: list[str] = []

    for fill in ordered:
        key = str(fill.get("contract_key") or fill.get("symbol") or "")
        price = fill.get("price")
        quantity = fill.get("quantity")
        if not key:
            continue
        day = str(fill.get("filled_at") or "")[:10]
        if str(fill.get("instrument_type")).upper() == "EQUITY":
            _apply_splits(lots[key], splits.get(str(fill.get("symbol") or ""), []), day)
        if not quantity or price is None:
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
            book.append([remaining * sign, price, day, set()])

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


def _settle_expired_options(open_lots: list[OpenLot], fills: list[dict[str, Any]], today: date) -> tuple[float, list[OpenLot], int, list[tuple[str, float]]]:
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
    dated: list[tuple[str, float]] = []
    for lot in open_lots:
        source = expiry_by_key.get(lot.contract_key)
        if lot.instrument_type == "OPTION" and source and _expired(source, today):
            multiplier = float(source.get("multiplier") or 1.0)
            amount = -lot.quantity * lot.price * multiplier
            loss += amount
            expired_count += 1
            dated.append((str(source.get("option_expire_date") or lot.opened_at), round(amount, 2)))
            continue
        survivors.append(lot)
    return round(loss, 2), survivors, expired_count, dated


def _settle_unaccounted_positions(
    open_lots: list[OpenLot],
    snapshot: dict[str, Any] | None,
) -> tuple[float, list[OpenLot], list[str], list[tuple[str, float]]]:
    """Equity lots for a symbol the broker no longer holds at all: those shares left the account
    without a sell order we can see — a delisting, a transfer, or a split we have no data for.

    Whatever happened, that cost basis is not sitting in the portfolio, so carrying it as an open
    position would flatter the total. Same conservative rule as an expired option: the remaining
    basis is written off, the symbols are named, and `reconciliation` still shows the raw drift.
    Only fully-vanished symbols settle — a partial quantity mismatch is reported, never assumed."""
    if snapshot is None:
        return 0.0, open_lots, [], []
    broker = {
        str(p.get("symbol")).upper()
        for p in snapshot.get("positions", [])
        if isinstance(p, dict) and p.get("symbol")
    }
    settled = 0.0
    survivors: list[OpenLot] = []
    symbols: list[str] = []
    dated: list[tuple[str, float]] = []
    for lot in open_lots:
        if lot.instrument_type == "EQUITY" and lot.symbol not in broker:
            amount = -lot.quantity * lot.price
            settled += amount
            symbols.append(lot.symbol)
            # No exit date exists for a position that vanished; the lot's own date is the only
            # honest anchor for placing it on the curve.
            dated.append((lot.opened_at, round(amount, 2)))
            continue
        survivors.append(lot)
    return round(settled, 2), survivors, sorted(set(symbols)), dated


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


def _held_symbols(snapshot: dict[str, Any] | None) -> set[str]:
    """What the broker reports holding right now — the line between a live position and history."""
    if not snapshot:
        return set()
    return {
        str(position["symbol"]).upper()
        for position in snapshot.get("positions", [])
        if isinstance(position, dict) and position.get("symbol")
    }


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

    held = _held_symbols(snapshot)
    rows = [
        SymbolPnl(
            symbol=symbol,
            realized_pnl=round(realized.get(symbol, 0.0), 2),
            unrealized_pnl=unrealized.get(symbol),
            total_pnl=round(realized.get(symbol, 0.0) + (unrealized.get(symbol) or 0.0), 2),
            trade_count=counts.get(symbol, 0),
            win_count=wins.get(symbol, 0),
            open_position=symbol in held,
        )
        for symbol in set(realized) | set(unrealized) | held
    ]
    return sorted(rows, key=lambda row: -row.total_pnl)


def build_equity_curve(
    trades: list[RealizedTrade],
    write_offs: list[tuple[str, float]],
    unrealized: float | None,
    *,
    today: date,
) -> list[CurvePoint]:
    """Cumulative realized P&L, one point per day something closed, with today's open P&L added at
    the tail so the last point equals the headline.

    Realized-only along the way — mark-to-market of *past* holdings would need a price history for
    every symbol ever held, including delisted ones we cannot fetch. This curve answers "how did I
    get here" from facts we actually have, rather than fabricating a smooth line."""
    events: dict[str, float] = defaultdict(float)
    for trade in trades:
        day = str(trade.closed_at)[:10]
        if day:
            events[day] += trade.pnl
    for day, amount in write_offs:
        if day:
            events[day[:10]] += amount
    if not events:
        return []

    running = 0.0
    points: list[CurvePoint] = []
    for day in sorted(events):
        running += events[day]
        points.append(CurvePoint(date=day, realized=round(running, 2), total=round(running, 2)))

    # The tail carries unrealized so the curve ends on the same number the panel shows.
    if unrealized:
        last = points[-1]
        end = today.isoformat()
        if end == last.date:
            points[-1] = CurvePoint(date=end, realized=last.realized, total=round(last.realized + unrealized, 2))
        else:
            points.append(CurvePoint(date=end, realized=last.realized, total=round(last.realized + unrealized, 2)))
    return points


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

    splits = orders_payload.get("splits") if isinstance(orders_payload.get("splits"), dict) else {}
    trades, replayed_lots, warnings = replay(fills, splits)
    expired_pl, open_lots, expired_count, expired_events = _settle_expired_options(replayed_lots, fills, today)
    # Reconciliation reads the pre-settlement lots so the raw drift stays visible in the table
    # even after the vanished positions have been written off below.
    reconciliation = reconcile(open_lots, snapshot)
    unaccounted_pl, open_lots, unaccounted_symbols, unaccounted_events = _settle_unaccounted_positions(open_lots, snapshot)
    round_trip = round(sum(trade.pnl for trade in trades), 2)
    # Expired premium is a realized loss like any other — the operator asked for it counted, not
    # quarantined. `expired_option_pl` stays as a memo so the composition is still traceable.
    realized = round(round_trip + expired_pl, 2)
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
            f"{expired_count} option lot(s) expired without a closing trade; the premium "
            f"(${abs(expired_pl):,.2f}) is counted in realized P&L"
        )
    estimated = [f for f in fills if str(f.get("price_source")) == "limit"]
    if estimated:
        caveats.append(
            f"{len(estimated)} fill(s) returned no execution price; their order's limit price is "
            "used as the estimate — a limit order fills at the limit or better, so this can only "
            "overstate the loss"
        )
    if unaccounted_symbols:
        caveats.append(
            f"{', '.join(unaccounted_symbols)} left the account with no sell order in the history; "
            f"the remaining cost basis (${abs(unaccounted_pl):,.2f}) is written off as a loss"
        )
    delisted = [str(symbol) for symbol in orders_payload.get("split_data_unavailable") or []]
    if delisted:
        caveats.append(
            f"no corporate-action data for {len(delisted)} delisted ticker(s) — their share counts "
            f"could not be split-adjusted ({', '.join(delisted[:8])}{'…' if len(delisted) > 8 else ''})"
        )
    caveats.append("dividends and interest are not included — the Webull open API exposes no cash-transaction endpoint")
    caveats.append("fees and commissions are not included — the API returns them empty on every fill")
    if not splits:
        caveats.append("no split history stored with these fills — re-sync to make the share-count replay split-aware")
    if unrealized is not None:
        caveats.append(f"unrealized P&L comes from the {_UNREALIZED_SOURCE}, using Webull's own average cost")

    return TradeLedger(
        synced_at=str(orders_payload.get("synced_at") or ""),
        history_start=str(orders_payload.get("history_start") or ""),
        fill_count=len(fills),
        realized_pnl=realized,
        expired_option_pl=expired_pl,
        unaccounted_position_pl=unaccounted_pl,
        unrealized_pnl=unrealized,
        all_time_pnl=round(realized + unaccounted_pl + (unrealized or 0.0), 2),
        trade_count=len(trades),
        win_count=wins,
        win_rate_pct=round(wins / len(trades) * 100, 1) if trades else None,
        best_trade=max(trades, key=lambda t: t.pnl) if trades else None,
        worst_trade=min(trades, key=lambda t: t.pnl) if trades else None,
        first_fill_at=min(fill_times) if fill_times else None,
        last_fill_at=max(fill_times) if fill_times else None,
        curve=build_equity_curve(trades, expired_events + unaccounted_events, unrealized, today=today),
        by_symbol=_summarize_by_symbol(trades, snapshot),
        trades=sorted(trades, key=lambda t: t.closed_at, reverse=True),
        open_lots=open_lots,
        reconciliation=reconciliation,
        caveats=caveats,
    )
