"""Forward-ledger reporting and point-in-time baseline comparisons."""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
from math import isclose
from statistics import mean
from typing import Any

from .ledger import (
    CLAIM_KINDS, HORIZON_DAYS, LEDGER_RULES_VERSION, SCREEN_KIND,
    LedgerClaim, LedgerStore, _ATTENTION_ABS_MOVE_PCT, _ATTENTION_EXCESS_PCT, _REGIME_RULES,
)
from .store import MarketStore
from .price_history import daily_close_available_at
from .universe import UNIVERSE

_DART_ROLES = ("holding", "watch", "trend", "spec", "sector")

# ---------- reporting ----------


def _tally(claims: list[LedgerClaim], horizon: str) -> dict[str, Any]:
    correct = incorrect = push = 0
    for claim in claims:
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
    return {"correct": correct, "incorrect": incorrect, "push": push, "accuracyPct": round(correct / scored * 100, 1) if scored else None}


def _epoch(iso: str) -> float | None:
    try:
        parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo else None
    except ValueError:
        return None


class _CloseLookup:
    """US-equity closes available at a moment, not bars merely dated before it.

    Bars use UTC midnight as a session label, not an availability timestamp. A full daily
    close is conservatively available at 16:00 New York (including early-close days).
    Intraday snapshots cannot be reconstructed from finalized daily bars; callers must
    match the recorded prices before using this lookup for a baseline.
    """

    def __init__(self, store: MarketStore) -> None:
        self._store = store
        self._bars: dict[str, tuple[list[float], list[float]]] = {}

    def at(self, symbol: str, iso: str) -> float | None:
        if symbol not in self._bars:
            bars = sorted(self._store.load_bars(symbol, "daily"), key=lambda bar: bar.t)
            available = [
                daily_close_available_at(bar).timestamp()
                for bar in bars
            ]
            self._bars[symbol] = (available, [float(bar.c) for bar in bars])
        times, closes = self._bars[symbol]
        moment = _epoch(iso)
        if moment is None or not times:
            return None
        index = bisect_right(times, moment) - 1
        # Missing history is not a flat return. Seven days allows weekends/holidays but
        # excludes dormant caches from the comparison population.
        return closes[index] if index >= 0 and moment - times[index] <= 7 * 86400 else None


def _matches(reconstructed: float | None, recorded: float | None) -> bool:
    return reconstructed is not None and recorded is not None and isclose(reconstructed, recorded, rel_tol=1e-8, abs_tol=1e-6)


def dart_universe() -> list[str]:
    """The names a dart could have landed on: everything tracked except the index and macro
    rows, which rarely move 5% and would flatter the model."""
    return [asset.symbol for asset in UNIVERSE if asset.role in _DART_ROLES]


def _window_hit(kind: str, value: str, return_pct: float, excess_pct: float | None) -> bool:
    if kind == "attention":
        return abs(return_pct) >= _ATTENTION_ABS_MOVE_PCT or (excess_pct is not None and abs(excess_pct) >= _ATTENTION_EXCESS_PCT)
    if value == "bullish":
        return return_pct > 0
    if value == "bearish":
        return return_pct < 0
    return False


def _baseline(store: MarketStore, claims: list[LedgerClaim], universe: list[str]) -> dict[str, Any]:
    """Per kind and horizon: what a dart (or the best constant regime call) would have scored
    over the same windows as the scored claims."""
    closes = _CloseLookup(store)
    out: dict[str, Any] = {}
    for kind in ("attention", "lean", SCREEN_KIND):
        by_horizon: dict[str, Any] = {}
        for horizon in HORIZON_DAYS:
            fractions: list[float] = []
            matched_correct = scored_claims = 0
            for claim in claims:
                if claim.kind != kind or claim.value == "neutral":
                    continue
                slot = claim.horizons.get(horizon)
                if not slot or not slot.resolved_at or slot.outcome not in ("correct", "incorrect"):
                    continue
                scored_claims += 1
                voo_start, voo_end = closes.at("VOO", claim.created_at), closes.at("VOO", slot.resolved_at)
                if not all((
                    _matches(closes.at(claim.target, claim.created_at), claim.snapshot_price),
                    _matches(closes.at(claim.target, slot.resolved_at), slot.price),
                    _matches(voo_start, claim.snapshot_voo),
                    _matches(voo_end, slot.voo),
                )):
                    continue
                voo_return = ((voo_end / voo_start) - 1) * 100 if voo_start and voo_end else None
                hits = names = 0
                for symbol in universe:
                    start, end = closes.at(symbol, claim.created_at), closes.at(symbol, slot.resolved_at)
                    if not start or end is None:
                        continue
                    return_pct = round(((end / start) - 1) * 100, 2)
                    excess = round(return_pct - voo_return, 2) if voo_return is not None else None
                    names += 1
                    hits += 1 if _window_hit(kind, claim.value, return_pct, excess) else 0
                # Keep the declared universe intact; silently dropping missing names
                # would turn data coverage into selection bias.
                if names and names == len(universe):
                    fractions.append(hits / names)
                    matched_correct += slot.outcome == "correct"
            by_horizon[horizon] = {
                "pct": round(mean(fractions) * 100, 1) if fractions else None,
                "n": len(universe),
                "label": f"dart over {len(universe)} tracked names",
                "matchedClaims": len(fractions),
                "scoredClaims": scored_claims,
                "accuracyPct": round(matched_correct / len(fractions) * 100, 1) if fractions else None,
            }
        out[kind] = by_horizon

    regime_by_horizon: dict[str, Any] = {}
    for horizon in HORIZON_DAYS:
        returns = [
            claim.horizons[horizon].return_pct
            for claim in claims
            if claim.kind == "regime" and horizon in claim.horizons and claim.horizons[horizon].resolved_at and claim.horizons[horizon].outcome in ("correct", "incorrect") and claim.horizons[horizon].return_pct is not None
        ]
        best_label, best_pct = None, None
        for name, rule in _REGIME_RULES.items():
            if not returns:
                break
            pct = round(sum(1 for r in returns if rule(r)) / len(returns) * 100, 1)
            if best_pct is None or pct > best_pct:
                best_label, best_pct = name, pct
        regime_by_horizon[horizon] = {
            "pct": best_pct, "n": len(returns),
            "label": f"always {best_label}" if best_label else "no scored regime calls",
            "matchedClaims": len(returns), "scoredClaims": len(returns),
            "accuracyPct": _tally([c for c in claims if c.kind == "regime"], horizon)["accuracyPct"],
        }
    out["regime"] = regime_by_horizon
    return out


def ledger_report(store: MarketStore, *, recent: int = 30, baseline_universe: list[str] | None = None) -> dict[str, Any]:
    """Wire payload: calibration stats by kind/horizon, the same per screen signal, the
    baseline each kind is measured against, and the most recent claims, newest first."""
    claims = LedgerStore(store).load()
    stats: dict[str, Any] = {
        kind: {horizon: _tally([c for c in claims if c.kind == kind], horizon) for horizon in HORIZON_DAYS}
        for kind in CLAIM_KINDS
    }
    signals: dict[str, Any] = {}
    for signal in sorted({c.signal for c in claims if c.kind == SCREEN_KIND and c.signal}):
        screen_claims = [c for c in claims if c.kind == SCREEN_KIND and c.signal == signal]
        signals[signal] = {horizon: _tally(screen_claims, horizon) for horizon in HORIZON_DAYS}
    universe = baseline_universe if baseline_universe is not None else dart_universe()

    pending = sum(1 for c in claims for s in c.horizons.values() if not s.resolved_at)
    ordered = sorted(claims, key=lambda c: c.created_at, reverse=True)
    return {
        "rulesVersion": LEDGER_RULES_VERSION,
        "totalClaims": len(claims),
        "pendingHorizons": pending,
        "stats": stats,
        "signals": signals,
        "baseline": _baseline(store, claims, universe),
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
