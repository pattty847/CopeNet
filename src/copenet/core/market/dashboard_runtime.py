"""Acquisition and dashboard projection extracted from the ticker runtime.

Scoped scans pass acquired evidence explicitly: projection never adds source work.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
import pandas as pd

from .base_rates import load_base_rate
from .edgar import fetch_evidence
from .features import compute_features
from .models import AccumulationRow, DashboardPayload, EvidenceItem, MarketPanel, SoftBottomItem, UniverseAsset
from .signals import compute_price_signals, compute_rrg_tail
from .synthesis import synthesize_briefing
from .universe import INDUSTRY_SYMBOLS, SECTOR_SYMBOLS, SIGNAL_ROLES
from .webull.sync import load_snapshot as load_webull_snapshot


class DashboardRuntime:
    def update_portfolio(self, snapshot: dict) -> DashboardPayload:
        """Project a completed broker sync without starting Yahoo/SEC acquisition."""
        from .runtime import _portfolio_panel_from_webull
        from .scans.store import file_lock

        # Wait behind a running scan so the two read/modify/write projections cannot
        # replace each other's unrelated panels. Broker acquisition itself stays outside.
        with file_lock(self.store.root_dir / "scans" / "execution.lock"):
            dashboard = project_cached_dashboard(self.store.load_dashboard_wire())
            synced_at = snapshot.get("synced_at")
            dashboard.portfolio = MarketPanel(status="live", data=_portfolio_panel_from_webull(snapshot),
                as_of=synced_at, note=f"account data: Webull · synced {synced_at or 'unknown'}")
            self.store.save_dashboard(dashboard)
            return dashboard

    def refresh(self, *, scope: str = "all") -> DashboardPayload:
        from .runtime import REFRESH_DAILY_BARS, REFRESH_WEEKLY_BARS, _bars_to_frame, _fetch_pace_seconds, _symbols_for_scope

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
        evidence: list[EvidenceItem] | None = None,
    ) -> DashboardPayload:
        from .runtime import _as_of_label, _now_iso, _macro_items, _speculative_panel, _portfolio_panel_from_webull, _evidence_from_dashboard

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
        if evidence is None:
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


def project_cached_dashboard(payload: dict) -> DashboardPayload:
    """Rehydrate panel metadata/data for a targeted projection, without I/O."""
    dashboard = DashboardPayload.empty(as_of=payload["asOf"])
    for name in ("briefing", "regime", "macro", "rrg", "industry_rrg", "accumulation", "trend", "soft_bottoming", "portfolio", "speculative", "evidence", "contrarian"):
        parts = name.split("_")
        wire_name = parts[0] + "".join(part.title() for part in parts[1:])
        panel = payload[wire_name]
        setattr(dashboard, name, MarketPanel(status=panel["status"], data=panel["data"], as_of=panel.get("asOf"), note=panel.get("note")))
    return dashboard
