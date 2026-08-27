"""DTOs for the Market Monitor wire contract.

Internal field names stay Pythonic. ``to_wire`` emits the camelCase JSON shape
consumed by ``host/frontend/src/sections/market/types.ts``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Literal


Tone = Literal["up", "down", "flat"]
Direction = Literal["up", "down"]
PanelStatus = Literal["live", "preview", "stale", "error"]
# "context" = in the scan universe for quotes, deliberately out of the signal panels and breadth.
AssetRole = Literal[
    "index", "holding", "watch", "trend", "spec", "sector", "industry", "macro", "context"
]


@dataclass(frozen=True)
class UniverseAsset:
    symbol: str
    name: str
    role: AssetRole
    yf_symbol: str | None = None

    def to_wire(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "name": self.name, "role": self.role}


@dataclass(frozen=True)
class MarketBar:
    t: int
    o: float
    h: float
    l: float
    c: float
    v: int


@dataclass
class MarketPanel:
    status: PanelStatus
    data: Any
    as_of: str | None = None
    note: str | None = None


@dataclass
class AttentionItem:
    kind: str
    label: str
    glyph: str
    symbol: str


@dataclass
class Briefing:
    headline: str
    summary: str
    changed: list[dict[str, Any]]
    attention: list[AttentionItem]
    vix: float
    breadth_pct: float
    emphasis: str | None = None


@dataclass
class Regime:
    current: Literal["risk-off", "chop", "risk-on", "event-risk"]
    scale: list[dict[str, Any]]


@dataclass
class MacroItem:
    label: str
    value: str
    change: str
    tone: Tone
    spark: list[float]


@dataclass
class RrgSector:
    symbol: str
    name: str
    tail: list[dict[str, float]]
    quadrant: Literal["leading", "weakening", "lagging", "improving"]
    # per-speed tails ("fast" / "default" / "slow"); `tail` above mirrors `tails["default"]`
    # for callers that only ever cared about the single-speed rotation read.
    tails: dict[str, list[dict[str, float]]] = field(default_factory=dict)


@dataclass
class AccumulationRow:
    symbol: str
    name: str
    below_ma: str
    drawdown: str
    rsi: str
    confluence: int
    why: str


@dataclass
class TrendRow:
    symbol: str
    direction: Direction
    note: str
    when: str
    confirmed: bool


@dataclass
class PortfolioPosition:
    symbol: str
    shares: float
    avg_cost: float
    last: str
    pnl_pct: str
    tone: Tone
    nudge: str | None = None


@dataclass
class Portfolio:
    total: str
    pnl: str
    pnl_tone: Tone
    positions: list[PortfolioPosition]


@dataclass
class SpecPosition:
    symbol: str
    pnl_pct: str
    tone: Tone
    thesis: str
    entry: str
    target: str
    invalidation: str


@dataclass
class EvidenceItem:
    type: Literal["Insider", "8-K", "News", "Form 144"]
    symbol: str
    headline: str
    source: str
    tone: Tone
    url: str | None = None
    t: int | None = None  # unix seconds, for chart marker placement
    # Badge-worthy anomaly: "cluster" = multi-insider buy window, "high-signal" = 8-K in a
    # high-signal category (exec change, results, M&A, distress, restructuring, material agreement).
    flag: Literal["cluster", "high-signal"] | None = None
    # Transaction dollar value (Form 4 gross_value / 144 aggregate value / cluster total) —
    # the difference between a $10K trade and a $1B one belongs in the data, not the prose.
    value: float | None = None
    # Per-share transaction price and share count (Form 4 / 144) — lets the chart place
    # cluster boxes at real transaction levels and compute a value-weighted average price.
    price: float | None = None
    shares: float | None = None


@dataclass
class ContrarianNote:
    signal: str
    kill: str


@dataclass
class VerdictRow:
    bench: str
    label: Literal["Beats", "Lags", "In line"]
    pct: str
    tone: Tone


@dataclass
class SignalRow:
    key: str
    value: str
    tone: Tone


@dataclass
class ChartEvent:
    t: int
    kind: Literal["insider", "8-K", "planned-sale"]
    glyph: str


@dataclass
class SoftBottomItem:
    symbol: str
    name: str
    score: float
    drawdown: str
    rsi: str


@dataclass
class DashboardPayload:
    as_of: str
    briefing: MarketPanel
    regime: MarketPanel
    macro: MarketPanel
    rrg: MarketPanel
    industry_rrg: MarketPanel
    accumulation: MarketPanel
    trend: MarketPanel
    soft_bottoming: MarketPanel
    portfolio: MarketPanel
    speculative: MarketPanel
    evidence: MarketPanel
    contrarian: MarketPanel

    @classmethod
    def empty(cls, *, as_of: str) -> "DashboardPayload":
        preview = "Preview until market refresh has live data."
        return cls(
            as_of=as_of,
            briefing=MarketPanel(
                status="preview",
                data=Briefing(
                    headline="Market briefing has not run yet.",
                    summary="Run a market refresh to compute live facts.",
                    changed=[],
                    attention=[],
                    vix=0.0,
                    breadth_pct=0.0,
                ),
                note=preview,
            ),
            regime=MarketPanel(
                status="preview",
                data=Regime(
                    current="chop",
                    scale=[
                        {"name": "risk-off", "active": False},
                        {"name": "chop", "active": True},
                        {"name": "risk-on", "active": False},
                        {"name": "event-risk", "active": False},
                    ],
                ),
                note=preview,
            ),
            macro=MarketPanel(status="preview", data=[], note=preview),
            rrg=MarketPanel(status="preview", data=[], note=preview),
            industry_rrg=MarketPanel(status="preview", data=[], note=preview),
            accumulation=MarketPanel(status="preview", data=[], note=preview),
            trend=MarketPanel(status="preview", data=[], note=preview),
            soft_bottoming=MarketPanel(status="preview", data=[], note=preview),
            portfolio=MarketPanel(status="preview", data=Portfolio("$0", "$0 · 0.0%", "flat", []), note=preview),
            speculative=MarketPanel(status="preview", data=[], note=preview),
            evidence=MarketPanel(status="preview", data=[], note=preview),
            contrarian=MarketPanel(status="preview", data=[], note=preview),
        )

    def to_wire(self) -> dict[str, Any]:
        return _to_wire(self)


@dataclass
class InsightBaseRate:
    pattern: str
    horizon_weeks: int
    pct_up: float
    median_fwd: float
    n: int
    headline: str


@dataclass
class InsightComponent:
    label: str
    met: bool


@dataclass
class TickerInsight:
    soft_bottoming: bool
    score: float
    components: list[InsightComponent]
    base_rate: InsightBaseRate | None


@dataclass
class TickerIntelligence:
    """Compact, agent-facing summary of a symbol's condition.

    This reshapes FeatureSet for reasoning instead of burying it under raw OHLCV.
    """

    as_of: str | None
    asset_role: str
    trend: dict[str, Any]
    momentum: dict[str, Any]
    returns: dict[str, Any]
    drawdown: dict[str, Any]
    volatility: dict[str, Any]
    relative_strength: dict[str, Any]
    structure: dict[str, Any]
    data_quality: dict[str, Any]
    rotation: dict[str, Any] | None = None
    portfolio: dict[str, Any] | None = None
    exposure: dict[str, Any] | None = None
    thesis: dict[str, Any] | None = None


@dataclass(frozen=True)
class TickerQuote:
    """Latest cached daily bar, explicitly distinguished from a live quote."""

    price: float | None
    change_pct: float | None
    bar_time: int | None
    comparison: Literal["previous_daily_bar"]
    price_basis: Literal["split_adjusted"]


@dataclass(frozen=True)
class ChartSeriesRow:
    symbol: str
    bars: list[MarketBar]


@dataclass(frozen=True)
class ChartSeriesPayload:
    """Small batch of like-for-like traded-price histories for chart comparison."""

    as_of: str
    timeframe: Literal["daily", "weekly", "monthly"]
    price_basis: Literal["split_adjusted"]
    series: list[ChartSeriesRow]

    def to_wire(self) -> dict[str, Any]:
        return _to_wire(self)


@dataclass
class CompareRow:
    symbol: str
    name: str
    last: float | None
    change_pct: float | None
    r_1w_pct: float | None
    r_4w_pct: float | None
    r_13w_pct: float | None
    r_26w_pct: float | None
    r_52w_pct: float | None
    r_ytd_pct: float | None
    vol_13w_pct: float | None
    drawdown_52w_pct: float | None
    rsi_14: float | None
    ma_stack: str
    long_trend: str
    rank_13w: int | None = None


@dataclass
class CompareResult:
    as_of: str
    rows: list[CompareRow]

    def to_wire(self) -> dict[str, Any]:
        return _to_wire(self)


@dataclass
class TickerDetailPayload:
    symbol: str
    name: str
    as_of: str
    quote: TickerQuote
    series: dict[str, list[MarketBar]]
    verdict: list[VerdictRow]
    signals: list[SignalRow]
    evidence: list[EvidenceItem]
    events: list[ChartEvent]
    kill: str
    insight: TickerInsight | None = None
    intelligence: TickerIntelligence | None = None
    # {market_cap, year_high, year_low, avg_volume_3m} from data_sources.fetch_key_stats;
    # None when yfinance can't resolve them (indexes, some ETFs).
    stats: dict[str, Any] | None = None

    def to_wire(self) -> dict[str, Any]:
        return _to_wire(self)


@dataclass
class MorningBriefPayload:
    """The overnight delta — what changed between the previous sweep and this one.

    List entries are wire-shaped dicts (snake_case keys; ``to_wire`` camelCases them):
    signal_flips {symbol, kind, detail, tone} · rrg_shifts {symbol, name, from_quadrant,
    to_quadrant, tone} · movers {symbol, name, last, change_pct, tone}.
    """

    brief_date: str  # YYYY-MM-DD, operator-local
    generated_at: str
    headline: str
    new_evidence: list[EvidenceItem]
    signal_flips: list[dict[str, Any]]
    rrg_shifts: list[dict[str, Any]]
    movers: list[dict[str, Any]]
    movers_label: str  # "today at the open" vs "last session" — freshness is self-evidencing
    regime_shift: dict[str, Any] | None
    portfolio_note: str | None
    previous_as_of: str | None
    first_sweep: bool = False
    note: str | None = None

    def to_wire(self) -> dict[str, Any]:
        return _to_wire(self)


@dataclass
class TickerEvidencePayload:
    symbol: str
    evidence: list[EvidenceItem]
    events: list[ChartEvent]
    as_of: str
    refreshed: bool
    # Net insider Form 4 activity per trailing window: {"d30": {...}, "d90": {...}} —
    # each {days, buys, sells, net_shares, net_value, tone}. None when no Form 4 data.
    insider_net: dict[str, Any] | None = None
    # Typed acquisition failures distinguish unavailable SEC evidence from no filings.
    warnings: list[str] = field(default_factory=list)

    def to_wire(self) -> dict[str, Any]:
        return _to_wire(self)


@dataclass(frozen=True)
class PriceSignals:
    below_ma: str
    drawdown: str
    rsi: str
    confluence: int
    trend_direction: Direction
    trend_note: str
    confirmed: bool
    relative_strength: str = "n/a"
    mama_regime: str = "n/a"
    atr_move: str = "n/a"
    volume_vs_avg: str = "n/a"
    thin_history: bool = False


def _camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _to_wire(value: Any) -> Any:
    if is_dataclass(value):
        raw = asdict(value)
        return { _camel(key): _to_wire(item) for key, item in raw.items() if item is not None }
    if isinstance(value, list):
        return [_to_wire(item) for item in value]
    if isinstance(value, tuple):
        return [_to_wire(item) for item in value]
    if isinstance(value, dict):
        return {_camel(str(key)): _to_wire(item) for key, item in value.items() if item is not None}
    return value
