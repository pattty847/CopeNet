"""Deterministic benchmark and peer candidate selection (design doc §9).

Nothing in the codebase today maps a resolved company to one of the 11 SPDR
sector ETFs in `core/market/universe.py::SECTOR_SYMBOLS` — this module builds
that mapping. Get it right: a wrong sector benchmark silently undermines the
whole benchmark-hurdle contract, which is the product's central thesis. A
diversified holding company (the UHAL case that motivated this whole feature)
is exactly the edge case that deserves a flagged low-confidence mapping
rather than a silently wrong guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from copenet.core.market.universe import SECTOR_SYMBOLS

DEFAULT_PRIMARY_BENCHMARK = "VOO"

# yfinance's Ticker.info "sector" field uses these GICS-like labels. Mapped to
# the SPDR sector ETF in SECTOR_SYMBOLS that tracks it. SMH (semiconductors)
# is deliberately not a mapping target here — it's a niche sub-sector ETF, not
# one of the 11 broad GICS sectors this table covers.
GICS_SECTOR_TO_ETF: dict[str, str] = {
    "Technology": "XLK",
    "Energy": "XLE",
    "Financial Services": "XLF",
    "Industrials": "XLI",
    "Healthcare": "XLV",
    "Consumer Defensive": "XLP",
    "Consumer Cyclical": "XLY",
    "Utilities": "XLU",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}


@dataclass(frozen=True)
class BenchmarkPlan:
    primary_benchmark: str
    sector_benchmark: str | None
    peer_benchmarks: list[str] = field(default_factory=list)
    sector_label: str | None = None
    mapping_confidence: str = "high"  # "high" | "low" | "unmapped"
    rationale: str = ""


def _fetch_sector_label(symbol: str) -> str | None:
    """Best-effort sector lookup via yfinance's full `.info` dict. Tolerant by
    design, matching data_sources.py's other yfinance callers: any failure or
    missing field returns None rather than raising."""
    try:
        import yfinance as yf

        info = yf.Ticker(symbol.strip().upper()).info
    except Exception:
        return None
    if not isinstance(info, dict):
        return None
    sector = info.get("sector")
    return str(sector).strip() if isinstance(sector, str) and sector.strip() else None


def resolve_benchmarks(
    symbol: str,
    *,
    primary_override: str | None = None,
    sector_override: str | None = None,
    peer_overrides: list[str] | None = None,
) -> BenchmarkPlan:
    """Resolve the benchmark plan for one subject, recording a rationale and
    confidence so a wrong/missing sector mapping is visible, not silent.

    Explicit overrides always win over the deterministic default and are
    always "high" confidence — the operator said so directly.
    """
    primary = (primary_override or "").strip() or DEFAULT_PRIMARY_BENCHMARK

    if sector_override and sector_override.strip():
        return BenchmarkPlan(
            primary_benchmark=primary,
            sector_benchmark=sector_override.strip().upper(),
            peer_benchmarks=[p.strip().upper() for p in (peer_overrides or []) if p.strip()],
            sector_label=None,
            mapping_confidence="high",
            rationale="operator override",
        )

    sector_label = _fetch_sector_label(symbol)
    if sector_label is None:
        return BenchmarkPlan(
            primary_benchmark=primary,
            sector_benchmark=None,
            peer_benchmarks=[p.strip().upper() for p in (peer_overrides or []) if p.strip()],
            sector_label=None,
            mapping_confidence="unmapped",
            rationale=f"no sector data available for {symbol.strip().upper()} — sector hurdle skipped, not guessed",
        )

    sector_etf = GICS_SECTOR_TO_ETF.get(sector_label)
    if sector_etf is None or sector_etf not in SECTOR_SYMBOLS:
        return BenchmarkPlan(
            primary_benchmark=primary,
            sector_benchmark=None,
            peer_benchmarks=[p.strip().upper() for p in (peer_overrides or []) if p.strip()],
            sector_label=sector_label,
            mapping_confidence="low",
            rationale=(
                f"sector '{sector_label}' has no confident SPDR sector ETF mapping "
                "(e.g. a diversified holding company) — flagged rather than guessed"
            ),
        )

    return BenchmarkPlan(
        primary_benchmark=primary,
        sector_benchmark=sector_etf,
        peer_benchmarks=[p.strip().upper() for p in (peer_overrides or []) if p.strip()],
        sector_label=sector_label,
        mapping_confidence="high",
        rationale=f"'{sector_label}' -> {sector_etf} via GICS sector mapping",
    )
