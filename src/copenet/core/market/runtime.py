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
from .data_sources import (
    fetch_fund_profile,
    fetch_key_stats,
    fetch_split_history,
    macro_item_from_frame,
)
from .edgar import chart_events_from_evidence, fetch_evidence, fetch_fundamentals
from .models import (
    AccumulationRow,
    ChartSeriesPayload,
    ChartSeriesRow,
    CompareResult,
    CompareRow,
    DashboardPayload,
    EvidenceItem,
    InsightBaseRate,
    InsightComponent,
    MarketBar,
    MarketPanel,
    Portfolio,
    PortfolioPosition,
    SignalRow,
    SoftBottomItem,
    SpecPosition,
    TickerDetailPayload,
    TickerInsight,
    TickerIntelligence,
    TickerQuote,
    UniverseAsset,
)
from .base_rates import load_base_rate
from .fact_packets import market_fact_packet, market_history_section, ticker_fact_packet
from .ledger import record_market_read_claims, record_ticker_read_claim
from .ledger_report import track_record_line
from .features import FeatureSet, compute_features
from .interpretation import generate_market_read, generate_ticker_read
from .market_tape import build_market_tape
from .market_tape_formatter import format_market_tape
from .price_cache import PriceCache
from .price_history import SPLIT_ADJUSTED, TOTAL_RETURN
from .signals import compute_price_signals, compute_rrg_tail
from .webull.config import include_portfolio_context_enabled
from .webull.context_pack import build_portfolio_context_pack
from .webull.sync import load_snapshot as load_webull_snapshot
from .store import MarketStore
from .synthesis import synthesize_briefing
from .universe import (
    INDUSTRY_SYMBOLS,
    MACRO_SYMBOLS,
    SECTOR_SYMBOLS,
    SIGNAL_ROLES,
    UNIVERSE,
    find_asset,
    merge_watchlist_assets,
)
from .watchlist_store import WatchlistStore


#: Existing consumers were fed `auto_adjust=True` bars — splits *and* dividends. Serving
#: total_return from the cache reproduces that basis to within 0.0005%, so adopting the
#: cache is a pure speed change and no signal, RRG, or drawdown value shifts underneath
#: it. Whether pattern detection *should* run on a split-only basis is a separate product
#: call. Trailing P/E already asks for `split_adjusted` instead, because a P/E numerator
#: has to be the price actually paid rather than a total-return series.
DEFAULT_MARKET_PRICE_BASIS = TOTAL_RETURN

#: Full history is cheap to serve now, but a 60-year daily series is a needlessly large
#: wire payload for a chart. Weekly and monthly stay unbounded so they always reach back
#: past the earliest SEC facts (2009-ish), which is what stops a financial overlay from
#: extending the chart's time axis before the first candle.
CHART_BAR_LIMITS: dict[str, int | None] = {"daily": 2_600, "weekly": None, "monthly": None}

#: Signal windows the dashboard sweep has always used — 5y weekly, 6mo daily. Held
#: constant while the *source* moved to the cache, so no signal, RRG, or drawdown value
#: shifts underneath the change. A caching commit must not silently re-tune pattern
#: detection by widening the history those features are computed over.
REFRESH_WEEKLY_BARS = 261
REFRESH_DAILY_BARS = 126


class MarketRuntime:
    def __init__(
        self,
        store: MarketStore | None = None,
        prices: PriceCache | None = None,
        watchlists: WatchlistStore | None = None,
    ) -> None:
        self.store = store or MarketStore(default_market_dir())
        self.prices = prices or PriceCache(self.store.root_dir / "prices")
        # Rooted off the same market dir as rpc_market_watchlist.watchlist_store(), so the
        # scan and the watchlist UI read one file and a symbol added in the UI is scanned
        # on the next sweep.
        self.watchlists = watchlists or WatchlistStore(self.store.root_dir / "watchlist.json")

    def scan_universe(self) -> tuple[UniverseAsset, ...]:
        """The public UNIVERSE plus the operator's watchlist symbols, resolved per call.

        Read fresh rather than cached at construction: the runtime is a long-lived singleton,
        and a symbol added mid-day must be picked up by the next refresh without a restart.
        A broken/unreadable watchlist file degrades to the public universe rather than
        failing the sweep — a stale panel beats no dashboard.
        """
        try:
            lists = self.watchlists.scan_lists()
        except Exception:
            logging.warning("market refresh: watchlist unreadable — scanning public universe only", exc_info=True)
            return UNIVERSE
        return merge_watchlist_assets(lists)

    def recent_sessions(self, *, limit: int = 6) -> list[dict[str, Any]]:
        """Structured day-over-day trail for the briefing UI, newest first.

        The prose twin of this is `market_history_section`, which feeds the model. Kept separate
        deliberately: the model wants one compact block it can reason over, the UI wants rows it
        can lay out. Reads are joined by date and may be absent for older sessions — the archive
        only starts where it started, and a missing read is rendered, not faked.
        """
        reads = {
            str(r.get("generatedAt") or "")[:10]: r
            for r in self.store.load_market_reads(limit=limit)
            if r.get("generatedAt")
        }
        sessions: list[dict[str, Any]] = []
        for brief in self.store.load_morning_briefs(limit=limit):
            date = str(brief.get("briefDate") or "").strip()
            if not date:
                continue
            read = reads.get(date) or {}
            sessions.append(
                {
                    "date": date,
                    "headline": brief.get("headline") or "",
                    "rrgShifts": brief.get("rrgShifts") or [],
                    "signalFlips": brief.get("signalFlips") or [],
                    "regime": read.get("regime") or "",
                }
            )
        return sessions

    def dashboard(self) -> DashboardPayload:
        return self.store.load_dashboard()

    def universe(self) -> list[dict[str, Any]]:
        return [asset.to_wire() for asset in self.scan_universe()]

    def cached_bars(
        self,
        symbol: str,
        timeframe: str,
        *,
        basis: str = DEFAULT_MARKET_PRICE_BASIS,
    ) -> list[MarketBar]:
        """Candles from the durable daily cache, falling back to MarketStore's bars.

        One cached daily history serves every timeframe, so this replaces what used to be
        a separate network fetch per timeframe per view. A refresh failure must never
        erase a good cache: an empty result falls through to the older stored bars rather
        than reporting the symbol as having no history.
        """
        try:
            self.prices.refresh(symbol)
        except Exception:
            logging.warning("market: %s price cache refresh failed", symbol, exc_info=True)
        return self._cache_bars(symbol, timeframe, CHART_BAR_LIMITS.get(timeframe), basis=basis) or (
            self.store.load_bars(symbol, timeframe)
        )

    def _cache_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int | None,
        *,
        basis: str = DEFAULT_MARKET_PRICE_BASIS,
    ) -> list[MarketBar]:
        """Derive from the stored cache without any network call. May be empty."""
        try:
            bars = self.prices.bars(symbol, timeframe=timeframe, basis=basis)
        except Exception:
            logging.warning("market: %s %s cache read failed", symbol, timeframe, exc_info=True)
            return []
        return bars[-limit:] if (bars and limit) else bars

    def _last_split_adjusted_close(self, symbol: str) -> float | None:
        """Latest close on the price basis a P/E numerator requires.

        The chart frames serve TOTAL_RETURN, which folds dividends into history; dividing
        that by split-only EPS understates every trailing multiple. Same defect the
        overlay path already fixed — the summary card must use the traded price too.
        """
        try:
            bars = self.prices.bars(symbol, timeframe="weekly", basis=SPLIT_ADJUSTED)
            return float(bars[-1].c) if bars else None
        except Exception:
            logging.warning(
                "market: %s split-adjusted close unavailable", symbol, exc_info=True
            )
            return None

    def _weekly_frame(
        self,
        symbol: str,
        *,
        basis: str = DEFAULT_MARKET_PRICE_BASIS,
    ) -> pd.DataFrame:
        """Weekly benchmark series off the shared cache.

        VOO/QQQ/XLK are the same three symbols for every ticker view, so before the cache
        existed each view re-downloaded all three from Yahoo just to compute one relative
        strength read."""
        return _bars_to_frame(self.cached_bars(symbol, "weekly", basis=basis))

    def ticker(self, symbol: str, *, compare: list[str] | None = None) -> TickerDetailPayload:
        normalized = symbol.strip().upper()
        asset = find_asset(normalized)
        name = asset.name if asset else normalized
        # All three timeframes are derived from one cached daily history, so opening a
        # ticker costs at most a single delta request instead of one download per
        # timeframe. Weekly and monthly now carry full history rather than 5y/10y.
        fetched_at = _now_iso()
        # The asset workspace shows historical prices that actually traded. Total-return
        # series remain appropriate for portfolio/replay analytics, but dividend-adjusted
        # history makes old chart levels and operator annotations misleading.
        daily = self.cached_bars(normalized, "daily", basis=SPLIT_ADJUSTED)
        weekly = self.cached_bars(normalized, "weekly", basis=SPLIT_ADJUSTED)
        monthly = self.cached_bars(normalized, "monthly", basis=SPLIT_ADJUSTED)
        weekly_frame = _bars_to_frame(weekly)
        evidence = [item for item in _evidence_from_dashboard(self.store.load_dashboard_wire()) if item.symbol == normalized]
        latest_bars = daily or weekly or monthly
        last = latest_bars[-1].c if latest_bars else None
        previous = latest_bars[-2].c if len(latest_bars) > 1 else None
        change_pct = ((last / previous) - 1) * 100 if last is not None and previous else None
        bar_time = latest_bars[-1].t if latest_bars else None
        voo_frame = self._weekly_frame("VOO", basis=SPLIT_ADJUSTED)
        qqq_frame = self._weekly_frame("QQQ", basis=SPLIT_ADJUSTED)
        # Always compute signals live from the same weekly_frame used below — the cached
        # per-symbol signals (written by the last dashboard refresh) can be stale enough
        # to disagree with the live-fetched intelligence packet (e.g. drawdown %) in the
        # same response, which is confusing rather than just imprecise.
        signals = compute_price_signals(weekly_frame, benchmark=voo_frame).__dict__ if not weekly_frame.empty else {}
        # Default benchmarks are the broad market/growth read (VOO/XLK/QQQ); `compare` lets the
        # caller add specific symbols (a sector ETF, a direct competitor) on top — it never
        # replaces the defaults, so the human-facing Market page's verdict table is unaffected.
        benchmark_frames = {
            "VOO": voo_frame,
            "XLK": self._weekly_frame("XLK", basis=SPLIT_ADJUSTED),
            "QQQ": qqq_frame,
        }
        for extra in compare or []:
            extra_symbol = extra.strip().upper()
            if extra_symbol and extra_symbol not in benchmark_frames:
                benchmark_frames[extra_symbol] = self._weekly_frame(extra_symbol, basis=SPLIT_ADJUSTED)
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
            portfolio=_portfolio_position_for_symbol(normalized, last=last or 0.0),
            exposure=fetch_fund_profile(normalized),
        )
        return TickerDetailPayload(
            symbol=normalized,
            name=name,
            as_of=fetched_at,
            quote=TickerQuote(
                price=round(last, 4) if last is not None else None,
                change_pct=round(change_pct, 4) if change_pct is not None else None,
                bar_time=bar_time,
                comparison="previous_daily_bar",
                price_basis="split_adjusted",
            ),
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

    def chart_series(self, symbols: list[str], timeframe: str) -> ChartSeriesPayload:
        normalized_timeframe = timeframe.strip().lower()
        if normalized_timeframe not in CHART_BAR_LIMITS:
            raise ValueError("timeframe must be daily, weekly, or monthly")
        normalized_symbols: list[str] = []
        for raw in symbols:
            symbol = raw.strip().upper()
            if symbol and symbol not in normalized_symbols:
                normalized_symbols.append(symbol)
        if not normalized_symbols:
            raise ValueError("at least one symbol is required")
        if len(normalized_symbols) > 10:
            raise ValueError("chart comparison supports at most 10 component symbols")
        return ChartSeriesPayload(
            as_of=_now_iso(),
            timeframe=normalized_timeframe,  # type: ignore[arg-type]
            price_basis="split_adjusted",
            series=[
                ChartSeriesRow(
                    symbol=symbol,
                    bars=self.cached_bars(symbol, normalized_timeframe, basis=SPLIT_ADJUSTED),
                )
                for symbol in normalized_symbols
            ],
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
            # The trail behind today: skip the current session's own brief/read so the model is
            # comparing against prior calls, not being handed its own conclusion as evidence.
            today = datetime.now().strftime("%Y-%m-%d")
            prior_briefs = [b for b in self.store.load_morning_briefs(limit=8) if b.get("briefDate") != today]
            prior_reads = [
                r for r in self.store.load_market_reads(limit=8)
                if str(r.get("generatedAt") or "")[:10] != today
            ]
            dashboard_wire = self.store.load_dashboard_wire()
            packet = market_fact_packet(
                dashboard_wire,
                sb_rate,
                overnight=overnight,
                history=market_history_section(prior_briefs, prior_reads),
            )
            tape = build_market_tape(self.store, dashboard_wire, generated_at=generated_at)
            self.store.save_market_tape(tape.to_wire())
            packet = f"{packet}\n\n{format_market_tape(tape)}"
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
        # Multi-year structure features need the 5y weekly history; same cache-backed path
        # as ticker(), bounded to the window these features have always been tuned on.
        weekly_frame = _bars_to_frame(
            self._cache_bars(symbol, "weekly", REFRESH_WEEKLY_BARS)
            or self.store.load_bars(symbol, "weekly")
        )
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
            fundamentals = {
                **fundamentals,
                **_trailing_eps_and_pe(
                    fundamentals,
                    self._last_split_adjusted_close(symbol),
                    symbol,
                ),
            }
        query_name = asset.name if asset else symbol
        try:
            news_results, news_source = await run_web_search(f"{query_name} {symbol} stock news", limit=5, kind="news")
        except Exception:
            news_results, news_source = [], "unavailable"
        packet = ticker_fact_packet(
            fs,
            name=asset.name if asset else symbol,
            base_rate=sb_rate,
            verdict=[
                {
                    "bench": v.bench,
                    "label": v.label,
                    "excess_return_pct": v.excess_return_pct,
                    "asset_return_pct": v.asset_return_pct,
                    "benchmark_return_pct": v.benchmark_return_pct,
                    "beta": v.beta,
                    "beta_adjusted_excess_pct": v.beta_adjusted_excess_pct,
                }
                for v in verdict
            ],
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
        universe = self.scan_universe()
        symbols = _symbols_for_scope(scope, universe)
        # Polite pacing between symbols keeps the full sweep well under Yahoo's rate
        # limits — the morning sentinel runs unattended, so slow-and-reliable wins.
        pace = _fetch_pace_seconds()
        for symbol in symbols:
            # One request per symbol now covers both timeframes: the first sweep pulls the
            # symbol's full history, every sweep afterwards is a small delta. This used to
            # be two downloads each, re-pulling years of unchanged bars every morning.
            # max_age_seconds=0 because collecting the session's new candle is precisely
            # this job's purpose — a sweep that served yesterday's cache would be useless.
            try:
                self.prices.refresh(symbol, max_age_seconds=0)
            except Exception:
                logging.warning("market refresh: %s price fetch failed", symbol, exc_info=True)
            fresh_weekly = self._cache_bars(symbol, "weekly", REFRESH_WEEKLY_BARS)
            fresh_daily = self._cache_bars(symbol, "daily", REFRESH_DAILY_BARS)
            # A failed/empty fetch must never overwrite a previously good cache entry — the
            # next reader (ticker(), interpret(), backtester, ledger) falls back to the cache,
            # and a transient rate-limit/network blip shouldn't silently erase real bars.
            if fresh_weekly:
                self.store.save_bars(symbol, "weekly", fresh_weekly)
            else:
                logging.warning("market refresh: %s weekly fetch failed/empty — keeping cached bars", symbol)
            if fresh_daily:
                self.store.save_bars(symbol, "daily", fresh_daily)
            else:
                logging.warning("market refresh: %s daily fetch failed/empty — keeping cached bars", symbol)
            weekly[symbol] = _bars_to_frame(fresh_weekly or self.store.load_bars(symbol, "weekly"))
            daily[symbol] = _bars_to_frame(fresh_daily or self.store.load_bars(symbol, "daily"))
            if pace > 0:
                time.sleep(pace)

        dashboard = self._assemble_dashboard(weekly=weekly, daily=daily, universe=universe)
        self.store.save_dashboard(dashboard)
        return dashboard

    def _assemble_dashboard(
        self,
        *,
        weekly: dict[str, pd.DataFrame],
        daily: dict[str, pd.DataFrame],
        universe: tuple[UniverseAsset, ...] | None = None,
    ) -> DashboardPayload:
        universe = universe if universe is not None else self.scan_universe()
        as_of = _as_of_label()
        dashboard = DashboardPayload.empty(as_of=as_of)
        macro = _macro_items(weekly)
        if macro:
            dashboard.macro = MarketPanel(status="live", data=macro, as_of=_now_iso())

        benchmark = weekly.get("VOO", pd.DataFrame())
        accumulation: list[AccumulationRow] = []
        trend: list[Any] = []
        live_signal_symbols = [asset.symbol for asset in universe if asset.role in SIGNAL_ROLES]
        soft_bottoms: list[SoftBottomItem] = []
        above_trend = 0
        total_trend = 0
        for asset in universe:
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
            for asset in universe
            if asset.symbol in SECTOR_SYMBOLS
        ]
        rrg = [sector for sector in rrg if sector.tail]
        if rrg:
            dashboard.rrg = MarketPanel(status="live", data=rrg, as_of=_now_iso())

        # Second rotation chart, same benchmark and math, narrower lens: industry funds rotate
        # against the S&P independently of the sector that contains them, and averaging them
        # into the 12-tail sector RRG both crowds that chart and hides the divergence.
        industry_rrg = [
            compute_rrg_tail(asset.symbol, asset.name, weekly.get(asset.symbol, pd.DataFrame()), benchmark)
            for asset in universe
            if asset.symbol in INDUSTRY_SYMBOLS
        ]
        industry_rrg = [item for item in industry_rrg if item.tail]
        if industry_rrg:
            dashboard.industry_rrg = MarketPanel(status="live", data=industry_rrg, as_of=_now_iso())

        webull_snapshot = load_webull_snapshot()
        if webull_snapshot and webull_snapshot.get("positions"):
            portfolio = _portfolio_panel_from_webull(webull_snapshot)
            note = f"account data: Webull · synced {webull_snapshot.get('synced_at', 'unknown')}"
        else:
            portfolio = None
            note = None
        if portfolio is not None and portfolio.positions:
            dashboard.portfolio = MarketPanel(status="live", data=portfolio, as_of=_now_iso(), note=note)

        speculative = _speculative_panel(weekly, universe)
        if speculative:
            dashboard.speculative = MarketPanel(status="live", data=speculative, as_of=_now_iso())

        # _assemble_dashboard runs inside asyncio.to_thread (see rpc_market.py), i.e. a plain
        # worker thread with no running loop, so asyncio.run() here is a safe sync/async bridge.
        evidence = asyncio.run(fetch_evidence(live_signal_symbols))
        evidence_note = None
        if not live_signal_symbols:
            # Nothing to sweep is not a fetch failure — say so, rather than blaming the SEC.
            evidence_note = "no watchlist symbols in the scan — add tickers or set a list's role to watch"
        elif not evidence:
            # Zero evidence across every symbol in one cycle is far more likely a transient failure
            # (SEC rate-limit, network hiccup) than every ticker genuinely having no insider/8-K
            # activity — don't let that silently wipe a previously good evidence panel.
            previous = _evidence_from_dashboard(self.store.load_dashboard_wire())
            if previous:
                logging.warning("market refresh: evidence fetch returned empty for all symbols, keeping last known evidence")
                evidence = previous
                evidence_note = "evidence fetch returned empty this cycle — showing last known evidence"
        # Newest filing first. fetch_evidence returns per-symbol batches concatenated in universe
        # order, so unsorted the panel reads as symbol-grouped noise and buries this morning's
        # Form 4 under last week's. Sorted here rather than in the panel so the ticker view and
        # the model fact packet inherit the same ordering. Undated items sink to the bottom.
        evidence.sort(key=lambda item: getattr(item, "t", None) or 0, reverse=True)
        dashboard.evidence = MarketPanel(status="live", data=evidence, as_of=_now_iso(), note=evidence_note)

        breadth_pct = (above_trend / total_trend * 100) if total_trend else 0.0
        briefing, contrarian = synthesize_briefing(macro=macro, evidence=evidence, breadth_pct=breadth_pct)

        regime_status: str = "live"
        regime_note: str | None = None
        if total_trend == 0:
            # Breadth of 0.0 here is an artifact, not a genuine "everything is risk-off" reading,
            # so publishing it as live would be a confident false regime call either way. But the
            # two causes need different words: an empty scan universe is a config problem the
            # operator can fix, and calling it a "fetch failure" sends them to the wrong layer.
            regime_status = "stale"
            if not live_signal_symbols:
                logging.warning(
                    "market refresh: scan universe has no holding/watch/spec symbols — "
                    "signal panels will be empty until a watchlist is populated"
                )
                regime_note = "no watchlist symbols in the scan — regime is unknown, not risk-off"
            else:
                logging.warning("market refresh: no symbols had trend data this cycle — regime/briefing marked stale")
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


def _speculative_panel(
    frames: dict[str, pd.DataFrame], universe: tuple[UniverseAsset, ...]
) -> list[SpecPosition]:
    """Drawdown-from-52w-high for every `spec`-role name in the scan universe.

    Restored from fca5acb, which deleted this wholesale because the symbol pair was hardcoded
    (operator data). Driving it off the role instead keeps the panel while leaving the names in
    the watchlist store where they belong — mark a list `spec` and it populates.
    """
    rows: list[SpecPosition] = []
    for asset in universe:
        if asset.role != "spec":
            continue
        frame = frames.get(asset.symbol, pd.DataFrame())
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
                symbol=asset.symbol,
                pnl_pct=f"{drawdown:+.1f}%",
                tone="down" if drawdown < 0 else "up",
                thesis="Spec lane: small-size position with defined invalidation.",
                entry=f"${last:,.2f}",
                target="risk-adjusted outperformance vs VOO/sector ETF",
                invalidation="weekly close below prior support plus lagging benchmark verdict",
            )
        )
    return rows


def _symbols_for_scope(scope: str, universe: tuple[UniverseAsset, ...] = UNIVERSE) -> list[str]:
    if scope == "macro":
        return list(MACRO_SYMBOLS) + ["VOO"]
    # `context` symbols are quoted, never analyzed — no panel reads their bars, and both the
    # watchlist quote strip and the ticker page fetch on demand (see cached_bars). Sweeping
    # them daily was buying nothing and is the bulk of the request budget when an operator
    # keeps old broker imports around.
    return [asset.symbol for asset in universe if asset.role != "context"]


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
            "benchmarks": [
                {
                    "symbol": v.bench,
                    "verdict": v.label,
                    "excess_return_pct": v.excess_return_pct,
                    "asset_return_pct": v.asset_return_pct,
                    "benchmark_return_pct": v.benchmark_return_pct,
                    "beta": v.beta,
                    "beta_adjusted_excess_pct": v.beta_adjusted_excess_pct,
                }
                for v in verdict
            ],
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
    """Best-effort portfolio join for a single symbol from the local Webull snapshot."""
    del last
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


def _trailing_eps_and_pe(
    fundamentals: dict[str, Any],
    last_price: float | None,
    symbol: str,
) -> dict[str, Any]:
    """Use CopeTech's canonical TTM diluted EPS for the latest summary valuation."""
    reported_eps_ttm = fundamentals.get("epsTtm")
    try:
        reported_eps_ttm = (
            float(reported_eps_ttm)
            if reported_eps_ttm is not None
            else None
        )
    except (TypeError, ValueError):
        reported_eps_ttm = None
    eps_ttm = reported_eps_ttm
    split_factor = None
    if eps_ttm is not None:
        if fundamentals.get("epsTtmShareBasis") == "split_adjusted":
            split_factor = 1.0
        else:
            splits, split_history_verified = fetch_split_history(symbol)
            if split_history_verified:
                available_at = str(fundamentals.get("epsTtmAvailableAt") or "")
                split_factor = 1.0
                for ex_date, ratio in splits:
                    if available_at and ex_date > available_at:
                        split_factor *= ratio
                eps_ttm /= split_factor
            else:
                eps_ttm = None
    pe_ttm = None
    if eps_ttm is not None and eps_ttm > 0 and last_price is not None and last_price > 0:
        pe_ttm = last_price / eps_ttm
    return {
        "epsTtm": eps_ttm,
        "epsTtmReported": reported_eps_ttm,
        "epsTtmSplitFactor": split_factor,
        "peTtm": pe_ttm,
    }


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
