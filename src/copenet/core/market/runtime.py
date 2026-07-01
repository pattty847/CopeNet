"""Market Monitor orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from copenet._paths import default_sessions_dir

from .benchmark import benchmark_verdict
from .data_sources import fetch_ohlcv, frame_to_bars, macro_item_from_frame
from .edgar import chart_events_from_evidence, fetch_evidence
from .models import (
    AccumulationRow,
    DashboardPayload,
    EvidenceItem,
    InsightBaseRate,
    InsightComponent,
    MarketPanel,
    Portfolio,
    PortfolioPosition,
    SignalRow,
    SoftBottomItem,
    SpecPosition,
    TickerDetailPayload,
    TickerInsight,
)
from .base_rates import load_base_rate
from .fact_packets import market_fact_packet, ticker_fact_packet
from .features import compute_features
from .interpretation import generate_market_read, generate_ticker_read
from .signals import compute_price_signals, compute_rrg_tail
from .webull.config import include_portfolio_context_enabled
from .webull.context_pack import build_portfolio_context_pack
from .webull.sync import load_snapshot as load_webull_snapshot
from .store import MarketStore
from .synthesis import synthesize_briefing
from .universe import MACRO_SYMBOLS, PORTFOLIO_BASIS, SECTOR_SYMBOLS, UNIVERSE, find_asset


class MarketRuntime:
    def __init__(self, store: MarketStore | None = None) -> None:
        self.store = store or MarketStore(default_market_dir())

    def dashboard(self) -> DashboardPayload:
        return self.store.load_dashboard()

    def universe(self) -> list[dict[str, Any]]:
        return [asset.to_wire() for asset in UNIVERSE]

    def ticker(self, symbol: str) -> TickerDetailPayload:
        normalized = symbol.strip().upper()
        asset = find_asset(normalized)
        name = asset.name if asset else normalized
        # Deep multi-timeframe history for the chart, fetched on-demand. The dashboard refresh only
        # persists weekly(3y)/daily(6mo) for signals, so pull richer D/W/M here for the candle view;
        # fall back to the stored bars if a live fetch fails.
        def _chart_bars(interval: str, period: str, cache_key: str) -> list:
            try:
                bars = frame_to_bars(fetch_ohlcv(normalized, interval=interval, period=period))
                if bars:
                    return bars
            except Exception:
                pass
            return self.store.load_bars(normalized, cache_key)

        daily = _chart_bars("1d", "2y", "daily")
        weekly = _chart_bars("1wk", "5y", "weekly")
        monthly = _chart_bars("1mo", "10y", "monthly")
        weekly_frame = _bars_to_frame(weekly)
        signals = self.store.load_signals(normalized)
        evidence = [item for item in _evidence_from_dashboard(self.store.load_dashboard_wire()) if item.symbol == normalized]
        last = weekly[-1].c if weekly else 0.0
        previous = weekly[-2].c if len(weekly) > 1 else last
        change_pct = ((last / previous) - 1) * 100 if previous else 0.0
        if not signals and not weekly_frame.empty:
            computed = compute_price_signals(weekly_frame)
            signals = computed.__dict__
        voo_frame = _bars_to_frame(self.store.load_bars("VOO", "weekly"))
        verdict = benchmark_verdict(
            weekly_frame,
            {
                "VOO": voo_frame,
                "XLK": _bars_to_frame(self.store.load_bars("XLK", "weekly")),
            },
        )
        insight = _build_insight(compute_features(weekly_frame, voo_frame, symbol=normalized))
        return TickerDetailPayload(
            symbol=normalized,
            name=name,
            last=f"${last:,.2f}" if last else "n/a",
            change=f"{change_pct:+.2f}%" if last else "n/a",
            tone="up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
            series={"daily": daily, "weekly": weekly, "monthly": monthly},
            verdict=verdict,
            signals=_signal_rows(signals),
            evidence=evidence,
            events=chart_events_from_evidence(evidence),
            kill="This read is wrong if price, volume, and benchmark-relative behavior stop confirming the thesis.",
            insight=insight,
        )

    async def interpret(self, provider, *, target: str = "market", model: str = "gpt-5.5") -> dict:
        """Run the LLM interpretation lane (Insight Engine Phase D) and persist the read.

        target='market' → whole-market read from the stored dashboard wire.
        target=<SYMBOL> → per-asset read from the stored weekly bars' FeatureSet.
        The provider is injected (openai-codex); the call is one-shot, no chat session.
        """
        generated_at = _now_iso()
        sb_rate = load_base_rate("soft_bottoming", 8)
        if target == "market":
            packet = market_fact_packet(self.store.load_dashboard_wire(), sb_rate)
            # Opt-in only (INCLUDE_WEBULL_PORTFOLIO_CONTEXT=true): append the sanitized account
            # context pack. Built from whitelisted snapshot fields — no credentials/tokens exist
            # anywhere in its inputs.
            if include_portfolio_context_enabled():
                snapshot = load_webull_snapshot()
                if snapshot:
                    packet = f"{packet}\n\n{build_portfolio_context_pack(snapshot)}"
            read = await generate_market_read(provider, packet, model=model, generated_at=generated_at)
            wire = read.to_wire()
            self.store.save_market_read(wire)
            return wire

        symbol = target.strip().upper()
        asset = find_asset(symbol)
        weekly_frame = _bars_to_frame(self.store.load_bars(symbol, "weekly"))
        voo_frame = _bars_to_frame(self.store.load_bars("VOO", "weekly"))
        fs = compute_features(weekly_frame, voo_frame, symbol=symbol)
        verdict = benchmark_verdict(weekly_frame, {"VOO": voo_frame})
        evidence = [item for item in _evidence_from_dashboard(self.store.load_dashboard_wire()) if item.symbol == symbol]
        packet = ticker_fact_packet(
            fs,
            name=asset.name if asset else symbol,
            base_rate=sb_rate,
            verdict=[{"bench": v.bench, "label": v.label} for v in verdict],
            evidence=[{"type": e.type, "headline": e.headline, "source": e.source} for e in evidence],
        )
        if include_portfolio_context_enabled():
            snapshot = load_webull_snapshot()
            held = next((p for p in (snapshot or {}).get("positions", []) if p.get("symbol") == symbol), None)
            if held:
                packet += (
                    f"\nOPERATOR POSITION (Webull): holds {held.get('quantity')} sh @ avg {held.get('avg_cost')}"
                    f" · unrealized P&L {held.get('unrealized_pl_pct')}% · {held.get('allocation_pct')}% of portfolio."
                )
        read = await generate_ticker_read(provider, packet, model=model, generated_at=generated_at)
        wire = read.to_wire()
        wire["symbol"] = symbol
        self.store.save_ticker_read(symbol, wire)
        return wire

    def refresh(self, *, scope: str = "all") -> DashboardPayload:
        weekly: dict[str, pd.DataFrame] = {}
        daily: dict[str, pd.DataFrame] = {}
        symbols = _symbols_for_scope(scope)
        for symbol in symbols:
            try:
                weekly[symbol] = fetch_ohlcv(symbol, interval="1wk", period="3y")
                daily[symbol] = fetch_ohlcv(symbol, interval="1d", period="6mo")
            except Exception:
                weekly[symbol] = pd.DataFrame()
                daily[symbol] = pd.DataFrame()
            self.store.save_bars(symbol, "weekly", frame_to_bars(weekly[symbol]))
            self.store.save_bars(symbol, "daily", frame_to_bars(daily[symbol]))

        dashboard = self._assemble_dashboard(weekly=weekly, daily=daily)
        self.store.save_dashboard(dashboard)
        return dashboard

    def _assemble_dashboard(self, *, weekly: dict[str, pd.DataFrame], daily: dict[str, pd.DataFrame]) -> DashboardPayload:
        as_of = _as_of_label()
        dashboard = DashboardPayload.empty(as_of=as_of)
        macro = _macro_items(weekly)
        if macro:
            dashboard.macro = MarketPanel(status="live", data=macro, as_of=_now_iso())

        benchmark = weekly.get("VOO", pd.DataFrame())
        accumulation: list[AccumulationRow] = []
        trend: list[Any] = []
        live_signal_symbols = [asset.symbol for asset in UNIVERSE if asset.role in {"holding", "watch", "spec"}]
        soft_bottoms: list[SoftBottomItem] = []
        above_trend = 0
        total_trend = 0
        for asset in UNIVERSE:
            frame = weekly.get(asset.symbol, pd.DataFrame())
            if frame.empty:
                continue
            signals = compute_price_signals(frame, benchmark=benchmark)
            self.store.save_signals(asset.symbol, signals.__dict__)
            if asset.symbol in live_signal_symbols:
                total_trend += 1
                fs = compute_features(frame, benchmark, symbol=asset.symbol)
                if fs.soft_bottoming:
                    soft_bottoms.append(
                        SoftBottomItem(
                            symbol=asset.symbol,
                            name=asset.name,
                            score=fs.soft_bottoming_score,
                            drawdown=signals.drawdown,
                            rsi=signals.rsi,
                        )
                    )
                above_trend += 1 if signals.trend_direction == "up" else 0
                if signals.confluence > 0 or signals.drawdown.startswith("-"):
                    accumulation.append(
                        AccumulationRow(
                            symbol=asset.symbol,
                            name=asset.name,
                            below_ma=signals.below_ma,
                            drawdown=signals.drawdown,
                            rsi=signals.rsi,
                            confluence=signals.confluence,
                            why=signals.trend_note,
                        )
                    )
                trend.append(
                    {
                        "symbol": asset.symbol,
                        "direction": signals.trend_direction,
                        "note": signals.trend_note,
                        "when": as_of,
                        "confirmed": signals.confirmed,
                    }
                )
        if accumulation:
            dashboard.accumulation = MarketPanel(status="live", data=accumulation[:12], as_of=_now_iso())
        if trend:
            dashboard.trend = MarketPanel(status="live", data=trend[:12], as_of=_now_iso())
        soft_bottoms.sort(key=lambda s: s.score, reverse=True)
        _sb_rate = load_base_rate("soft_bottoming", 8)
        dashboard.soft_bottoming = MarketPanel(
            status="live",
            data=soft_bottoms,
            as_of=_now_iso(),
            note=_sb_rate.headline() if _sb_rate else "base rate calibrating",
        )

        rrg = [
            compute_rrg_tail(asset.symbol, asset.name, weekly.get(asset.symbol, pd.DataFrame()), benchmark)
            for asset in UNIVERSE
            if asset.symbol in SECTOR_SYMBOLS
        ]
        rrg = [sector for sector in rrg if sector.tail]
        if rrg:
            dashboard.rrg = MarketPanel(status="live", data=rrg, as_of=_now_iso())

        webull_snapshot = load_webull_snapshot()
        if webull_snapshot and webull_snapshot.get("positions"):
            portfolio = _portfolio_panel_from_webull(webull_snapshot)
            note = f"account data: Webull · synced {webull_snapshot.get('synced_at', 'unknown')}"
        else:
            portfolio = _portfolio_panel(weekly)
            note = "account data: configured cost basis · prices: yfinance"
        if portfolio.positions:
            dashboard.portfolio = MarketPanel(status="live", data=portfolio, as_of=_now_iso(), note=note)

        speculative = _speculative_panel(weekly)
        if speculative:
            dashboard.speculative = MarketPanel(status="live", data=speculative, as_of=_now_iso())

        evidence = fetch_evidence([asset.symbol for asset in UNIVERSE if asset.role in {"holding", "watch", "spec"}])
        dashboard.evidence = MarketPanel(status="live", data=evidence, as_of=_now_iso())

        breadth_pct = (above_trend / total_trend * 100) if total_trend else 0.0
        briefing, contrarian = synthesize_briefing(macro=macro, evidence=evidence, breadth_pct=breadth_pct)
        dashboard.briefing = MarketPanel(status="live", data=briefing, as_of=_now_iso())
        dashboard.contrarian = MarketPanel(status="live", data=contrarian, as_of=_now_iso())
        dashboard.regime = MarketPanel(
            status="live",
            data={
                "current": "risk-on" if breadth_pct >= 55 else "risk-off" if breadth_pct < 40 else "chop",
                "scale": [
                    {"name": "risk-off", "active": breadth_pct < 40},
                    {"name": "chop", "active": 40 <= breadth_pct < 55},
                    {"name": "risk-on", "active": breadth_pct >= 55},
                    {"name": "event-risk", "active": False},
                ],
            },
            as_of=_now_iso(),
        )
        return dashboard


def default_market_dir() -> Path:
    return default_sessions_dir().parent / "market"


def _symbols_for_scope(scope: str) -> list[str]:
    if scope == "macro":
        return list(MACRO_SYMBOLS) + ["VOO"]
    if scope in {"signals", "all", "edgar"}:
        return [asset.symbol for asset in UNIVERSE]
    return [asset.symbol for asset in UNIVERSE]


def _macro_items(frames: dict[str, pd.DataFrame]) -> list:
    items = []
    for symbol in MACRO_SYMBOLS:
        item = macro_item_from_frame(symbol, frames.get(symbol, pd.DataFrame()))
        if item is not None:
            items.append(item)
    return items


def _build_insight(fs) -> TickerInsight:
    """Attach the soft_bottoming flag + decomposed components + the calibrated base rate (read by key
    from the cached artifact). The base rate is only surfaced when the pattern is currently firing."""
    base_rate = None
    if fs.soft_bottoming:
        br = load_base_rate("soft_bottoming", 8)
        if br is not None:
            base_rate = InsightBaseRate(
                pattern="soft_bottoming",
                horizon_weeks=br.horizon_weeks,
                pct_up=br.pct_up,
                median_fwd=br.median_fwd,
                n=br.n,
                headline=br.headline(),
            )
    components = [
        InsightComponent("Lower lows stopped", fs.sb_lower_lows_stopped),
        InsightComponent("Higher low formed", fs.sb_higher_low),
        InsightComponent("Reclaimed short MA", fs.sb_ma_reclaim),
        InsightComponent("Drawdown stabilized", fs.sb_drawdown_stabilized),
        InsightComponent("Relative strength improving", fs.sb_rs_improving),
        InsightComponent("Decline volume drying", fs.sb_volume_drying),
        InsightComponent("Momentum divergence", fs.sb_momentum_divergence),
    ]
    return TickerInsight(
        soft_bottoming=fs.soft_bottoming,
        score=fs.soft_bottoming_score,
        components=components,
        base_rate=base_rate,
    )


def _portfolio_panel_from_webull(snapshot: dict) -> Portfolio:
    """Build the portfolio panel from the synced (sanitized) Webull snapshot — real broker data."""
    positions: list[PortfolioPosition] = []
    total = 0.0
    cost = 0.0
    for row in snapshot.get("positions", []):
        if not isinstance(row, dict) or not row.get("symbol"):
            continue
        quantity = float(row.get("quantity") or 0)
        avg_cost = float(row.get("avg_cost") or 0)
        last = row.get("last_price")
        market_value = row.get("market_value")
        pnl_pct = row.get("unrealized_pl_pct")
        if market_value is not None:
            total += float(market_value)
        cost += quantity * avg_cost
        positions.append(
            PortfolioPosition(
                symbol=str(row["symbol"]),
                shares=quantity,
                avg_cost=avg_cost,
                last=f"${float(last):,.2f}" if last is not None else "n/a",
                pnl_pct=f"{float(pnl_pct):+.1f}%" if pnl_pct is not None else "n/a",
                tone="up" if (pnl_pct or 0) > 0 else "down" if (pnl_pct or 0) < 0 else "flat",
                nudge="add zone" if (pnl_pct or 0) < -10 else None,
            )
        )
    equity = snapshot.get("total_equity")
    headline_total = float(equity) if equity is not None else total
    pnl = total - cost
    pnl_pct_total = (pnl / cost * 100) if cost else 0.0
    return Portfolio(
        total=f"${headline_total:,.0f}",
        pnl=f"{pnl:+,.0f} · {pnl_pct_total:+.1f}%",
        pnl_tone="up" if pnl > 0 else "down" if pnl < 0 else "flat",
        positions=positions,
    )


def _portfolio_panel(frames: dict[str, pd.DataFrame]) -> Portfolio:
    positions: list[PortfolioPosition] = []
    total = 0.0
    cost = 0.0
    for symbol, basis in PORTFOLIO_BASIS.items():
        frame = frames.get(symbol, pd.DataFrame())
        if frame.empty:
            continue
        shares = float(basis["shares"])
        avg_cost = float(basis["avg_cost"])
        last = float(frame["close"].dropna().iloc[-1])
        market_value = shares * last
        cost_value = shares * avg_cost
        total += market_value
        cost += cost_value
        pnl_pct = ((last / avg_cost) - 1) * 100 if avg_cost else 0.0
        positions.append(
            PortfolioPosition(
                symbol=symbol,
                shares=shares,
                avg_cost=avg_cost,
                last=f"${last:,.2f}",
                pnl_pct=f"{pnl_pct:+.1f}%",
                tone="up" if pnl_pct > 0 else "down" if pnl_pct < 0 else "flat",
                nudge="add zone" if pnl_pct < -10 else None,
            )
        )
    pnl = total - cost
    pnl_pct = (pnl / cost * 100) if cost else 0.0
    return Portfolio(total=f"${total:,.0f}", pnl=f"{pnl:+,.0f} · {pnl_pct:+.1f}%", pnl_tone="up" if pnl > 0 else "down" if pnl < 0 else "flat", positions=positions)


def _speculative_panel(frames: dict[str, pd.DataFrame]) -> list[SpecPosition]:
    rows: list[SpecPosition] = []
    for symbol in ("SOFI", "SLI"):
        frame = frames.get(symbol, pd.DataFrame())
        if frame.empty:
            continue
        close = frame["close"].astype(float).dropna()
        if close.empty:
            continue
        high = float(close.tail(min(len(close), 52)).max())
        last = float(close.iloc[-1])
        drawdown = ((last / high) - 1) * 100 if high else 0.0
        rows.append(
            SpecPosition(
                symbol=symbol,
                pnl_pct=f"{drawdown:+.1f}%",
                tone="down" if drawdown < 0 else "up",
                thesis="Spec lane: small-size position with defined invalidation.",
                entry=f"${last:,.2f}",
                target="risk-adjusted outperformance vs VOO/sector ETF",
                invalidation="weekly close below prior support plus lagging benchmark verdict",
            )
        )
    return rows


def _signal_rows(signals: dict[str, Any]) -> list[SignalRow]:
    mapping = {
        "below_ma": "Below 40W MA",
        "drawdown": "Drawdown",
        "rsi": "RSI",
        "relative_strength": "Relative strength",
        "mama_regime": "MAMA/FAMA",
        "atr_move": "ATR move",
        "volume_vs_avg": "Volume",
    }
    rows = []
    for key, label in mapping.items():
        value = str(signals.get(key) or signals.get(_camel(key)) or "n/a")
        rows.append(SignalRow(key=label, value=value, tone=_tone_from_value(value)))
    return rows


def _evidence_from_dashboard(payload: dict[str, Any]) -> list[EvidenceItem]:
    panel = payload.get("evidence") if isinstance(payload, dict) else None
    rows = panel.get("data") if isinstance(panel, dict) else None
    evidence = []
    if not isinstance(rows, list):
        return evidence
    for row in rows:
        if isinstance(row, dict):
            evidence.append(
                EvidenceItem(
                    type=row.get("type") or "News",
                    symbol=row.get("symbol") or "",
                    headline=row.get("headline") or "",
                    source=row.get("source") or "",
                    tone=row.get("tone") or "flat",
                    url=row.get("url"),
                )
            )
    return evidence


def _bars_to_frame(bars: list) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    return pd.DataFrame(
        [
            {
                "date": datetime.fromtimestamp(bar.t, tz=timezone.utc),
                "open": bar.o,
                "high": bar.h,
                "low": bar.l,
                "close": bar.c,
                "volume": bar.v,
            }
            for bar in bars
        ]
    )


def _tone_from_value(value: str) -> str:
    if value.startswith("+"):
        return "up"
    if value.startswith("-"):
        return "down"
    return "flat"


def _camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_of_label() -> str:
    return f"as of {datetime.now().strftime('%a %-I:%M%p ET')} market refresh"
