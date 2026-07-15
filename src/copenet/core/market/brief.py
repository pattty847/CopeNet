"""Morning delta brief — what changed since the previous market sweep.

The sentinel runs one sweep per day (pre-market), so the dashboard state
immediately before a sweep is, by construction, the state the operator last
looked at. Every delta here is computed between the persisted dashboard wire
dicts captured before and after a refresh — no separate snapshot store needed.
The incremental SEC cache upstream (CopeTech-Edgar) guarantees new filings
merge in rather than overwrite, so an evidence diff is a real "what's new".
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .models import EvidenceItem, MorningBriefPayload
from .store import MarketStore
from .universe import UNIVERSE

_MAX_EVIDENCE = 8
_MAX_FLIPS = 8
_MAX_SHIFTS = 6
_MAX_MOVERS = 5
# Minimum |move| for the top mover to claim the headline (honest-quiet rule).
_HEADLINE_MOVER_PCT = 3.0

_UP_QUADRANTS = {"improving", "leading"}


def compute_movers(store: MarketStore, *, limit: int = _MAX_MOVERS) -> tuple[list[dict[str, Any]], str]:
    """Top movers by close-over-close change from the freshly refreshed daily bars.

    Returns (rows, label). The label is self-evidencing freshness: when the newest daily
    bar IS the brief's calendar day (market open, forming candle present) it reads
    "today at the open"; otherwise "last session" — so a stale pull is visible on the
    hero, not silently mislabeled."""
    rows: list[dict[str, Any]] = []
    newest_bar_day: str | None = None
    for asset in UNIVERSE:
        if asset.role not in {"holding", "watch", "spec", "index"}:
            continue
        bars = store.load_bars(asset.symbol, "daily")
        if len(bars) < 2 or not bars[-2].c:
            continue
        # Local calendar day on BOTH sides of the comparison — a UTC day flips past 8 PM ET
        # and would mislabel an evening sweep's forming candle as "last session".
        bar_day = datetime.fromtimestamp(bars[-1].t).strftime("%Y-%m-%d")
        if newest_bar_day is None or bar_day > newest_bar_day:
            newest_bar_day = bar_day
        change = ((bars[-1].c / bars[-2].c) - 1) * 100
        rows.append(
            {
                "symbol": asset.symbol,
                "name": asset.name,
                "last": f"${bars[-1].c:,.2f}",
                "change_pct": round(change, 2),
                "tone": "up" if change > 0 else "down" if change < 0 else "flat",
            }
        )
    rows.sort(key=lambda r: abs(r["change_pct"]), reverse=True)
    label = "today at the open" if newest_bar_day == datetime.now().strftime("%Y-%m-%d") else "last session"
    return rows[:limit], label


def build_morning_brief(
    previous_wire: dict[str, Any],
    current_wire: dict[str, Any],
    *,
    movers: list[dict[str, Any]],
    movers_label: str = "last session",
    brief_date: str | None = None,
    generated_at: str | None = None,
) -> MorningBriefPayload:
    brief_date = brief_date or datetime.now().strftime("%Y-%m-%d")
    generated_at = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    first_sweep = _is_first_sweep(previous_wire)

    if first_sweep:
        new_evidence: list[EvidenceItem] = []
        signal_flips: list[dict[str, Any]] = []
        rrg_shifts: list[dict[str, Any]] = []
        regime_shift: dict[str, Any] | None = None
        portfolio_note = _portfolio_note(previous_wire, current_wire)
        note = "first sweep — no previous snapshot to diff against"
    else:
        new_evidence = _new_evidence(previous_wire, current_wire)
        signal_flips = _signal_flips(previous_wire, current_wire)
        rrg_shifts = _rrg_shifts(previous_wire, current_wire)
        regime_shift = _regime_shift(previous_wire, current_wire)
        portfolio_note = _portfolio_note(previous_wire, current_wire)
        note = None

    return MorningBriefPayload(
        brief_date=brief_date,
        generated_at=generated_at,
        headline=_headline(
            new_evidence=new_evidence,
            signal_flips=signal_flips,
            rrg_shifts=rrg_shifts,
            movers=movers,
            regime_shift=regime_shift,
            first_sweep=first_sweep,
        ),
        new_evidence=new_evidence,
        signal_flips=signal_flips,
        rrg_shifts=rrg_shifts,
        movers=movers,
        movers_label=movers_label,
        regime_shift=regime_shift,
        portfolio_note=portfolio_note,
        previous_as_of=str(previous_wire.get("asOf") or "") or None,
        first_sweep=first_sweep,
        note=note,
    )


def _is_first_sweep(previous_wire: dict[str, Any]) -> bool:
    as_of = str(previous_wire.get("asOf") or "")
    return not as_of or as_of.startswith("as of no market refresh")


def _panel_rows(wire: dict[str, Any], panel: str) -> list[dict[str, Any]]:
    data = (wire.get(panel) or {}).get("data") if isinstance(wire.get(panel), dict) else None
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _new_evidence(previous_wire: dict[str, Any], current_wire: dict[str, Any]) -> list[EvidenceItem]:
    seen = {_evidence_key(row) for row in _panel_rows(previous_wire, "evidence")}
    fresh: list[EvidenceItem] = []
    for row in _panel_rows(current_wire, "evidence"):
        if _evidence_key(row) in seen:
            continue
        fresh.append(
            EvidenceItem(
                type=row.get("type") or "News",
                symbol=row.get("symbol") or "",
                headline=row.get("headline") or "",
                source=row.get("source") or "",
                tone=row.get("tone") or "flat",
                url=row.get("url"),
                t=row.get("t"),
                flag=row.get("flag"),
                value=row.get("value"),
                price=row.get("price"),
                shares=row.get("shares"),
            )
        )
    return fresh[:_MAX_EVIDENCE]


def _evidence_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("type") or ""), str(row.get("symbol") or ""), str(row.get("headline") or ""))


def _signal_flips(previous_wire: dict[str, Any], current_wire: dict[str, Any]) -> list[dict[str, Any]]:
    flips: list[dict[str, Any]] = []

    prev_soft = {str(row.get("symbol")) for row in _panel_rows(previous_wire, "softBottoming")}
    curr_soft = {str(row.get("symbol")): row for row in _panel_rows(current_wire, "softBottoming")}
    for symbol, row in curr_soft.items():
        if symbol not in prev_soft:
            flips.append(
                {
                    "symbol": symbol,
                    "kind": "soft-bottoming",
                    "detail": f"soft bottoming fired (score {row.get('score')})",
                    "tone": "up",
                }
            )
    for symbol in sorted(prev_soft - set(curr_soft)):
        flips.append({"symbol": symbol, "kind": "soft-bottoming", "detail": "soft bottoming cleared", "tone": "flat"})

    prev_trend = {str(row.get("symbol")): row for row in _panel_rows(previous_wire, "trend")}
    for row in _panel_rows(current_wire, "trend"):
        symbol = str(row.get("symbol"))
        before = prev_trend.get(symbol)
        if before is None or before.get("direction") == row.get("direction"):
            continue
        direction = str(row.get("direction") or "")
        confirmed = " (confirmed)" if row.get("confirmed") else ""
        flips.append(
            {
                "symbol": symbol,
                "kind": "trend",
                "detail": f"weekly trend flipped {before.get('direction')} → {direction}{confirmed}",
                "tone": "up" if direction == "up" else "down",
            }
        )
    return flips[:_MAX_FLIPS]


def _rrg_shifts(previous_wire: dict[str, Any], current_wire: dict[str, Any]) -> list[dict[str, Any]]:
    prev = {str(row.get("symbol")): str(row.get("quadrant") or "") for row in _panel_rows(previous_wire, "rrg")}
    shifts: list[dict[str, Any]] = []
    for row in _panel_rows(current_wire, "rrg"):
        symbol = str(row.get("symbol"))
        quadrant = str(row.get("quadrant") or "")
        before = prev.get(symbol)
        if not before or before == quadrant:
            continue
        shifts.append(
            {
                "symbol": symbol,
                "name": str(row.get("name") or symbol),
                "from_quadrant": before,
                "to_quadrant": quadrant,
                "tone": "up" if quadrant in _UP_QUADRANTS else "down",
            }
        )
    return shifts[:_MAX_SHIFTS]


def _regime_shift(previous_wire: dict[str, Any], current_wire: dict[str, Any]) -> dict[str, Any] | None:
    def current(wire: dict[str, Any]) -> str:
        data = (wire.get("regime") or {}).get("data") if isinstance(wire.get("regime"), dict) else None
        return str(data.get("current") or "") if isinstance(data, dict) else ""

    before, after = current(previous_wire), current(current_wire)
    if before and after and before != after:
        return {"from": before, "to": after}
    return None


def _portfolio_note(previous_wire: dict[str, Any], current_wire: dict[str, Any]) -> str | None:
    """The overnight delta leads; the lifetime P&L is explicitly labeled "all-time" so a
    +20% cost-basis gain can never read as an overnight jump inside "since you last looked"."""

    def panel(wire: dict[str, Any]) -> dict[str, Any]:
        data = (wire.get("portfolio") or {}).get("data") if isinstance(wire.get("portfolio"), dict) else None
        return data if isinstance(data, dict) else {}

    curr = panel(current_wire)
    total = str(curr.get("total") or "")
    if not total or not curr.get("positions"):
        return None
    parts = [f"Portfolio {total}"]
    prev_total = _money(str(panel(previous_wire).get("total") or ""))
    curr_total = _money(total)
    if prev_total is not None and curr_total is not None:
        delta = curr_total - prev_total
        parts.append(f"{delta:+,.0f} since last sweep" if round(delta) != 0 else "flat since last sweep")
    pnl = str(curr.get("pnl") or "").strip()
    if pnl:
        lifetime = pnl.split(" · ")[-1] if "%" in pnl else pnl
        parts.append(f"{lifetime} all-time")
    return " · ".join(parts)


def _money(text: str) -> float | None:
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _headline(
    *,
    new_evidence: list[EvidenceItem],
    signal_flips: list[dict[str, Any]],
    rrg_shifts: list[dict[str, Any]],
    movers: list[dict[str, Any]],
    regime_shift: dict[str, Any] | None,
    first_sweep: bool,
) -> str:
    if first_sweep:
        return "First sweep — baseline captured; deltas start tomorrow."
    bits: list[str] = []
    if new_evidence:
        plural = "s" if len(new_evidence) != 1 else ""
        bits.append(f"{len(new_evidence)} new SEC filing{plural}")
    if regime_shift:
        bits.append(f"regime {regime_shift['from']} → {regime_shift['to']}")
    if rrg_shifts:
        top = rrg_shifts[0]
        bits.append(f"{top['symbol']} rotated to {top['to_quadrant']}")
    if signal_flips:
        plural = "s" if len(signal_flips) != 1 else ""
        bits.append(f"{len(signal_flips)} signal flip{plural}")
    if movers:
        top = movers[0]
        # A mover claims the headline only when it's material — ordinary drift stays in
        # the movers row so a quiet headline stays trustworthy (honest-quiet rule).
        if abs(top["change_pct"]) >= _HEADLINE_MOVER_PCT:
            bits.append(f"{top['symbol']} {top['change_pct']:+.1f}% last session")
    if not bits:
        return "Quiet tape — nothing thesis-relevant changed since the last sweep."
    return " · ".join(bits[:4])
