"""Market Monitor orchestration."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from copenet._paths import default_sessions_dir
from copenet.core.tools.handlers.web import run_web_search

from .benchmark import benchmark_verdict
from .data_sources import fetch_fund_profile, fetch_key_stats, fetch_ohlcv, frame_to_bars, macro_item_from_frame
from .edgar import chart_events_from_evidence, fetch_evidence, fetch_fundamentals
from .models import (
    AccumulationRow,
    CompareResult,
    CompareRow,
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
    TickerIntelligence,
)
from .base_rates import load_base_rate
from .fact_packets import market_fact_packet, ticker_fact_packet
from .ledger import record_market_read_claims, record_ticker_read_claim, track_record_line
from .features import FeatureSet, compute_features
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

    def _weekly_frame(self, symbol: str) -> pd.DataFrame:
        """Live weekly fetch with a store-bars fallback — the same freshness pattern as the
        chart bars, so a benchmark series is never a stale cache sitting next to a live one."""
        try:
            frame = fetch_ohlcv(symbol, interval="1wk", period="5y", auto_adjust=True)
            if not frame.empty:
                return frame
        except Exception:
            pass
        return _bars_to_frame(self.store.load_bars(symbol, "weekly"))

    def ticker(self, symbol: str, *, compare: list[str] | None = None) -> TickerDetailPayload:
        normalized = symbol.strip().upper()
        asset = find_asset(normalized)
        name = asset.name if asset else normalized
        # Deep multi-timeframe history for the chart, fetched on-demand. The dashboard refresh only
        # persists weekly(3y)/daily(6mo) for signals, so pull richer D/W/M here for the candle view;
        # fall back to the stored bars if a live fetch fails.
        def _chart_bars(interval: str, period: str, cache_key: str) -> list:
            try:
                bars = frame_to_bars(fetch_ohlcv(normalized, interval=interval, period=period, auto_adjust=True))
                if bars:
                    return bars
            except Exception:
                pass
            return self.store.load_bars(normalized, cache_key)

        fetched_at = _now_iso()
        daily = _chart_bars("1d", "2y", "daily")
        weekly = _chart_bars("1wk", "5y", "weekly")
        monthly = _chart_bars("1mo", "10y", "monthly")
        weekly_frame = _bars_to_frame(weekly)
        evidence = [item for item in _evidence_from_dashboard(self.store.load_dashboard_wire()) if item.symbol == normalized]
        last = weekly[-1].c if weekly else 0.0
        previous = weekly[-2].c if len(weekly) > 1 else last
        change_pct = ((last / previous) - 1) * 100 if previous else 0.0
        voo_frame = self._weekly_frame("VOO")
        qqq_frame = self._weekly_frame("QQQ")
        # Always compute signals live from the same weekly_frame used below — the cached
        # per-symbol signals (written by the last dashboard refresh) can be stale enough
        # to disagree with the live-fetched intelligence packet (e.g. drawdown %) in the
        # same response, which is confusing rather than just imprecise.
        signals = compute_price_signals(weekly_frame, benchmark=voo_frame).__dict__ if not weekly_frame.empty else {}
        # Default benchmarks are the broad market/growth read (VOO/XLK/QQQ); `compare` lets the
        # caller add specific symbols (a sector ETF, a direct competitor) on top — it never
        # replaces the defaults, so the human-facing Market page's verdict table is unaffected.
        benchmark_frames = {"VOO": voo_frame, "XLK": self._weekly_frame("XLK"), "QQQ": qqq_frame}
        for extra in compare or []:
            extra_symbol = extra.strip().upper()
            if extra_symbol and extra_symbol not in benchmark_frames:
                benchmark_frames[extra_symbol] = self._weekly_frame(extra_symbol)
        benchmark_frames.pop(normalized, None)  # never benchmark a symbol against itself
        verdict = benchmark_verdict(weekly_frame, benchmark_frames)
        fs = compute_features(weekly_frame, voo_frame, symbol=normalized, as_of=fetched_at)
        insight = _build_insight(fs)
        rotation = compute_rrg_tail(normalized, name, weekly_frame, voo_frame)
        intelligence = _build_intelligence(
            fs,
            role=asset.role if asset else "unknown",
            verdict=verdict,
            rotation=rotation if rotation.tail else None,
            portfolio=_portfolio_position_for_symbol(normalized, last=last),
            exposure=fetch_fund_profile(normalized),
        )
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
            intelligence=intelligence,
            stats=fetch_key_stats(normalized),
        )

    def compare(self, symbols: list[str]) -> CompareResult:
        """Side-by-side comparable stats for an arbitrary list of symbols — two names head-to-head
        or a batch. No pairwise verdicts or rankings-as-conclusions: just the same numbers for each
        symbol so the caller (model or human) draws its own comparison."""
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in symbols:
            sym = raw.strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                normalized.append(sym)
        as_of = _now_iso()
        rows: list[CompareRow] = []
        for sym in normalized:
            asset = find_asset(sym)
            name = asset.name if asset else sym
            frame = self._weekly_frame(sym)
            if frame.empty:
                rows.append(
                    CompareRow(
                        symbol=sym, name=name, last=None, change_pct=None,
                        r_1w_pct=None, r_4w_pct=None, r_13w_pct=None, r_26w_pct=None, r_52w_pct=None, r_ytd_pct=None,
                        vol_13w_pct=None, drawdown_52w_pct=None, rsi_14=None, ma_stack="n/a", long_trend="n/a",
                    )
                )
                continue
            close = frame["close"].astype(float).dropna()
            last_price = float(close.iloc[-1]) if len(close) else None
            change = ((close.iloc[-1] / close.iloc[-2]) - 1) * 100 if len(close) > 1 else None
            fs = compute_features(frame, None, symbol=sym, as_of=as_of)
            rows.append(
                CompareRow(
                    symbol=sym,
                    name=name,
                    last=last_price,
                    change_pct=round(change, 2) if change is not None else None,
                    r_1w_pct=fs.r_1w,
                    r_4w_pct=fs.r_4w,
                    r_13w_pct=fs.r_13w,
                    r_26w_pct=fs.r_26w,
                    r_52w_pct=fs.r_52w,
                    r_ytd_pct=fs.r_ytd,
                    vol_13w_pct=fs.vol_13w,
                    drawdown_52w_pct=fs.drawdown_pct,
                    rsi_14=fs.rsi_14,
                    ma_stack=fs.ma_stack,
                    long_trend=fs.long_trend,
                )
            )
        ranked = sorted((r for r in rows if r.r_13w_pct is not None), key=lambda r: r.r_13w_pct, reverse=True)
        for position, row in enumerate(ranked, start=1):
            row.rank_13w = position
        return CompareResult(as_of=as_of, rows=rows)

    async def interpret(self, provider, *, target: str = "market", model: str = "gpt-5.5") -> dict:
        """Run the LLM interpretation lane (Insight Engine Phase D) and persist the read.

        target='market' → whole-market read from the stored dashboard wire.
        target=<SYMBOL> → per-asset read from the stored weekly bars' FeatureSet.
        The provider is injected (openai-codex); the call is one-shot, no chat session.
        """
        generated_at = _now_iso()
        sb_rate = load_base_rate("soft_bottoming", 8)
        if target == "market":
            # Include the overnight delta only when it's today's — a week-old brief in the
            # packet would read as fresh "overnight changes" and mislead the model.
            overnight = self.store.load_morning_brief()
            if overnight and overnight.get("briefDate") != datetime.now().strftime("%Y-%m-%d"):
                overnight = None
            packet = market_fact_packet(self.store.load_dashboard_wire(), sb_rate, overnight=overnight)
            track_record = track_record_line(self.store)
            if track_record:
                packet = f"{packet}\n{track_record}"
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
            try:
                record_market_read_claims(self.store, wire)
            except Exception:
                logging.warning("forward ledger: failed to record market read claims", exc_info=True)
            return wire

        symbol = target.strip().upper()
        asset = find_asset(symbol)
        # Multi-year structure features need the full 5y weekly history; fetch live with a
        # stored-bars fallback (same pattern as the chart path in ticker()).
        try:
            weekly_frame = fetch_ohlcv(symbol, interval="1wk", period="5y", auto_adjust=True)
            if weekly_frame.empty:
                weekly_frame = _bars_to_frame(self.store.load_bars(symbol, "weekly"))
        except Exception:
            weekly_frame = _bars_to_frame(self.store.load_bars(symbol, "weekly"))
        voo_frame = _bars_to_frame(self.store.load_bars("VOO", "weekly"))
        fs = compute_features(weekly_frame, voo_frame, symbol=symbol)
        verdict = benchmark_verdict(weekly_frame, {"VOO": voo_frame})
        evidence = [item for item in _evidence_from_dashboard(self.store.load_dashboard_wire()) if item.symbol == symbol]
        fundamentals_warning = None
        try:
            fundamentals = await fetch_fundamentals(symbol)
        except Exception as exc:
            try:
                from copetech_sec import SecRequestError
            except ImportError:
                raise
            if not isinstance(exc, SecRequestError):
                raise
            logging.warning("SEC fundamentals unavailable for %s: %s", symbol, exc)
            fundamentals = None
            fundamentals_warning = type(exc).__name__
        if fundamentals is not None:
            fundamentals = {**fundamentals, **_trailing_eps_and_pe(fundamentals, weekly_frame)}
        query_name = asset.name if asset else symbol
        try:
            news_results, news_source = await run_web_search(f"{query_name} {symbol} stock news", limit=5, kind="news")
        except Exception:
            news_results, news_source = [], "unavailable"
        packet = ticker_fact_packet(
            fs,
            name=asset.name if asset else symbol,
            base_rate=sb_rate,
            verdict=[{"bench": v.bench, "label": v.label} for v in verdict],
            evidence=[{"type": e.type, "headline": e.headline, "source": e.source} for e in evidence],
            fundamentals=fundamentals,
            news=news_results,
            news_source=news_source,
        )
        if fundamentals_warning:
            packet += (
                "\nSEC FUNDAMENTALS STATUS: unavailable "
                f"({fundamentals_warning}); do not infer zero values."
            )
        if include_portfolio_context_enabled():
            snapshot = load_webull_snapshot()
            held = next((p for p in (snapshot or {}).get("positions", []) if p.get("symbol") == symbol), None)
            if held:
                packet += (
                    f"\nOPERATOR POSITION (Webull): holds {held.get('quantity')} sh @ avg {held.get('avg_cost')}"
                    f" · unrealized P&L {held.get('unrealized_pl_pct')}% · {held.get('allocation_pct')}% of portfolio."
                )
        track_record = track_record_line(self.store)
        if track_record:
            packet = f"{packet}\n{track_record}"
        read = await generate_ticker_read(provider, packet, model=model, generated_at=generated_at)
        wire = read.to_wire()
        wire["symbol"] = symbol
        self.store.save_ticker_read(symbol, wire)
        try:
            record_ticker_read_claim(self.store, symbol, wire)
        except Exception:
            logging.warning("forward ledger: failed to record ticker read claim", exc_info=True)
        return wire

    def refresh(self, *, scope: str = "all") -> DashboardPayload:
        weekly: dict[str, pd.DataFrame] = {}
        daily: dict[str, pd.DataFrame] = {}
        symbols = _symbols_for_scope(scope)
        # Polite pacing between symbols keeps the full sweep well under Yahoo's rate
        # limits — the morning sentinel runs unattended, so slow-and-reliable wins.
        pace = _fetch_pace_seconds()
        for symbol in symbols:
            try:
                weekly[symbol] = fetch_ohlcv(symbol, interval="1wk", period="5y", auto_adjust=True)
                daily[symbol] = fetch_ohlcv(symbol, interval="1d", period="6mo", auto_adjust=True)
            except Exception:
                weekly[symbol] = pd.DataFrame()
                daily[symbol] = pd.DataFrame()
            # A failed/empty fetch must never overwrite a previously good cache entry — the
            # next reader (ticker(), interpret(), backtester, ledger) falls back to the cache,
            # and a transient rate-limit/network blip shouldn't silently erase real bars.
            if not weekly[symbol].empty:
                self.store.save_bars(symbol, "weekly", frame_to_bars(weekly[symbol]))
            else:
                logging.warning("market refresh: %s weekly fetch failed/empty — keeping cached bars", symbol)
            if not daily[symbol].empty:
                self.store.save_bars(symbol, "daily", frame_to_bars(daily[symbol]))
            else:
                logging.warning("market refresh: %s daily fetch failed/empty — keeping cached bars", symbol)
            if pace > 0:
                time.sleep(pace)

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

        # _assemble_dashboard runs inside asyncio.to_thread (see rpc_market.py), i.e. a plain
        # worker thread with no running loop, so asyncio.run() here is a safe sync/async bridge.
        evidence = asyncio.run(
            fetch_evidence([asset.symbol for asset in UNIVERSE if asset.role in {"holding", "watch", "spec"}])
        )
        evidence_note = None
        if not evidence:
            # Zero evidence across every symbol in one cycle is far more likely a transient failure
            # (SEC rate-limit, network hiccup) than every ticker genuinely having no insider/8-K
            # activity — don't let that silently wipe a previously good evidence panel.
            previous = _evidence_from_dashboard(self.store.load_dashboard_wire())
            if previous:
                logging.warning("market refresh: evidence fetch returned empty for all symbols, keeping last known evidence")
                evidence = previous
                evidence_note = "evidence fetch returned empty this cycle — showing last known evidence"
        dashboard.evidence = MarketPanel(status="live", data=evidence, as_of=_now_iso(), note=evidence_note)

        breadth_pct = (above_trend / total_trend * 100) if total_trend else 0.0
        briefing, contrarian = synthesize_briefing(macro=macro, evidence=evidence, breadth_pct=breadth_pct)

        regime_status: str = "live"
        regime_note: str | None = None
        if total_trend == 0:
            # No symbol had trend data this cycle — every fetch failed/was empty. 0.0 breadth
            # is a fetch-failure artifact, not a genuine "everything is risk-off" reading;
            # publishing it as live would be a confident false regime call. Mark it stale
            # instead, mirroring the evidence-panel fetch-failure guard above.
            logging.warning("market refresh: no symbols had trend data this cycle — regime/briefing marked stale")
            regime_status = "stale"
            regime_note = "no trend data this cycle (fetch failure) — regime is unknown, not risk-off"

        dashboard.briefing = MarketPanel(status=regime_status, data=briefing, as_of=_now_iso(), note=regime_note)
        dashboard.contrarian = MarketPanel(status=regime_status, data=contrarian, as_of=_now_iso(), note=regime_note)
        dashboard.regime = MarketPanel(
            status=regime_status,
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
            note=regime_note,
        )
        return dashboard


def default_market_dir() -> Path:
    return default_sessions_dir().parent / "market"


def resolve_market_runtime(orchestrator) -> MarketRuntime:
    """Shared MarketRuntime per orchestrator — the sentinel and the RPC layer must see the
    same store so a scheduled sweep and an operator-triggered one never diverge."""
    runtime = getattr(orchestrator, "_market_runtime", None)
    if isinstance(runtime, MarketRuntime):
        return runtime
    store = getattr(orchestrator, "market_store", None)
    runtime = MarketRuntime(store=store if isinstance(store, MarketStore) else None)
    try:
        setattr(orchestrator, "_market_runtime", runtime)
    except Exception:
        pass
    return runtime


def _fetch_pace_seconds() -> float:
    try:
        return max(float(os.environ.get("COPNET_MARKET_FETCH_PACE", "0.2")), 0.0)
    except ValueError:
        return 0.2


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


def _build_intelligence(
    fs: FeatureSet,
    *,
    role: str,
    verdict: list,
    rotation,
    portfolio: dict[str, Any] | None,
    exposure: dict[str, Any] | None,
) -> TickerIntelligence:
    """Reshape the FeatureSet the Insight Engine already computes into a compact, agent-facing
    packet — the numbers already exist, this just stops discarding all but the soft-bottoming flags."""
    return TickerIntelligence(
        as_of=fs.as_of,
        asset_role=role,
        trend={
            "ma_stack": fs.ma_stack,
            "long_trend": fs.long_trend,
            "long_trend_slope_pct_per_year": fs.long_trend_slope,
            "dist_ma10_pct": fs.dist_ma10,
            "dist_ma30_pct": fs.dist_ma30,
            "dist_ma40_pct": fs.dist_ma40,
            "slope_ma10_pct": fs.slope_ma10,
            "slope_ma30_pct": fs.slope_ma30,
            "slope_ma40_pct": fs.slope_ma40,
        },
        momentum={
            "rsi_14": fs.rsi_14,
            "atr_pct": fs.atr_pct,
            "atr_move_multiple": fs.atr_move,
            "atr_percentile": fs.atr_pctile,
            "vol_vs_avg": fs.vol_vs_avg,
            "up_down_vol_ratio": fs.up_down_vol,
        },
        returns={
            "r_1w_pct": fs.r_1w,
            "r_4w_pct": fs.r_4w,
            "r_13w_pct": fs.r_13w,
            "r_26w_pct": fs.r_26w,
            "r_52w_pct": fs.r_52w,
            "r_ytd_pct": fs.r_ytd,
            "r_3y_pct": fs.r_3y,
        },
        drawdown={
            "drawdown_52w_pct": fs.drawdown_pct,
            "weeks_since_52w_high": fs.weeks_since_high,
            "pct_of_52w_range": fs.pct_52w,
            "dist_from_full_history_high_pct": fs.dist_hi_full,
            "weeks_since_full_history_high": fs.weeks_since_hi_full,
            "pct_of_full_history_range": fs.pct_range_full,
        },
        volatility={
            "vol_4w_annualized_pct": fs.vol_4w,
            "vol_13w_annualized_pct": fs.vol_13w,
            "vol_26w_annualized_pct": fs.vol_26w,
            "beta_52w_vs_voo": fs.beta_52w,
            "corr_52w_vs_voo": fs.corr_52w,
        },
        relative_strength={
            "rs_ratio_vs_voo": fs.rs_ratio,
            "rs_momentum_vs_voo": fs.rs_momentum,
            "excess_return_13w_pct": fs.excess_13w,
            "excess_return_26w_pct": fs.excess_26w,
            "benchmarks": [{"symbol": v.bench, "verdict": v.label, "risk_adjusted_excess": v.pct} for v in verdict],
        },
        structure={
            "compression": fs.compression,
            "compression_shape": fs.compression_shape,
            "range_ratio_12w_vs_36w": fs.range_ratio_12v36,
        },
        data_quality={
            "history_weeks": fs.history_weeks,
            "has_volume": fs.has_volume,
            "thin_history": fs.thin_history,
        },
        rotation={"quadrant": rotation.quadrant, "benchmark": "VOO"} if rotation is not None else None,
        portfolio=portfolio,
        exposure=exposure,
    )


def _portfolio_position_for_symbol(symbol: str, *, last: float) -> dict[str, Any] | None:
    """Best-effort portfolio join for a single symbol — Webull snapshot first, static cost-basis
    fallback second. Mirrors the join already done for the whole-dashboard portfolio panel."""
    snapshot = load_webull_snapshot()
    if snapshot:
        for row in snapshot.get("positions", []):
            if isinstance(row, dict) and row.get("symbol") == symbol:
                return {
                    "shares": row.get("quantity"),
                    "avg_cost": row.get("avg_cost"),
                    "last_price": row.get("last_price"),
                    "pnl_pct": row.get("unrealized_pl_pct"),
                    "allocation_pct": row.get("allocation_pct"),
                    "source": "webull",
                }
    basis = PORTFOLIO_BASIS.get(symbol)
    if basis and last:
        avg_cost = float(basis["avg_cost"])
        pnl_pct = ((last / avg_cost) - 1) * 100 if avg_cost else None
        return {
            "shares": basis["shares"],
            "avg_cost": avg_cost,
            "last_price": last,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "allocation_pct": None,
            "source": "configured cost basis",
        }
    return None


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
        "below_ma": "Dist from 40W MA",
        "drawdown": "Drawdown (52w)",
        "rsi": "RSI",
        "relative_strength": "Relative strength",
        "mama_regime": "MAMA/FAMA",
        "atr_move": "ATR move",
        "volume_vs_avg": "Volume vs 20D avg",
    }
    rows = []
    for key, label in mapping.items():
        value = str(signals.get(key) or signals.get(_camel(key)) or "n/a")
        rows.append(SignalRow(key=label, value=value, tone=_tone_from_value(value)))
    return rows


def _trailing_eps_and_pe(fundamentals: dict[str, Any], weekly_frame: pd.DataFrame) -> dict[str, Any]:
    """CopeTech-Edgar has no ratio calculator (ratios need a live price, which is CopeNet's job) —
    sum the last 4 quarterly EPS values for trailing-twelve-month EPS, then divide the last known
    close into it for a trailing P/E. Returns {} (not a P/E) if EPS is negative or unavailable."""
    eps_quarterly = fundamentals.get("epsQuarterly") or []
    eps_ttm = None
    if len(eps_quarterly) >= 4:
        try:
            eps_ttm = sum(float(e["value"]) for e in eps_quarterly[:4])
        except (TypeError, ValueError, KeyError):
            eps_ttm = None
    pe_ttm = None
    if eps_ttm is not None and eps_ttm > 0 and not weekly_frame.empty:
        try:
            last_price = float(weekly_frame["close"].iloc[-1])
            pe_ttm = last_price / eps_ttm
        except (TypeError, ValueError, IndexError, KeyError):
            pe_ttm = None
    return {"epsTtm": eps_ttm, "peTtm": pe_ttm}


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
                    t=row.get("t"),
                    flag=row.get("flag"),
                    value=row.get("value"),
                    price=row.get("price"),
                    shares=row.get("shares"),
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
