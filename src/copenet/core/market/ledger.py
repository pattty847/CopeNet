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
    if claim.kind == "lean":
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


# ---------- reporting ----------


def ledger_report(store: MarketStore, *, recent: int = 30) -> dict[str, Any]:
    """Wire payload: calibration stats by kind/horizon (+ confidence slices for leans)
    and the most recent claims, newest first."""
    claims = LedgerStore(store).load()
    stats: dict[str, Any] = {}
    for kind in ("regime", "lean", "attention"):
        by_horizon: dict[str, Any] = {}
        for horizon in HORIZON_DAYS:
            correct = incorrect = push = 0
            for claim in claims:
                if claim.kind != kind:
                    continue
                slot = claim.horizons.get(horizon)
                if not slot or not slot.resolved_at:
                    continue
                if slot.outcome == "correct":
                    correct += 1
                elif slot.outcome == "incorrect":
                    incorrect += 1
                elif slot.outcome == "push":
                    push += 1
            scored = correct + incorrect
            by_horizon[horizon] = {
                "correct": correct,
                "incorrect": incorrect,
                "push": push,
                "accuracyPct": round(correct / scored * 100, 1) if scored else None,
            }
        stats[kind] = by_horizon

    pending = sum(1 for c in claims for s in c.horizons.values() if not s.resolved_at)
    ordered = sorted(claims, key=lambda c: c.created_at, reverse=True)
    return {
        "rulesVersion": LEDGER_RULES_VERSION,
        "totalClaims": len(claims),
        "pendingHorizons": pending,
        "stats": stats,
        "recent": [c.to_json() for c in ordered[:recent]],
    }


def track_record_line(store: MarketStore) -> str | None:
    """One compact sentence for the model's own prompt — its measured track record."""
    report = ledger_report(store, recent=0)
    bits: list[str] = []
    for kind, label in (("regime", "regime calls"), ("lean", "ticker leans"), ("attention", "attention flags")):
        h4 = report["stats"][kind]["4w"]
        scored = h4["correct"] + h4["incorrect"]
        if scored >= 3:
            bits.append(f"{label}: {h4['correct']}/{scored} correct at 4w")
    if not bits:
        return None
    return "YOUR MEASURED TRACK RECORD (forward ledger, pre-registered scoring): " + "; ".join(bits) + "."
