"""Build point-in-time market tapes for interpretation and future research.

Raw split-adjusted bars remain the durable source of truth.  This module freezes the
normalized state an analyst or model actually saw: recent candle geometry, broad-market
participation, RRG motion, and the risk-plumbing relationships around credit, volatility,
rates, and the dollar.  Keeping the builder pure over ``MarketStore`` makes historical
replay use the same path as the live morning read.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import math
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .market_tape_contract import (
    MARKET_TAPE_BAR_WINDOW,
    MARKET_TAPE_SCHEMA_VERSION,
    MarketTapePacket,
    ParticipationSnapshot,
    RiskPlumbingSnapshot,
    RrgObservation,
    RrgVector,
    TapeBar,
    TapeDataQuality,
    TapeInstrument,
    TapeSummary,
    TrendObservation,
)
from .store import MARKET_BAR_PRICE_BASIS, MarketStore
from .trend_states import classify_trend
from .universe import SECTOR_SYMBOLS


_EASTERN = ZoneInfo("America/New_York")

# A small, stable, account-neutral basket.  The packet is not a quote screen: every name
# answers one market-health question and already exists in CopeNet's public universe.
TAPE_INSTRUMENTS: tuple[tuple[str, str], ...] = (
    ("VOO", "broad_market"),
    ("QQQ", "growth_leadership"),
    ("RSP", "equal_weight"),
    ("IWM", "small_caps"),
    ("HYG", "high_yield_credit"),
    ("LQD", "investment_grade_credit"),
    ("TLT", "long_duration"),
    ("VIX", "volatility"),
    ("DXY", "dollar"),
    ("GLD", "defensive_hedge"),
)
INDEX_PARTICIPATION_SYMBOLS = ("VOO", "QQQ", "DIA", "RSP", "IWM", "VONE", "VTHR", "EFA", "VWO")
_POSITIVE_TREND_STATES = {"up", "strong_up"}
_NEGATIVE_TREND_STATES = {"down", "strong_down"}


def _finite(value: float | int | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    result = float(value)
    return round(result, digits) if math.isfinite(result) else None


def _as_of_datetime(generated_at: str | None, now: datetime | None) -> datetime:
    if now is not None:
        return now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if generated_at:
        try:
            parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _dashboard_observed_at(dashboard: dict[str, Any], generated_at: datetime) -> datetime:
    candidates: list[datetime] = []
    for panel in dashboard.values():
        if not isinstance(panel, dict):
            continue
        raw = panel.get("asOf")
        if not isinstance(raw, str) or not raw:
            continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        normalized = parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        if normalized <= generated_at:
            candidates.append(normalized)
    return max(candidates) if candidates else generated_at


def _bar_date(timestamp: int) -> date:
    # MarketStore normalizes daily/weekly dates to midnight UTC; interpreting them in
    # Eastern would shift every date backward during the US session.
    return datetime.fromtimestamp(timestamp, timezone.utc).date()


def _daily_complete(bar_date: date, as_of: datetime) -> bool:
    eastern = as_of.astimezone(_EASTERN)
    if bar_date < eastern.date():
        return True
    if bar_date > eastern.date():
        return False
    return eastern.time() >= time(16, 15)


def _weekly_complete(bar_date: date, as_of: datetime) -> bool:
    eastern = as_of.astimezone(_EASTERN)
    week_end = bar_date + timedelta(days=4)
    return eastern.date() > week_end or (eastern.date() == week_end and eastern.time() >= time(16, 15))


def _frame(store: MarketStore, symbol: str, timeframe: str, as_of: datetime) -> pd.DataFrame:
    rows = [bar for bar in store.load_bars(symbol, timeframe) if _bar_date(bar.t) <= as_of.astimezone(_EASTERN).date()]
    if not rows:
        return pd.DataFrame(columns=["timestamp", "date", "open", "high", "low", "close", "volume"])
    return pd.DataFrame(
        {
            "timestamp": [bar.t for bar in rows],
            "date": [pd.Timestamp(_bar_date(bar.t)) for bar in rows],
            "open": [bar.o for bar in rows],
            "high": [bar.h for bar in rows],
            "low": [bar.l for bar in rows],
            "close": [bar.c for bar in rows],
            "volume": [bar.v for bar in rows],
        }
    ).sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def _return(close: pd.Series, periods: int) -> float | None:
    if len(close) <= periods or not float(close.iloc[-1 - periods]):
        return None
    return _finite((float(close.iloc[-1]) / float(close.iloc[-1 - periods]) - 1) * 100)


def _instrument(store: MarketStore, symbol: str, role: str, as_of: datetime) -> TapeInstrument | None:
    frame = _frame(store, symbol, "daily", as_of)
    if frame.empty:
        return None
    close = frame["close"].astype(float)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(14, min_periods=14).mean().replace(0, math.nan)
    volume = frame["volume"].astype(float)
    volume_average = volume.rolling(20, min_periods=20).mean().replace(0, math.nan)
    returns = close.pct_change()
    ma20 = close.rolling(20, min_periods=20).mean()
    ma50 = close.rolling(50, min_periods=50).mean()

    bars: list[TapeBar] = []
    for index, row in frame.tail(MARKET_TAPE_BAR_WINDOW).iterrows():
        row_atr = float(atr.iloc[index]) if pd.notna(atr.iloc[index]) else None
        candle_range = float(row["high"] - row["low"])
        open_, high, low, close_ = (float(row[key]) for key in ("open", "high", "low", "close"))
        geometry_valid = low <= min(open_, close_) <= max(open_, close_) <= high
        bars.append(
            TapeBar(
                date=str(pd.Timestamp(row["date"]).date()),
                timestamp=int(row["timestamp"]),
                complete=_daily_complete(pd.Timestamp(row["date"]).date(), as_of),
                geometry_valid=geometry_valid,
                open=_finite(open_, 6) or 0.0,
                high=_finite(high, 6) or 0.0,
                low=_finite(low, 6) or 0.0,
                close=_finite(close_, 6) or 0.0,
                volume=int(row["volume"]),
                return_pct=_finite(float(returns.iloc[index]) * 100) if pd.notna(returns.iloc[index]) else None,
                gap_pct=(
                    _finite((open_ / float(previous_close.iloc[index]) - 1) * 100)
                    if geometry_valid and pd.notna(previous_close.iloc[index]) and previous_close.iloc[index]
                    else None
                ),
                range_atr=_finite(candle_range / row_atr) if geometry_valid and row_atr else None,
                body_atr=_finite(abs(close_ - open_) / row_atr) if geometry_valid and row_atr else None,
                upper_wick_atr=(
                    _finite((high - max(open_, close_)) / row_atr) if geometry_valid and row_atr else None
                ),
                lower_wick_atr=(
                    _finite((min(open_, close_) - low) / row_atr) if geometry_valid and row_atr else None
                ),
                close_location_pct=(
                    _finite((close_ - low) / candle_range * 100) if geometry_valid and candle_range else None
                ),
                volume_vs_20d=_finite(float(volume.iloc[index]) / float(volume_average.iloc[index])) if pd.notna(volume_average.iloc[index]) else None,
            )
        )

    last_atr = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else None
    last_close = float(close.iloc[-1])
    realized = returns.tail(20).std() * math.sqrt(252) * 100
    summary = TapeSummary(
        return_1d_pct=_return(close, 1),
        return_2d_pct=_return(close, 2),
        return_5d_pct=_return(close, 5),
        atr_pct=_finite(last_atr / last_close * 100) if last_atr and last_close else None,
        realized_vol_20d_pct=_finite(float(realized)) if pd.notna(realized) else None,
        dist_ma20_atr=_finite((last_close - float(ma20.iloc[-1])) / last_atr) if last_atr and pd.notna(ma20.iloc[-1]) else None,
        dist_ma50_atr=_finite((last_close - float(ma50.iloc[-1])) / last_atr) if last_atr and pd.notna(ma50.iloc[-1]) else None,
        volume_vs_20d=_finite(float(volume.iloc[-1]) / float(volume_average.iloc[-1])) if pd.notna(volume_average.iloc[-1]) else None,
    )
    return TapeInstrument(
        symbol=symbol,
        role=role,
        timeframe="daily",
        price_basis=MARKET_BAR_PRICE_BASIS,
        latest_bar_complete=bars[-1].complete,
        summary=summary,
        bars=bars,
    )


def _trend_observations(store: MarketStore, symbols: tuple[str, ...], as_of: datetime) -> list[TrendObservation]:
    observations: list[TrendObservation] = []
    for symbol in symbols:
        frame = _frame(store, symbol, "weekly", as_of)
        if frame.empty:
            continue
        latest_date = pd.Timestamp(frame["date"].iloc[-1]).date()
        trend = classify_trend(frame, symbol=symbol, as_of=str(latest_date))
        observations.append(
            TrendObservation(
                symbol=symbol,
                state=trend.state,
                prior_state=trend.prior_state,
                weeks_in_state=trend.weeks_in_state,
                slope_40_atr=trend.slope40_atr,
                distance_40_atr=trend.dist40_atr,
                current_week_complete=_weekly_complete(latest_date, as_of),
            )
        )
    return observations


def _state_counts(rows: list[TrendObservation]) -> tuple[int, int, int]:
    positive = sum(row.state in _POSITIVE_TREND_STATES for row in rows)
    negative = sum(row.state in _NEGATIVE_TREND_STATES for row in rows)
    return positive, negative, len(rows) - positive - negative


def _rrg_observations(dashboard: dict[str, Any]) -> list[RrgObservation]:
    observations: list[RrgObservation] = []
    for panel_key, group in (("rrg", "sector"), ("industryRrg", "industry")):
        rows = ((dashboard.get(panel_key) or {}).get("data") or [])
        for row in rows:
            modes: dict[str, RrgVector] = {}
            tails = row.get("tails") or {"default": row.get("tail") or []}
            for mode, tail in tails.items():
                if not isinstance(tail, list) or not tail:
                    continue
                last = tail[-1]
                previous = tail[-2] if len(tail) > 1 else None
                x, y = float(last.get("x") or 0), float(last.get("y") or 0)
                dx = x - float(previous.get("x") or 0) if previous else None
                dy = y - float(previous.get("y") or 0) if previous else None
                modes[str(mode)] = RrgVector(
                    x=_finite(x) or 0.0,
                    y=_finite(y) or 0.0,
                    delta_x=_finite(dx),
                    delta_y=_finite(dy),
                    velocity=_finite(math.hypot(dx, dy)) if dx is not None and dy is not None else None,
                )
            observations.append(
                RrgObservation(
                    symbol=str(row.get("symbol") or ""),
                    group=group,
                    quadrant=str(row.get("quadrant") or "unknown"),
                    modes=modes,
                )
            )
    return observations


def _summary_by_symbol(instruments: list[TapeInstrument]) -> dict[str, TapeSummary]:
    return {item.symbol: item.summary for item in instruments}


def _excess(summaries: dict[str, TapeSummary], symbol: str, benchmark: str) -> float | None:
    left = summaries.get(symbol)
    right = summaries.get(benchmark)
    if not left or not right or left.return_5d_pct is None or right.return_5d_pct is None:
        return None
    return _finite(left.return_5d_pct - right.return_5d_pct)


def build_market_tape(
    store: MarketStore,
    dashboard: dict[str, Any],
    *,
    generated_at: str | None = None,
    now: datetime | None = None,
) -> MarketTapePacket:
    """Build one immutable point-in-time packet using only already-persisted market data."""
    created_at = _as_of_datetime(generated_at, now)
    observed_at = _dashboard_observed_at(dashboard, created_at)
    stamp = generated_at or created_at.isoformat().replace("+00:00", "Z")
    observation_stamp = observed_at.isoformat().replace("+00:00", "Z")
    instruments = [
        item
        for symbol, role in TAPE_INSTRUMENTS
        if (item := _instrument(store, symbol, role, observed_at))
    ]
    summaries = _summary_by_symbol(instruments)
    index_states = _trend_observations(store, INDEX_PARTICIPATION_SYMBOLS, observed_at)
    sector_states = _trend_observations(store, SECTOR_SYMBOLS, observed_at)
    index_counts = _state_counts(index_states)
    sector_counts = _state_counts(sector_states)
    participation = ParticipationSnapshot(
        index_positive=index_counts[0],
        index_negative=index_counts[1],
        index_transition=index_counts[2],
        sector_positive=sector_counts[0],
        sector_negative=sector_counts[1],
        sector_transition=sector_counts[2],
        equal_weight_excess_5d_pct=_excess(summaries, "RSP", "VOO"),
        small_cap_excess_5d_pct=_excess(summaries, "IWM", "VOO"),
        index_states=index_states,
        sector_states=sector_states,
    )
    risk = RiskPlumbingSnapshot(
        high_yield_excess_5d_pct=_excess(summaries, "HYG", "LQD"),
        volatility_1d_pct=summaries.get("VIX").return_1d_pct if summaries.get("VIX") else None,
        volatility_5d_pct=summaries.get("VIX").return_5d_pct if summaries.get("VIX") else None,
        long_duration_5d_pct=summaries.get("TLT").return_5d_pct if summaries.get("TLT") else None,
        dollar_5d_pct=summaries.get("DXY").return_5d_pct if summaries.get("DXY") else None,
        gold_5d_pct=summaries.get("GLD").return_5d_pct if summaries.get("GLD") else None,
    )
    available = {item.symbol for item in instruments}
    missing = [symbol for symbol, _ in TAPE_INSTRUMENTS if symbol not in available]
    incomplete_daily = [item.symbol for item in instruments if not item.latest_bar_complete]
    incomplete_weekly = [row.symbol for row in [*index_states, *sector_states] if not row.current_week_complete]
    malformed_daily = sorted(
        item.symbol for item in instruments if any(not bar.geometry_valid for bar in item.bars)
    )
    source_age_minutes = max((created_at - observed_at).total_seconds() / 60, 0)
    warnings: list[str] = []
    if incomplete_daily:
        warnings.append("Current-session daily bars are partial; volume ratios and candle geometry can change before the close.")
    if incomplete_weekly:
        warnings.append("Current weekly bars are partial; structural trend states can change before Friday's close.")
    if missing:
        warnings.append("Some required public instruments were unavailable; interpret the missing lens as lower coverage, never as neutral.")
    if malformed_daily:
        warnings.append(
            "Some stored OHLC rows violate high/low bounds; their candle geometry and gap features were suppressed."
        )
    if source_age_minutes > 30:
        warnings.append(
            "The market snapshot predates packet generation; interpret it as the stated observation, not current intraday conditions."
        )
    # This is a common-coverage watermark, not the freshest date seen anywhere.  Taking
    # the maximum would overstate packet freshness whenever one required lens lags.
    completed_dates = [
        max(bar.date for bar in item.bars if bar.complete)
        for item in instruments
        if any(bar.complete for bar in item.bars)
    ]
    quality = TapeDataQuality(
        required_symbols=len(TAPE_INSTRUMENTS),
        available_symbols=len(instruments),
        missing_symbols=missing,
        potentially_incomplete_daily_symbols=incomplete_daily,
        potentially_incomplete_weekly_symbols=sorted(set(incomplete_weekly)),
        malformed_daily_symbols=malformed_daily,
        source_age_minutes=round(source_age_minutes, 1),
        warnings=warnings,
    )
    return MarketTapePacket(
        schema_version=MARKET_TAPE_SCHEMA_VERSION,
        generated_at=stamp,
        observed_at=observation_stamp,
        completed_through=min(completed_dates) if completed_dates else None,
        price_basis=MARKET_BAR_PRICE_BASIS,
        instruments=instruments,
        participation=participation,
        rrg=_rrg_observations(dashboard),
        risk_plumbing=risk,
        data_quality=quality,
    )
