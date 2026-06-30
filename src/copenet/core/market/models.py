"""DTOs for the Market Monitor wire contract.

Internal field names stay Pythonic. ``to_wire`` emits the camelCase JSON shape
from docs/plans/MARKET_MONITOR_BUILD_BLUEPRINT.md §2.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Literal


Tone = Literal["up", "down", "flat"]
Direction = Literal["up", "down"]
PanelStatus = Literal["live", "preview", "stale", "error"]
AssetRole = Literal["index", "holding", "watch", "trend", "spec", "sector", "macro"]


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
    type: Literal["Insider", "8-K", "News"]
    symbol: str
    headline: str
    source: str
    tone: Tone
    url: str | None = None


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
    kind: Literal["insider", "8-K"]
    glyph: str


@dataclass
class DashboardPayload:
    as_of: str
    briefing: MarketPanel
    regime: MarketPanel
    macro: MarketPanel
    rrg: MarketPanel
    accumulation: MarketPanel
    trend: MarketPanel
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
            accumulation=MarketPanel(status="preview", data=[], note=preview),
            trend=MarketPanel(status="preview", data=[], note=preview),
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
class TickerDetailPayload:
    symbol: str
    name: str
    last: str
    change: str
    tone: Tone
    series: dict[str, list[MarketBar]]
    verdict: list[VerdictRow]
    signals: list[SignalRow]
    evidence: list[EvidenceItem]
    events: list[ChartEvent]
    kill: str
    insight: TickerInsight | None = None

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
