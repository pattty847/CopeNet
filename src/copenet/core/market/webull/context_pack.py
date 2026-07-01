"""Portfolio context pack — the ONLY portfolio artifact a model may see.

Built exclusively from the sanitized snapshot dict (whitelisted fields; account id pre-masked;
no credentials/tokens exist anywhere in its inputs). Includes an analytical-only instruction
header, allocation/concentration summary, and risk flags. Redaction is unit-tested.
"""

from __future__ import annotations

from typing import Any

MODEL_INSTRUCTION_HEADER = (
    "PORTFOLIO CONTEXT (read-only account snapshot). Analyze this portfolio context. Do not provide "
    "personalized financial advice or tell the user to buy/sell. Focus on risk, exposure, "
    "concentration, notable changes, questions to investigate, and scenario analysis."
)

OVERSIZED_ALLOCATION_PCT = 25.0
LARGE_LOSER_PCT = -25.0
LARGE_WINNER_PCT = 50.0


def _fmt(value: Any, *, money: bool = False, pct: bool = False) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if money:
        return f"${number:,.2f}"
    if pct:
        return f"{number:+.1f}%"
    return f"{number:g}"


def build_portfolio_context_pack(snapshot: dict[str, Any]) -> str:
    positions = [p for p in snapshot.get("positions", []) if isinstance(p, dict)]
    lines: list[str] = [MODEL_INSTRUCTION_HEADER, ""]
    lines.append(
        f"ACCOUNT: {snapshot.get('accountIdMasked') or snapshot.get('account_id_masked') or '***'} "
        f"· synced {snapshot.get('synced_at', 'unknown')} · account data source: Webull · price source: yfinance/Webull per position"
    )
    summary_bits = []
    if snapshot.get("total_equity") is not None:
        summary_bits.append(f"total equity {_fmt(snapshot['total_equity'], money=True)}")
    if snapshot.get("cash") is not None:
        summary_bits.append(f"cash {_fmt(snapshot['cash'], money=True)}")
    if snapshot.get("buying_power") is not None:
        summary_bits.append(f"buying power {_fmt(snapshot['buying_power'], money=True)}")
    if summary_bits:
        lines.append("BALANCES: " + " · ".join(summary_bits))

    lines.append("")
    lines.append("POSITIONS (symbol · qty · avg cost · last · mkt value · unrl P&L · unrl % · alloc % · day % · price src):")
    for p in sorted(positions, key=lambda r: -(r.get("market_value") or 0)):
        lines.append(
            "  {sym} · {qty} sh · {cost} · {last} · {mv} · {pl} · {plp} · {alloc} · {day} · {src}".format(
                sym=p.get("symbol", "?"),
                qty=_fmt(p.get("quantity")),
                cost=_fmt(p.get("avg_cost"), money=True),
                last=_fmt(p.get("last_price"), money=True),
                mv=_fmt(p.get("market_value"), money=True),
                pl=_fmt(p.get("unrealized_pl"), money=True),
                plp=_fmt(p.get("unrealized_pl_pct"), pct=True),
                alloc=_fmt(p.get("allocation_pct"), pct=True),
                day=_fmt(p.get("day_change_pct"), pct=True),
                src=p.get("price_source", "?"),
            )
        )

    # concentration summary
    allocated = [p for p in positions if p.get("allocation_pct") is not None]
    top = sorted(allocated, key=lambda r: -r["allocation_pct"])[:5]
    if top:
        lines.append("")
        lines.append("CONCENTRATION: top positions " + ", ".join(f"{p['symbol']} {p['allocation_pct']:.1f}%" for p in top))
    total_equity = snapshot.get("total_equity")
    cash = snapshot.get("cash")
    if total_equity and cash is not None:
        lines.append(f"CASH ALLOCATION: {cash / total_equity * 100:.1f}% of equity")

    # risk flags
    flags: list[str] = []
    for p in allocated:
        if p["allocation_pct"] >= OVERSIZED_ALLOCATION_PCT:
            flags.append(f"oversized position: {p['symbol']} at {p['allocation_pct']:.1f}% of portfolio")
    for p in positions:
        plp = p.get("unrealized_pl_pct")
        if plp is not None and plp <= LARGE_LOSER_PCT:
            flags.append(f"large unrealized loser: {p['symbol']} {plp:+.1f}%")
        if plp is not None and plp >= LARGE_WINNER_PCT:
            flags.append(f"large unrealized winner: {p['symbol']} {plp:+.1f}%")
        for warning in p.get("warnings", []) or []:
            flags.append(f"data gap ({p.get('symbol', '?')}): {warning}")
    for warning in snapshot.get("warnings", []) or []:
        flags.append(f"data gap: {warning}")
    if flags:
        lines.append("")
        lines.append("RISK FLAGS:")
        lines.extend(f"  - {flag}" for flag in flags)

    return "\n".join(lines)
