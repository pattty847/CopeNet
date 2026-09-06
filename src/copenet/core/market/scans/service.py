"""One coordinator for scheduled/manual scans with durable scope and partial results."""
from __future__ import annotations

import asyncio
import logging
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from .definitions import SOURCES, next_run_at, validate_scan
from .resolver import resolve_scope
from .sources import ScanSources
from .store import ScanStore, file_lock, execution_lease

_LOG = logging.getLogger(__name__)


async def finish_inflight(awaitable):
    """Keep the process lease until already-started worker I/O actually finishes."""
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        except Exception:
            pass
        raise


class ScanService:
    def __init__(self, runtime, *, sources=None, post_prices=None, forecast_prices=None, provider=None, pulse_store=None, pace=0.25):
        self.runtime = runtime
        self.store = ScanStore(runtime.store.root_dir, runtime.watchlists)
        self.sources = sources or ScanSources(runtime)
        self.post_prices = post_prices
        self.forecast_prices = forecast_prices
        self.provider = provider
        self.pulse_store = pulse_store
        self.pace = max(0.0, pace)
        self.tasks: set[asyncio.Task] = set()
        try:
            with file_lock(self.store.root / "execution.lock", blocking=False):
                for run in self.store.runs():
                    if run["status"] == "running":
                        run.update(status="interrupted", finishedAt=datetime.now(timezone.utc).isoformat())
                        self.store.save_run(run)
        except ValueError:
            pass  # Another process still owns these running records.

    def preview(self, scan: dict, *, now=None, work_cache=None, watchlists=None, resolved_scope=None) -> dict:
        scan = validate_scan(scan)
        now = now or datetime.now(timezone.utc)
        work_cache = work_cache if work_cache is not None else {}
        watchlists = watchlists if watchlists is not None else self.runtime.watchlists.scan_lists()
        scope = dict(resolved_scope) if resolved_scope is not None else resolve_scope(scan, watchlists)
        assets = scope.pop("assets")
        issuer_symbols = {asset.symbol for asset in assets if asset.role not in {"index", "sector", "industry", "macro"}}
        work = []
        notes = []
        for source in scan["sources"]:
            symbols = scope["resolvedSymbols"] + (scope["contextSymbols"] if source == "prices" else [])
            if source in ("sec", "financials"):
                omitted = [symbol for symbol in symbols if symbol not in issuer_symbols]
                symbols = [symbol for symbol in symbols if symbol in issuer_symbols]
                if omitted:
                    notes.append(f"{source}: skips {len(omitted)} known fund/index/macro instruments; issuer filings only")
            if source in ("rates", "calendar"):
                symbols = ["global"]
            for symbol in symbols:
                key = (source, symbol)
                if key not in work_cache:
                    cached = self.sources.cached(source, symbol, now)
                    initial = not cached and source == "prices" and self.runtime.prices.load(symbol) is None
                    work_cache[key] = "cached" if cached else "initial" if initial else "fetch"
                work.append({"source": source, "symbol": symbol, "status": work_cache[key]})
        upcoming = next_run_at(scan, now)
        if not work:
            scope["issues"].append("No supported source work for the selected assets")
        scope_token = hashlib.sha256(json.dumps({"scan": scan, "resolvedSymbols": scope["resolvedSymbols"], "contextSymbols": scope["contextSymbols"]}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {**scope, "scopeToken": scope_token, "work": work, "notes": notes, "cacheHits": sum(row["status"] == "cached" for row in work),
                "fetchSymbols": list(dict.fromkeys(row["symbol"] for row in work if row["status"] != "cached")),
                "nextRunAt": upcoming.isoformat() if upcoming else None}

    def state(self) -> dict:
        from ..sentinel import sentinel_enabled
        runs = self.store.run_summaries()
        scans = []
        work_cache = {}
        watchlists = self.runtime.watchlists.scan_lists()
        now = datetime.now(timezone.utc)
        for scan in self.store.definitions():
            preview = self.preview(scan, now=now, work_cache=work_cache, watchlists=watchlists)
            scans.append({**scan, **preview, "nextRunAt": preview["nextRunAt"] if not preview["issues"] and sentinel_enabled() else None,
                          "lastRun": next((r for r in runs if r["scanId"] == scan["id"]), None)})
        upcoming = sorted((s["nextRunAt"], s["id"]) for s in scans if s["nextRunAt"])
        return {"scans": scans, "runs": runs, "sources": SOURCES,
                "watchlists": [{"name": w["name"], "symbols": [e["symbol"] for e in w["entries"]]} for w in watchlists],
                "nextRunAt": upcoming[0][0] if upcoming else None, "nextScanId": upcoming[0][1] if upcoming else None,
                "schedulerEnabled": sentinel_enabled()}

    async def run(self, identifier: str, *, reason="manual", scheduled_at=None, expected_revision=None, expected_scope_token=None) -> dict:
        # Separate handles plus flock protects threads, independent hosts and manual/scheduled work.
        async with execution_lease(self.store.root / "execution.lock", wait=reason == "scheduled"):
            scan = self.store.get(identifier)
            if expected_revision is not None and scan["revision"] != expected_revision:
                raise ValueError("Scheduled definition changed while queued; waiting for its new schedule")
            if reason == "scheduled" and not scan["enabled"]:
                raise ValueError("Scan is paused")
            if scheduled_at and any(r.get("scheduledAt") == scheduled_at and r["scanId"] == identifier for r in self.store.runs(1000)):
                raise ValueError("This scheduled occurrence has already run")
            scope = resolve_scope(scan, self.runtime.watchlists.scan_lists())
            plan = self.preview(scan, resolved_scope=scope)
            if plan["issues"]:
                raise ValueError("; ".join(plan["issues"]))
            if expected_scope_token is not None and expected_scope_token != plan["scopeToken"]:
                raise ValueError("Scan scope changed after preview; review its current assets and work before running")
            now = datetime.now(timezone.utc).isoformat()
            run = {"id": uuid4().hex, "scanId": identifier, "name": scan["name"], "revision": scan["revision"],
                   "definition": scan, "reason": reason, "scheduledAt": scheduled_at, "startedAt": now, "finishedAt": None,
                   "status": "running", "resolvedSymbols": plan["resolvedSymbols"], "contextSymbols": plan["contextSymbols"],
                   "sources": scan["sources"], "cacheHits": 0, "fetched": 0, "errors": [], "results": [], "triggerEvents": []}
            run["assets"] = [asset.to_wire() for asset in scope["assets"]]
            self.store.save_run(run)
            try:
                for work in plan["work"]:
                    source, symbol = work["source"], work["symbol"]
                    try:
                        # Recheck after taking the process lock: overlapping jobs reuse fresh work.
                        cache_window = {"since": datetime.fromisoformat(scheduled_at)} if scheduled_at else {}
                        cached = self.sources.cached(source, symbol, datetime.now(timezone.utc), **cache_window)
                        result = cached or await finish_inflight(self.sources.acquire(source, symbol))
                        run["cacheHits" if cached else "fetched"] += 1
                        error = result.get("payload", {}).get("error")
                        if error:
                            run["errors"].append({"source": source, "symbol": symbol, "message": error})
                        run["results"].append({"source": source, "symbol": symbol, "cached": bool(cached), **result})
                    except Exception as exc:
                        run["errors"].append({"source": source, "symbol": symbol, "message": str(exc)[:300]})
                    self.store.save_run(run)
                    if self.pace and work["status"] != "cached":
                        await asyncio.sleep(self.pace)
                if "prices" in scan["sources"]:
                    try:
                        from ..alert_engine import evaluate_scan_alerts
                        self._screens(run)
                        run["triggerEvents"] = await finish_inflight(asyncio.to_thread(evaluate_scan_alerts, self.runtime, identifier, plan["resolvedSymbols"]))
                    except Exception as exc:
                        run["errors"].append({"source": "alerts", "symbol": "", "message": str(exc)[:300]})
                    if self.forecast_prices:
                        try:
                            run["forecastResults"] = await self.forecast_prices(identifier, plan["resolvedSymbols"])
                        except Exception as exc:
                            run["errors"].append({"source": "forecasts", "symbol": "", "message": str(exc)[:300]})
                    if self.post_prices and run["triggerEvents"]:
                        try:
                            await self.post_prices(run["triggerEvents"])
                        except Exception as exc:
                            run["errors"].append({"source": "delivery", "symbol": "", "message": str(exc)[:300]})
                if scan["publishBrief"]:
                    await self._publish(scan, run)
                run["status"] = "partial" if run["errors"] else "completed"
            except asyncio.CancelledError:
                run["status"] = "interrupted"
                raise
            except Exception as exc:
                run["errors"].append({"source": "processing", "symbol": "", "message": str(exc)[:300]})
                run["status"] = "partial" if run["results"] else "failed"
            finally:
                run["finishedAt"] = datetime.now(timezone.utc).isoformat()
                self.store.save_run(run)
            return run

    def _screens(self, run):
        from ..runtime import _bars_to_frame
        from ..mama_regime import mama_regime
        from ..signals import compute_price_signals
        benchmark = _bars_to_frame(self.runtime._cache_bars("VOO", "weekly", 261))
        screens = []
        failed = {row["symbol"] for row in run["errors"] if row["source"] == "prices"}
        for symbol in run["resolvedSymbols"]:
            frame = _bars_to_frame(self.runtime._cache_bars(symbol, "weekly", 261))
            if symbol in failed or frame.empty:
                continue
            signals = compute_price_signals(frame, benchmark=benchmark, mama_regime=mama_regime(frame))
            self.runtime.store.save_signals(symbol, signals.__dict__)
            screens.append({"symbol": symbol, "signals": signals.__dict__})
        run["screens"] = screens

    async def _publish(self, scan, run):
        from ..models import EvidenceItem, UniverseAsset, MarketPanel
        from ..dashboard_runtime import project_cached_dashboard
        from ..runtime import _bars_to_frame, _evidence_from_dashboard
        from .publishing import publish_brief
        symbols = run["resolvedSymbols"] + run["contextSymbols"]
        weekly = {symbol: _bars_to_frame(self.runtime._cache_bars(symbol, "weekly", 261)) for symbol in symbols}
        daily = {symbol: _bars_to_frame(self.runtime._cache_bars(symbol, "daily", 126)) for symbol in symbols}
        evidence = []
        for result in run["results"]:
            if result["source"] == "sec":
                counts = {}
                for row in result.get("payload", {}).get("evidence", []):
                    if row["type"] == "8-K" and row.get("flag") != "high-signal":
                        continue
                    bucket = "cluster" if row.get("flag") == "cluster" else row["type"]
                    counts[bucket] = counts.get(bucket, 0) + 1
                    if counts[bucket] > (1 if bucket in {"cluster", "Form 144"} else 2):
                        continue
                    evidence.append(EvidenceItem(**{k: v for k, v in row.items() if k in EvidenceItem.__dataclass_fields__}))
        previous = self.runtime.store.load_dashboard_wire()
        failed_evidence = {error["symbol"] for error in run["errors"] if error["source"] == "sec"}
        evidence.extend(item for item in _evidence_from_dashboard(previous) if item.symbol in failed_evidence)
        failed_prices = {error["symbol"] for error in run["errors"] if error["source"] == "prices"}
        if failed_prices:
            # A coherent previous snapshot is more honest than stamping mixed old/new
            # bars as a new market read. Successful source work remains in its run/cache.
            dashboard = project_cached_dashboard(previous)
            for name in ("briefing", "regime", "macro", "rrg", "industry_rrg", "accumulation", "trend", "soft_bottoming", "speculative", "contrarian"):
                panel = getattr(dashboard, name)
                panel.status = "stale"
                panel.note = "Price scan incomplete; retaining the last coherent market snapshot"
            dashboard.evidence = MarketPanel(status="stale" if failed_evidence else "live", data=evidence,
                as_of=datetime.now(timezone.utc).isoformat(), note="Partial SEC refresh; retained prior evidence" if failed_evidence else None)
            self.runtime.store.save_dashboard(dashboard)
            run["errors"].append({"source": "publishing", "symbol": "", "message": "Morning brief and model read unchanged because the price scan was incomplete"})
            return
        dashboard = await finish_inflight(asyncio.to_thread(self.runtime._assemble_dashboard, weekly=weekly, daily=daily, universe=tuple(UniverseAsset(**asset) for asset in run["assets"]), evidence=evidence))
        if failed_evidence:
            dashboard.evidence.status = "stale"
            dashboard.evidence.note = "Partial SEC refresh; retaining prior evidence for unavailable assets"
        self.runtime.store.save_dashboard(dashboard)
        run["brief"] = await publish_brief(self.runtime, previous, self.provider if scan["interpret"] else None, self.pulse_store, universe=tuple(UniverseAsset(**asset) for asset in run["assets"]))


def resolve_scan_service(orchestrator) -> ScanService:
    from functools import partial
    from ..monitoring_delivery import on_scan_alert_events
    from ..forecasts.tracking import on_forecast_prices
    from ..runtime import resolve_market_runtime
    service = getattr(orchestrator, "_market_scan_service", None)
    if service is None:
        providers = getattr(orchestrator, "_providers", {})
        service = ScanService(resolve_market_runtime(orchestrator), provider=providers.get("openai-codex"),
                              pulse_store=getattr(orchestrator, "_pulse_store", None),
                              post_prices=partial(on_scan_alert_events, orchestrator),
                              forecast_prices=partial(on_forecast_prices, orchestrator))
        orchestrator._market_scan_service = service
    return service
