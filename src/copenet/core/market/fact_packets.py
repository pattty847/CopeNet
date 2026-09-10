"""Fact-packet formatter (Insight Engine Phase B) — computed facts → compact model-readable text.

This is the ONLY place feature data becomes prose for a model. Rules (spec §9):
- Input is pre-computed facts (dashboard wire / FeatureSet) — never raw candles.
- Base rates are quoted verbatim from calibrated artifacts; the model must never invent statistics.
- Data-quality caveats are included so the model knows when facts are weak.
"""

from __future__ import annotations

from typing import Any

from .base_rates import BaseRate


def _line(parts: list[str]) -> str:
    return " · ".join(p for p in parts if p)


def market_history_section(
    briefs: list[dict[str, Any]], reads: list[dict[str, Any]], *, limit: int = 5
) -> str | None:
    """The recent trail: what the tape did, and what the model called, on each prior session.

    ``overnight`` covers a single night. This covers the last few sessions, which is what lets a
    briefing read as a continuing story instead of a daily cold start — and it is the only way
    the model can be held to its own prior calls ("risk-on three sessions running, still intact").

    The two lists are expected to be misaligned: briefs go back ~30 days while the read archive
    only begins when archiving shipped. Reads are matched by date and omitted where absent,
    rather than zipped positionally, which would silently attribute the wrong call to a session.
    """
    if not briefs:
        return None
    read_by_date = {str(r.get("generatedAt") or "")[:10]: r for r in reads if r.get("generatedAt")}
    lines: list[str] = []
    # Oldest-first so the trail reads forward in time, the way the narrative should.
    for brief in list(briefs)[:limit][::-1]:
        date = str(brief.get("briefDate") or "").strip()
        if not date:
            continue
        parts = [f"{date}: {brief.get('headline') or 'no headline'}"]
        shifts = brief.get("rrgShifts") or []
        if shifts:
            parts.append(
                "rotation: "
                + ", ".join(
                    f"{s.get('symbol')} {s.get('fromQuadrant')}->{s.get('toQuadrant')}"
                    for s in shifts[:4]
                )
            )
        flips = brief.get("signalFlips") or []
        if flips:
            parts.append("flips: " + ", ".join(f"{f.get('symbol')} {f.get('kind')}" for f in flips[:4]))
        read = read_by_date.get(date)
        called = str((read or {}).get("regime") or "").strip()
        if called:
            parts.append(f"model called: {called}")
        lines.append("  " + " | ".join(parts))
    if not lines:
        return None
    return (
        "RECENT SESSIONS (oldest first — compare today against this trail, and say plainly "
        "whether your prior call is holding up):\n" + "\n".join(lines)
    )


def market_fact_packet(
    wire: dict[str, Any],
    base_rate: BaseRate | None,
    *,
    overnight: dict[str, Any] | None = None,
    history: str | None = None,
) -> str:
    """Format the whole-market packet from the persisted dashboard wire dict.

    ``overnight`` is today's morning-brief wire (the delta vs the previous sweep);
    when present it leads the packet so the model narrates what CHANGED, not just
    what is."""
    sections: list[str] = []

    briefing = (wire.get("briefing") or {}).get("data") or {}
    vix = briefing.get("vix")
    breadth = briefing.get("breadthPct")
    header = [f"AS OF: {wire.get('asOf', 'unknown')}"]
    if vix is not None:
        header.append(f"VIX {vix}")
    if breadth is not None:
        header.append(f"breadth {breadth:.0f}% of tracked names above weekly trend")
    sections.append(_line(header))

    overnight_section = _overnight_section(overnight)
    if overnight_section:
        sections.append(overnight_section)

    # After the overnight delta, before today's raw state: last night, then recent days, then now.
    if history:
        sections.append(history)

    macro = (wire.get("macro") or {}).get("data") or []
    if macro:
        rows = [f"{m['label']} {m['value']} ({m['change']}, 5d)" for m in macro]
        sections.append("MACRO: " + "; ".join(rows))

    rrg = (wire.get("rrg") or {}).get("data") or []
    if rrg:
        by_quadrant: dict[str, list[str]] = {}
        for s in rrg:
            by_quadrant.setdefault(s.get("quadrant", "unknown"), []).append(s["symbol"])
        rows = [f"{quad}: {', '.join(symbols)}" for quad, symbols in sorted(by_quadrant.items())]
        sections.append("SECTOR ROTATION (RRG vs S&P, weekly): " + " | ".join(rows))

    soft = (wire.get("softBottoming") or {}).get("data") or []
    if soft:
        rows = [f"{s['symbol']} (score {s['score']}, drawdown {s['drawdown']}, RSI {s['rsi']})" for s in soft]
        line = "SOFT BOTTOMING FLAGS: " + "; ".join(rows)
        if base_rate is not None and base_rate.n >= 5:
            line += (
                f". Calibrated base rate for this pattern: {base_rate.headline()}; "
                f"beat benchmark {base_rate.pct_beat_bench:.0f}% of the time; "
                f"bull-regime win rate {base_rate.bull_pct_up:.0f}% (n={base_rate.bull_n}), "
                f"bear-regime {base_rate.bear_pct_up:.0f}% (n={base_rate.bear_n})."
            )
        sections.append(line)

    trend = (wire.get("trend") or {}).get("data") or []
    confirmed = [t for t in trend if t.get("confirmed")]
    if confirmed:
        rows = [f"{t['symbol']} {t['direction']} ({t.get('note', '')})" for t in confirmed[:8]]
        sections.append("CONFIRMED WEEKLY TREND CHANGES: " + "; ".join(rows))

    portfolio = (wire.get("portfolio") or {}).get("data") or {}
    positions = portfolio.get("positions") or []
    if positions:
        rows = [f"{p['symbol']} {p.get('pnlPct', 'n/a')}" for p in positions]
        sections.append(
            f"OPERATOR PORTFOLIO: total {portfolio.get('total', 'n/a')}, P&L {portfolio.get('pnl', 'n/a')} "
            f"({'; '.join(rows)})"
        )

    spec = (wire.get("speculative") or {}).get("data") or []
    if spec:
        rows = [f"{s['symbol']} {s.get('pnlPct', 'n/a')} (thesis: {s.get('thesis', 'n/a')})" for s in spec]
        sections.append("SPECULATIVE LANE (sized small, defined exits): " + "; ".join(rows))

    evidence = (wire.get("evidence") or {}).get("data") or []
    if evidence:
        rows = [f"[{e['type']}] {e['symbol']}: {e['headline']} ({e.get('source', '')})" for e in evidence[:8]]
        sections.append("SEC/NEWS EVIDENCE (last 72h): " + "; ".join(rows))
    else:
        sections.append("SEC/NEWS EVIDENCE: none in the current window.")

    return "\n".join(sections)


def _overnight_section(overnight: dict[str, Any] | None) -> str | None:
    """Render the morning-brief delta as one packet section. Verbatim facts only —
    the deltas were computed deterministically in brief.py, never re-derived here."""
    if not overnight or overnight.get("firstSweep"):
        return None
    parts: list[str] = []
    evidence = overnight.get("newEvidence") or []
    if evidence:
        rows = [f"[{e.get('type')}] {e.get('symbol')}: {e.get('headline')}" for e in evidence[:6]]
        parts.append("new SEC/news evidence: " + "; ".join(rows))
    regime = overnight.get("regimeShift")
    if regime:
        parts.append(f"regime shifted {regime.get('from')} → {regime.get('to')}")
    shifts = overnight.get("rrgShifts") or []
    if shifts:
        rows = [f"{s.get('symbol')} {s.get('fromQuadrant')}→{s.get('toQuadrant')}" for s in shifts]
        parts.append("sector rotation moves: " + ", ".join(rows))
    flips = overnight.get("signalFlips") or []
    if flips:
        rows = [f"{f.get('symbol')}: {f.get('detail')}" for f in flips]
        parts.append("signal flips: " + "; ".join(rows))
    movers = overnight.get("movers") or []
    if movers:
        rows = [f"{m.get('symbol')} {m.get('changePct'):+.1f}%" for m in movers if m.get("changePct") is not None]
        if rows:
            parts.append("last-session movers: " + ", ".join(rows))
    portfolio_note = overnight.get("portfolioNote")
    if portfolio_note:
        parts.append(portfolio_note)
    if not parts:
        return "OVERNIGHT CHANGES (since previous sweep): none material — a quiet tape."
    return "OVERNIGHT CHANGES (since previous sweep): " + " | ".join(parts)
