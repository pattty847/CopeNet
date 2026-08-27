"""Compact model-readable rendering of the complete persisted tape contract."""

from __future__ import annotations

from .market_tape_contract import MarketTapePacket


def _fmt(value: float | None, suffix: str = "", *, signed: bool = True) -> str:
    if value is None:
        return "n/a"
    sign = "+" if signed else ""
    return f"{value:{sign}.2f}{suffix}"


def format_market_tape(packet: MarketTapePacket) -> str:
    """Render the analyst subset; the persisted packet retains every raw/derived field."""
    lines = [
        f"MARKET TAPE SNAPSHOT ({packet.schema_version}, observed {packet.observed_at}, "
        f"generated {packet.generated_at}, completed through {packet.completed_through or 'unknown'}):",
        "  Candle geometry is normalized by ATR; close-location is 0%=low and 100%=high; volume is versus the trailing 20-day average.",
    ]
    for item in packet.instruments:
        summary = item.summary
        latest = item.bars[-1]
        status = "complete" if latest.complete else "PARTIAL CURRENT SESSION"
        if not latest.geometry_valid:
            status += ", INVALID OHLC GEOMETRY"
        lines.append(
            f"  {item.symbol} [{item.role}, {status}]: 1d {_fmt(summary.return_1d_pct, '%')} · "
            f"2d {_fmt(summary.return_2d_pct, '%')} · 5d {_fmt(summary.return_5d_pct, '%')} · "
            f"dist MA20 {_fmt(summary.dist_ma20_atr, ' ATR')} · vol {_fmt(summary.volume_vs_20d, 'x20d', signed=False)} · "
            f"last candle range {_fmt(latest.range_atr, ' ATR', signed=False)}, "
            f"body {_fmt(latest.body_atr, ' ATR', signed=False)}, "
            f"close-location {_fmt(latest.close_location_pct, '%', signed=False)}"
        )
    voo = next((item for item in packet.instruments if item.symbol == "VOO"), None)
    if voo:
        lines.append("VOO RECENT DAILY SEQUENCE (oldest first):")
        for bar in voo.bars[-5:]:
            status = "complete" if bar.complete else "PARTIAL"
            lines.append(
                f"  {bar.date} {status}: return {_fmt(bar.return_pct, '%')} · gap {_fmt(bar.gap_pct, '%')} · "
                f"range {_fmt(bar.range_atr, ' ATR', signed=False)} · "
                f"body {_fmt(bar.body_atr, ' ATR', signed=False)} · "
                f"upper/lower wick {_fmt(bar.upper_wick_atr, ' ATR', signed=False)}/"
                f"{_fmt(bar.lower_wick_atr, ' ATR', signed=False)} · "
                f"close-location {_fmt(bar.close_location_pct, '%', signed=False)} · "
                f"volume {_fmt(bar.volume_vs_20d, 'x20d', signed=False)}"
            )
    p = packet.participation
    lines.append(
        "ACCOUNT-NEUTRAL PARTICIPATION: "
        f"indexes {p.index_positive} positive / {p.index_negative} negative / {p.index_transition} transition; "
        f"sectors {p.sector_positive} positive / {p.sector_negative} negative / {p.sector_transition} transition; "
        f"RSP−VOO 5d {_fmt(p.equal_weight_excess_5d_pct, '%')}; IWM−VOO 5d {_fmt(p.small_cap_excess_5d_pct, '%')}."
    )
    risk = packet.risk_plumbing
    lines.append(
        "RISK PLUMBING: "
        f"HYG−LQD 5d {_fmt(risk.high_yield_excess_5d_pct, '%')} · VIX 1d/5d {_fmt(risk.volatility_1d_pct, '%')}/{_fmt(risk.volatility_5d_pct, '%')} · "
        f"TLT 5d {_fmt(risk.long_duration_5d_pct, '%')} · DXY 5d {_fmt(risk.dollar_5d_pct, '%')} · GLD 5d {_fmt(risk.gold_5d_pct, '%')}"
    )
    moving = sorted(
        (row for row in packet.rrg if row.modes.get("default") and row.modes["default"].velocity is not None),
        key=lambda row: row.modes["default"].velocity or 0,
        reverse=True,
    )[:8]
    if moving:
        lines.append("RRG MOTION (largest default-tail moves; Δx=relative-strength change, Δy=momentum change):")
        for row in moving:
            vector = row.modes["default"]
            fast = row.modes.get("fast")
            slow = row.modes.get("slow")
            description = (
                f"  {row.symbol} {row.quadrant}: Δx {_fmt(vector.delta_x)} · Δy {_fmt(vector.delta_y)} · "
                f"velocity {_fmt(vector.velocity, signed=False)}"
            )
            if fast:
                description += f" · fast ({_fmt(fast.x)},{_fmt(fast.y)})"
            if slow:
                description += f" · slow ({_fmt(slow.x)},{_fmt(slow.y)})"
            lines.append(description)
    for warning in packet.data_quality.warnings:
        lines.append(f"DATA QUALITY WARNING: {warning}")
    return "\n".join(lines)
