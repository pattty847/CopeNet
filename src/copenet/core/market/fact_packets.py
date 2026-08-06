"""Fact-packet formatter (Insight Engine Phase B) — computed facts → compact model-readable text.

This is the ONLY place feature data becomes prose for a model. Rules (spec §9):
- Input is pre-computed facts (dashboard wire / FeatureSet) — never raw candles.
- Base rates are quoted verbatim from calibrated artifacts; the model must never invent statistics.
- Data-quality caveats are included so the model knows when facts are weak.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .base_rates import BaseRate
from .features import FeatureSet


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


def _domain(url: str) -> str:
    try:
        return urlparse(url).hostname or url
    except ValueError:
        return url


def _fmt_money(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1e9:
        return f"${value / 1e9:.2f}B"
    if magnitude >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value:,.0f}"


def ticker_fact_packet(
    fs: FeatureSet,
    *,
    name: str,
    base_rate: BaseRate | None,
    verdict: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    fundamentals: dict[str, Any] | None = None,
    news: list[dict[str, Any]] | None = None,
    news_source: str | None = None,
) -> str:
    """Format a single asset's packet from its typed FeatureSet."""
    sections: list[str] = [f"ASSET: {fs.symbol} ({name}) · weekly timeframe · basis {fs.basis}"]

    quality = [f"history {fs.history_weeks} weeks"]
    if fs.thin_history:
        quality.append("THIN HISTORY — treat all trend/shape facts as low-confidence")
    if not fs.has_volume:
        quality.append("no volume data — volume facts unavailable")
    sections.append("DATA QUALITY: " + "; ".join(quality))

    returns = []
    for label, value in (("1w", fs.r_1w), ("4w", fs.r_4w), ("13w", fs.r_13w), ("26w", fs.r_26w), ("52w", fs.r_52w), ("YTD", fs.r_ytd)):
        if value is not None:
            returns.append(f"{label} {value:+.1f}%")
    if returns:
        sections.append("RETURNS: " + ", ".join(returns))

    trend_bits = [f"MA stack: {fs.ma_stack}"]
    for label, dist, slope in (("10w", fs.dist_ma10, fs.slope_ma10), ("30w", fs.dist_ma30, fs.slope_ma30), ("40w", fs.dist_ma40, fs.slope_ma40)):
        if dist is not None:
            slope_txt = f", slope {slope:+.1f}%/5w" if slope is not None else ""
            trend_bits.append(f"{label} MA {dist:+.1f}% away{slope_txt}")
    sections.append("TREND: " + "; ".join(trend_bits))

    # multi-year structure — the horizon a human reads off a 5y chart
    structure_bits = []
    if fs.r_3y is not None:
        structure_bits.append(f"3y return {fs.r_3y:+.0f}%")
    if fs.dist_hi_full is not None and fs.weeks_since_hi_full is not None:
        structure_bits.append(f"{fs.dist_hi_full:+.1f}% from the multi-year high set {fs.weeks_since_hi_full}w ago")
    if fs.pct_range_full is not None:
        structure_bits.append(f"at {fs.pct_range_full:.0f}% of the full historical range")
    if fs.long_trend != "n/a" and fs.long_trend_slope is not None:
        structure_bits.append(f"long trend (2y regression): {fs.long_trend} ~{fs.long_trend_slope:+.0f}%/yr")
    if structure_bits:
        years = fs.history_weeks / 52
        sections.append(f"STRUCTURE (multi-year, {years:.1f}y of weekly history): " + "; ".join(structure_bits))
    if fs.range_ratio_12v36 is not None:
        line = f"RANGE BEHAVIOR: last-12w range is {fs.range_ratio_12v36:.2f}x the prior-24w range"
        if fs.compression:
            line += f" — CONSOLIDATION detected ({fs.compression_shape or 'compressed'}"
            if fs.compression_shape == "symmetrical":
                line += ": lower highs + higher lows converging"
            line += ")"
        sections.append(line)

    risk_bits = []
    if fs.drawdown_pct is not None:
        risk_bits.append(f"drawdown {fs.drawdown_pct:+.1f}% from 52w high")
    if fs.weeks_since_high is not None:
        risk_bits.append(f"{fs.weeks_since_high}w since high")
    if fs.pct_52w is not None:
        risk_bits.append(f"at {fs.pct_52w:.0f}% of 52w range")
    if fs.vol_13w is not None:
        risk_bits.append(f"13w realized vol {fs.vol_13w:.0f}% ann.")
    if fs.atr_pctile is not None:
        risk_bits.append(f"ATR percentile {fs.atr_pctile:.0f}")
    if risk_bits:
        sections.append("RISK STATE: " + "; ".join(risk_bits))

    rel_bits = []
    if fs.excess_13w is not None:
        rel_bits.append(f"13w excess return vs benchmark {fs.excess_13w:+.1f}%")
    if fs.excess_26w is not None:
        rel_bits.append(f"26w excess {fs.excess_26w:+.1f}%")
    if fs.beta_52w is not None:
        rel_bits.append(f"beta {fs.beta_52w:.2f}")
    if fs.rs_momentum is not None:
        rel_bits.append(f"RS momentum {fs.rs_momentum:+.1f}")
    if fs.rsi_14 is not None:
        rel_bits.append(f"RSI(14w) {fs.rsi_14:.0f}")
    if rel_bits:
        sections.append("RELATIVE: " + "; ".join(rel_bits))

    vol_bits = []
    if fs.vol_vs_avg is not None:
        vol_bits.append(f"last-week volume {fs.vol_vs_avg:.1f}x 20w avg")
    if fs.up_down_vol is not None:
        vol_bits.append(f"13w up/down volume ratio {fs.up_down_vol:.2f}")
    if vol_bits:
        sections.append("VOLUME: " + "; ".join(vol_bits))

    if fs.soft_bottoming:
        met = []
        for label, flag in (
            ("lower lows stopped", fs.sb_lower_lows_stopped),
            ("higher low", fs.sb_higher_low),
            ("short-MA reclaim", fs.sb_ma_reclaim),
            ("drawdown stabilized", fs.sb_drawdown_stabilized),
            ("RS improving", fs.sb_rs_improving),
            ("decline volume drying", fs.sb_volume_drying),
            ("momentum divergence", fs.sb_momentum_divergence),
        ):
            met.append(f"{label}: {'yes' if flag else 'no'}")
        line = f"PATTERN — SOFT BOTTOMING FIRING (score {fs.soft_bottoming_score}): " + "; ".join(met)
        if base_rate is not None and base_rate.n >= 5:
            line += f". Calibrated base rate: {base_rate.headline()}."
        sections.append(line)

    if verdict:
        rows = [f"vs {v['bench']}: {v['label']}" for v in verdict]
        sections.append("BENCHMARK VERDICT (risk-adjusted, 1y): " + "; ".join(rows))

    if evidence:
        rows = [f"[{e['type']}] {e['headline']} ({e.get('source', '')})" for e in evidence[:5]]
        sections.append("EVIDENCE: " + "; ".join(rows))

    if fundamentals:
        revenue_q = fundamentals.get("revenueQuarterly") or []
        if revenue_q:
            rows = []
            for r in revenue_q[:4]:
                yoy = r.get("yoy_pct")
                yoy_txt = f", YoY {yoy:+.1%}" if yoy is not None else ""
                rows.append(f"{r['period']} {_fmt_money(r['value'])}{yoy_txt}")
            sections.append("FUNDAMENTALS — REVENUE (quarterly, newest first): " + "; ".join(rows))
        pe_ttm = fundamentals.get("peTtm")
        eps_ttm = fundamentals.get("epsTtm")
        if pe_ttm is not None:
            sections.append(f"VALUATION: trailing P/E ~{pe_ttm:.1f}x (TTM EPS ${eps_ttm:.2f})")
        elif eps_ttm is not None and eps_ttm <= 0:
            sections.append("VALUATION: trailing EPS is negative — P/E not meaningful")
        if not revenue_q and pe_ttm is None:
            sections.append("FUNDAMENTALS: SEC data found but no usable revenue/EPS series for this filer.")
    else:
        sections.append("FUNDAMENTALS: not available (ETF, or no matching SEC company facts).")

    if news:
        rows = [f"\"{n['title']}\" ({_domain(n['url'])}): {n.get('snippet', '').strip()[:180]}" for n in news[:5]]
        source_note = f" [{news_source}]" if news_source else ""
        sections.append(f"RECENT WEB/NEWS{source_note}: " + " | ".join(rows))
    else:
        sections.append("RECENT WEB/NEWS: no results returned (or search unavailable) — do not invent headlines.")

    return "\n".join(sections)
