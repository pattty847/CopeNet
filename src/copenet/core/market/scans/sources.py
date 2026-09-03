"""Source-specific, paced acquisition. No source can implicitly acquire another."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from copenet.core._json_store import read_json, write_json_atomic
from ..economic_calendar import load_economic_calendar
from ..edgar import fetch_ticker_evidence, _sec_fetcher_class
from ..financials import get_financial_series
from ..yield_curve import fetch_treasury_yield_curve

MAX_AGE = {"prices": 900, "sec": 3600, "financials": 86400, "rates": 3600, "calendar": 900}


def fresh(stamp: str, seconds: int, now: datetime) -> bool:
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return 0 <= (now - moment).total_seconds() < seconds
    except (ValueError, TypeError):
        return False


def price_cache_is_fresh(history, now: datetime, *, max_age_seconds=MAX_AGE["prices"]) -> bool:
    if history is None or not fresh(history.updated_at, max_age_seconds, now):
        return False
    from ..alert_candles import _calendar
    calendar = _calendar(now.year - 1, now.year + 1)
    recent = calendar.schedule.loc[(now.date() - timedelta(days=7)).isoformat():now.date().isoformat()]
    closed = recent[recent["close"] <= now]
    if closed.empty:
        return True
    # A cache fetched just before a regular/early close contains a forming tail even
    # when the ordinary 15-minute TTL says fresh. A post-close scan must fetch again.
    return datetime.fromisoformat(history.updated_at) >= closed.iloc[-1]["close"].to_pydatetime()


class ScanSources:
    def __init__(self, runtime):
        self.runtime = runtime
        self.root = runtime.store.root_dir / "scans" / "sources"

    def cached(self, source: str, symbol: str, now: datetime, *, since=None) -> dict | None:
        # Jobs admitted at the same slot can wait behind a large sweep. Reuse work
        # acquired since that slot even if the ordinary interactive TTL elapsed.
        max_age = max(MAX_AGE[source], (now - since).total_seconds() + 1) if since else MAX_AGE[source]
        if source == "prices":
            history = self.runtime.prices.load(symbol)
            return {"updatedAt": history.updated_at} if price_cache_is_fresh(history, now, max_age_seconds=max_age) else None
        result = read_json(self.root / source / f"{symbol}.json", None)
        return result if result and fresh(result["updatedAt"], max_age, now) else None

    async def acquire(self, source: str, symbol: str) -> dict:
        import asyncio
        if source == "prices":
            now = datetime.now(timezone.utc)
            current = self.runtime.prices.load(symbol)
            max_age = MAX_AGE[source] if price_cache_is_fresh(current, now) else 0
            history = await asyncio.to_thread(self.runtime.prices.refresh, symbol, max_age_seconds=max_age)
            if not price_cache_is_fresh(history, datetime.now(timezone.utc)):
                raise RuntimeError("Price refresh returned no fresh history; retained the previous cache")
            # Feed existing ledger and dashboard consumers without triggering another fetch.
            for timeframe, limit in (("daily", 126), ("weekly", 261)):
                bars = self.runtime._cache_bars(symbol, timeframe, limit)
                if bars:
                    self.runtime.store.save_bars(symbol, timeframe, bars)
            return {"updatedAt": history.updated_at, "bars": len(history.bars)}
        if source == "sec":
            if _sec_fetcher_class() is None:
                raise RuntimeError("CopeTech SEC adapter is unavailable")
            payload = (await fetch_ticker_evidence(symbol, days_back=30)).to_wire()
            if payload.get("warnings"):
                payload["error"] = "; ".join(payload["warnings"])
        elif source == "financials":
            series = {}
            for metric in ("revenue", "diluted_eps"):
                series[metric] = await get_financial_series(symbol=symbol, metric=metric, frequency="quarterly")
            payload = {"series": series}
            unavailable = [metric for metric, result in series.items() if result is None]
            if unavailable:
                payload["error"] = "Financial series unavailable: " + ", ".join(unavailable)
        elif source == "rates":
            payload = await asyncio.to_thread(fetch_treasury_yield_curve)
        elif source == "calendar":
            payload = await load_economic_calendar(self.runtime.store.root_dir)
            if not payload.get("configured"):
                payload["error"] = "Calendar requires TRADING_ECONOMICS_API_KEY"
        else:
            raise ValueError("Unknown source")
        result = {"updatedAt": datetime.now(timezone.utc).isoformat(), "payload": payload}
        # Failed/partial responses remain in the run, never replace a successful source cache.
        if not payload.get("error"):
            write_json_atomic(self.root / source / f"{symbol}.json", result)
        return result
