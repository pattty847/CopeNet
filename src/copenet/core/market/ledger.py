"""Forward Ledger — the model's market calls, logged at read time and scored at horizon.

Backtesting an LLM on market history is contaminated (it memorized the past); a forward
ledger is contamination-proof truth. Every model read makes scoreable claims:

- MARKET read → one "regime" claim (risk-on / chop / risk-off / event-risk), scored
  against VOO's realized forward return.
- MARKET read → one "attention" claim per attention item, scored on whether the symbol
  actually moved materially.
- TICKER read → one "lean" claim (bullish / bearish / neutral), scored against the
  symbol's realized forward return.

PRE-REGISTERED RESOLUTION RULES (v1 — changing these invalidates accumulated stats, so
bump LEDGER_RULES_VERSION and start a fresh ledger file if they ever change):

  regime @ horizon (VOO total return over the window):
    risk-on   correct if VOO return >= +1.0%
    chop      correct if -3.0% < VOO return < +3.0%
    risk-off  correct if VOO return <= -1.0%
    event-risk is never scored (unscoreable — it's a warning, not a direction)
    (risk-on/chop and chop/risk-off deliberately overlap: a +2% tape is consistent with
     both a mild risk-on and a chop call; overlap beats a false knife-edge.)

  lean @ horizon (symbol total return over the window):
    bullish  correct if return > 0
    bearish  correct if return < 0
    neutral  push — recorded, never counted in accuracy
    Confidence is stored so calibration can slice by it.

  attention @ horizon:
    correct if abs(symbol return) >= 5.0%, or abs(symbol return - VOO return) >= 3.0%
    ("worth your attention" means it moved, either absolutely or vs the tape.)

  screen @ horizon (added 2026-09-02, additive — no existing outcome changes):
    The deterministic screens make claims too, so the ledger compares the model against
    the rules the operator can actually tune. A claim is logged when a screen NEWLY fires
    at the morning sweep: soft bottoming fires → bullish; a weekly trend flip to up that is
    daily-confirmed → bullish; a flip to down → bearish; accumulation confluence reaching
    3/4 → bullish. Scored exactly like leans (bullish correct if return > 0, bearish if < 0).

  baseline (computed at report time, never stored):
    A hit rate means nothing without the dart it is measured against. For attention, lean
    and screen claims the baseline is the share of the tracked universe (holdings, watch,
    trend, spec and sector names — never the index or macro rows) that would have satisfied
    the same rule over the same window, averaged across matched scored claims. Reporting
    uses completed session closes that match the recorded snapshots, discloses coverage,
    and excludes unreconstructable windows without changing recorded outcomes. For regime calls
    the baseline is the best constant call ("always chop") over the same windows.

Horizons: 4w (28 days) and 8w (56 days) from claim creation. Claims resolve during the
morning sweep (prices are fresh) using the stored daily bars' latest close.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from copenet.core._json_store import read_json, write_json_atomic

from .store import MarketStore

_LOG = logging.getLogger(__name__)

LEDGER_RULES_VERSION = "v1"
HORIZON_DAYS = {"4w": 28, "8w": 56}

_REGIME_RULES = {
    "risk-on": lambda r: r >= 1.0,
    "chop": lambda r: -3.0 < r < 3.0,
    "risk-off": lambda r: r <= -1.0,
}
_ATTENTION_ABS_MOVE_PCT = 5.0
_ATTENTION_EXCESS_PCT = 3.0
SCREEN_KIND = "screen"
_SCREEN_ACCUMULATION_MIN_CONFLUENCE = 3
_SCREEN_REFIRE_GRACE_DAYS = 7  # a flag that clears and re-fires within a week is one episode
CLAIM_KINDS = ("regime", "lean", "attention", SCREEN_KIND)
_MAX_CLAIMS = 5000  # oldest-resolved pruned beyond this; far above years of daily use


@dataclass
class HorizonSlot:
    due_at: str
    resolved_at: str | None = None
    price: float | None = None
    voo: float | None = None
    return_pct: float | None = None
    excess_pct: float | None = None
    outcome: str | None = None  # correct | incorrect | push | unscoreable


@dataclass
class LedgerClaim:
    claim_id: str
    created_at: str
    kind: str  # regime | lean | attention
    target: str  # "VOO" for regime, else the symbol
    value: str  # the claim: "risk-on", "bullish", "attention", ...
    confidence: str | None
    model: str
    note: str  # short human context (attention "why", etc.) — display only, never scored
    snapshot_price: float | None
    snapshot_voo: float | None
    horizons: dict[str, HorizonSlot] = field(default_factory=dict)
    signal: str | None = None  # screen claims: soft-bottoming | trend | accumulation

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "LedgerClaim":
        horizons = {}
        for key, slot in (raw.get("horizons") or {}).items():
            if isinstance(slot, dict) and slot.get("due_at"):
                horizons[key] = HorizonSlot(**{k: slot.get(k) for k in HorizonSlot.__dataclass_fields__})
        return cls(
            claim_id=str(raw.get("claim_id") or ""),
            created_at=str(raw.get("created_at") or ""),
            kind=str(raw.get("kind") or ""),
            target=str(raw.get("target") or ""),
            value=str(raw.get("value") or ""),
            confidence=raw.get("confidence"),
            model=str(raw.get("model") or ""),
            note=str(raw.get("note") or ""),
            snapshot_price=raw.get("snapshot_price"),
            snapshot_voo=raw.get("snapshot_voo"),
            horizons=horizons,
            signal=raw.get("signal"),
        )


class LedgerStore:
    """Claims file under the market dir. Append/update via full-file atomic writes —
    a handful of claims per day never outgrows that."""

    def __init__(self, market_store: MarketStore) -> None:
        self._path = market_store.root_dir / "ledger" / "claims.json"

    def load(self) -> list[LedgerClaim]:
        raw = read_json(self._path, {})
        rows = raw.get("claims") if isinstance(raw, dict) else None
        claims = []
        for row in rows or []:
            if isinstance(row, dict) and row.get("claim_id"):
                claims.append(LedgerClaim.from_json(row))
        return claims

    def save(self, claims: list[LedgerClaim]) -> None:
        if len(claims) > _MAX_CLAIMS:
            resolved = [c for c in claims if _fully_resolved(c)]
            resolved.sort(key=lambda c: c.created_at)
            drop = {c.claim_id for c in resolved[: len(claims) - _MAX_CLAIMS]}
            claims = [c for c in claims if c.claim_id not in drop]
        write_json_atomic(self._path, {"rulesVersion": LEDGER_RULES_VERSION, "claims": [c.to_json() for c in claims]})


def _fully_resolved(claim: LedgerClaim) -> bool:
    return all(slot.resolved_at for slot in claim.horizons.values())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_horizons(created_at: datetime) -> dict[str, HorizonSlot]:
    return {
        key: HorizonSlot(due_at=(created_at + timedelta(days=days)).isoformat().replace("+00:00", "Z"))
        for key, days in HORIZON_DAYS.items()
    }


def _last_close(store: MarketStore, symbol: str) -> float | None:
    bars = store.load_bars(symbol, "daily")
    return float(bars[-1].c) if bars else None


# ---------- capture ----------


def record_market_read_claims(store: MarketStore, read_wire: dict[str, Any]) -> int:
    """Log the regime call + attention items from a market read. Returns claims added."""
    ledger = LedgerStore(store)
    claims = ledger.load()
    now = datetime.now(timezone.utc)
    voo = _last_close(store, "VOO")
    model = str(read_wire.get("model") or "")
    added = 0

    regime = str(read_wire.get("regime") or "").strip()
    if regime:
        claims.append(
            LedgerClaim(
                claim_id=uuid4().hex[:12],
                created_at=_now_iso(),
                kind="regime",
                target="VOO",
                value=regime,
                confidence=None,
                model=model,
                note=str(read_wire.get("regimeReasoning") or "")[:160],
                snapshot_price=voo,
                snapshot_voo=voo,
                horizons=_new_horizons(now),
            )
        )
        added += 1

    for item in read_wire.get("attention") or []:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        claims.append(
            LedgerClaim(
                claim_id=uuid4().hex[:12],
                created_at=_now_iso(),
                kind="attention",
                target=symbol,
                value="attention",
                confidence=None,
                model=model,
                note=str(item.get("why") or "")[:160],
                snapshot_price=_last_close(store, symbol),
                snapshot_voo=voo,
                horizons=_new_horizons(now),
            )
        )
        added += 1

    if added:
        ledger.save(claims)
    return added


def record_ticker_read_claim(store: MarketStore, symbol: str, read_wire: dict[str, Any]) -> int:
    """Log a ticker read's directional lean. Returns claims added (0 or 1)."""
    lean = str(read_wire.get("lean") or "").strip().lower()
    if lean not in {"bullish", "bearish", "neutral"}:
        return 0
    ledger = LedgerStore(store)
    claims = ledger.load()
    claims.append(
        LedgerClaim(
            claim_id=uuid4().hex[:12],
            created_at=_now_iso(),
            kind="lean",
            target=symbol.strip().upper(),
            value=lean,
            confidence=str(read_wire.get("confidence") or "") or None,
            model=str(read_wire.get("model") or ""),
            note=str(read_wire.get("read") or "")[:160],
            snapshot_price=_last_close(store, symbol.strip().upper()),
            snapshot_voo=_last_close(store, "VOO"),
            horizons=_new_horizons(datetime.now(timezone.utc)),
        )
    )
    ledger.save(claims)
    return 1


# ---------- resolution ----------


def _wire_rows(wire: dict[str, Any], panel: str) -> list[dict[str, Any]]:
    data = (wire.get(panel) or {}).get("data") if isinstance(wire.get(panel), dict) else None
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _is_first_sweep(previous_wire: dict[str, Any]) -> bool:
    as_of = str(previous_wire.get("asOf") or "")
    return not as_of or as_of.startswith("as of no market refresh")


def _screen_events(previous_wire: dict[str, Any], current_wire: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """(signal, symbol, value, note) for every screen that NEWLY fires between two sweeps."""
    events: list[tuple[str, str, str, str]] = []
    prev_soft = {str(row.get("symbol")) for row in _wire_rows(previous_wire, "softBottoming")}
    for row in _wire_rows(current_wire, "softBottoming"):
        symbol = str(row.get("symbol") or "").upper()
        if symbol and symbol not in prev_soft:
            events.append(("soft-bottoming", symbol, "bullish", f"soft bottoming fired (score {row.get('score')}) · {row.get('drawdown')} dd · RSI {row.get('rsi')}"))
    prev_trend = {str(row.get("symbol")): row for row in _wire_rows(previous_wire, "trend")}
    for row in _wire_rows(current_wire, "trend"):
        symbol = str(row.get("symbol") or "").upper()
        before = prev_trend.get(symbol)
        direction = str(row.get("direction") or "")
        if not symbol or before is None or before.get("direction") == direction:
            continue
        if direction == "up" and row.get("confirmed"):
            events.append(("trend", symbol, "bullish", f"weekly trend flipped {before.get('direction')} → up (confirmed)"))
        elif direction == "down":
            events.append(("trend", symbol, "bearish", f"weekly trend flipped {before.get('direction')} → down"))
    prev_acc = {str(row.get("symbol")): int(row.get("confluence") or 0) for row in _wire_rows(previous_wire, "accumulation")}
    for row in _wire_rows(current_wire, "accumulation"):
        symbol = str(row.get("symbol") or "").upper()
        confluence = int(row.get("confluence") or 0)
        if symbol and confluence >= _SCREEN_ACCUMULATION_MIN_CONFLUENCE and prev_acc.get(symbol, 0) < _SCREEN_ACCUMULATION_MIN_CONFLUENCE:
            events.append(("accumulation", symbol, "bullish", f"accumulation confluence {confluence}/4 · {row.get('why') or row.get('belowMa')}"))
    return events


def record_screen_claims(store: MarketStore, previous_wire: dict[str, Any], current_wire: dict[str, Any]) -> int:
    """Log one claim per screen that newly fired between two sweeps. Never on the first
    sweep (everything would look new), and never twice for the same symbol+screen within
    the re-fire grace window. Returns claims added."""
    if _is_first_sweep(previous_wire):
        return 0
    events = _screen_events(previous_wire, current_wire)
    if not events:
        return 0
    ledger = LedgerStore(store)
    claims = ledger.load()
    now = datetime.now(timezone.utc)
    grace = now - timedelta(days=_SCREEN_REFIRE_GRACE_DAYS)
    recent = set()
    for claim in claims:
        if claim.kind != SCREEN_KIND:
            continue
        try:
            created = datetime.fromisoformat(claim.created_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if created >= grace:
            recent.add((claim.signal, claim.target))
    voo = _last_close(store, "VOO")
    added = 0
    for signal, symbol, value, note in events:
        if (signal, symbol) in recent:
            continue
        claims.append(
            LedgerClaim(
                claim_id=uuid4().hex[:12],
                created_at=_now_iso(),
                kind=SCREEN_KIND,
                target=symbol,
                value=value,
                confidence=None,
                model="screen",
                note=note[:160],
                snapshot_price=_last_close(store, symbol),
                snapshot_voo=voo,
                horizons=_new_horizons(now),
                signal=signal,
            )
        )
        recent.add((signal, symbol))
        added += 1
    if added:
        ledger.save(claims)
    return added


def resolve_due_claims(store: MarketStore) -> int:
    """Score every horizon slot past due, using current stored daily closes. Returns slots resolved."""
    ledger = LedgerStore(store)
    claims = ledger.load()
    if not claims:
        return 0
    now = datetime.now(timezone.utc)
    voo_now = _last_close(store, "VOO")
    resolved = 0
    for claim in claims:
        for slot in claim.horizons.values():
            if slot.resolved_at:
                continue
            try:
                due = datetime.fromisoformat(slot.due_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if due > now:
                continue
            price_now = _last_close(store, claim.target)
            slot.resolved_at = _now_iso()
            slot.price = price_now
            slot.voo = voo_now
            if price_now is None or not claim.snapshot_price:
                slot.outcome = "unscoreable"
                resolved += 1
                continue
            slot.return_pct = round(((price_now / claim.snapshot_price) - 1) * 100, 2)
            if voo_now is not None and claim.snapshot_voo:
                voo_return = ((voo_now / claim.snapshot_voo) - 1) * 100
                slot.excess_pct = round(slot.return_pct - voo_return, 2)
            slot.outcome = _score(claim, slot)
            resolved += 1
    if resolved:
        ledger.save(claims)
        _LOG.info("forward ledger: resolved %d claim horizon(s)", resolved)
    return resolved


def _score(claim: LedgerClaim, slot: HorizonSlot) -> str:
    r = slot.return_pct if slot.return_pct is not None else 0.0
    if claim.kind == "regime":
        rule = _REGIME_RULES.get(claim.value)
        if rule is None:
            return "unscoreable"  # event-risk (and any unknown value)
        return "correct" if rule(r) else "incorrect"
    if claim.kind in ("lean", SCREEN_KIND):
        if claim.value == "neutral":
            return "push"
        if claim.value == "bullish":
            return "correct" if r > 0 else "incorrect"
        return "correct" if r < 0 else "incorrect"
    if claim.kind == "attention":
        moved = abs(r) >= _ATTENTION_ABS_MOVE_PCT
        excess = slot.excess_pct is not None and abs(slot.excess_pct) >= _ATTENTION_EXCESS_PCT
        return "correct" if (moved or excess) else "incorrect"
    return "unscoreable"
