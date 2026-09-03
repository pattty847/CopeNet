"""Offline scan control contracts with isolated stores and injected source I/O."""
from datetime import datetime, timezone
import asyncio
import pytest

from copenet.core.market.runtime import MarketRuntime
from copenet.core.market.store import MarketStore
from copenet.core.market.scans.service import ScanService
from copenet.core.market.scans.store import file_lock


class Sources:
    def __init__(self):
        self.cache = {}
        self.calls = []
        self.fail = set()
    def cached(self, source, symbol, now, **kwargs):
        return self.cache.get((source, symbol))
    async def acquire(self, source, symbol):
        self.calls.append((source, symbol))
        if symbol in self.fail:
            raise RuntimeError("Synthetic provider outage")
        result = {"updatedAt": datetime.now(timezone.utc).isoformat(), "payload": {"evidence": []}}
        self.cache[source, symbol] = result
        return result


@pytest.fixture
def service(tmp_path):
    return ScanService(MarketRuntime(store=MarketStore(tmp_path)), sources=Sources(), pace=0)


def focused(service, **changes):
    return service.store.save({"name": "Focused", "symbols": ["TEST"], "sources": ["sec"], **changes})


def test_migrates_once_and_never_refetches_on_state(service, monkeypatch):
    original = service.store.get("morning")
    monkeypatch.setenv("COPNET_MARKET_BRIEF_TIME", "17:30")
    assert service.store.get("morning") == original
    assert service.state()["scans"]
    assert service.sources.calls == []


def test_scope_deduplicates_and_reports_missing_lists(service):
    service.runtime.watchlists.add("TEST")
    service.runtime.watchlists.add("OTHER")
    scan = focused(service, watchlists=["Default"], excludeSymbols=["OTHER"])
    preview = service.preview(scan)
    assert preview["resolvedSymbols"] == ["TEST"]
    assert len(preview["inclusions"][0]["reasons"]) == 2
    scan["watchlists"] = ["Gone"]
    assert "removed or renamed" in service.preview(scan)["issues"][0]


def test_revisions_and_archive_preserve_history(service):
    scan = focused(service)
    paused = service.store.save({**scan, "enabled": False})
    assert service.preview(paused)["nextRunAt"] is None
    with pytest.raises(ValueError, match="another window"):
        service.store.save(scan)
    service.store.archive(scan["id"])
    with pytest.raises(ValueError, match="not found"):
        service.store.get(scan["id"])
    assert list((service.store.root / "archived").glob("*.json"))


@pytest.mark.asyncio
async def test_sec_only_never_fetches_prices_or_replaces_dashboard(service, monkeypatch):
    monkeypatch.setattr(service.runtime.prices, "refresh", lambda *a, **kw: pytest.fail("Yahoo fetch"))
    before = service.runtime.store.load_dashboard_wire()
    run = await service.run(focused(service)["id"])
    assert run["status"] == "completed"
    assert service.sources.calls == [("sec", "TEST")]
    assert service.runtime.store.load_dashboard_wire() == before


@pytest.mark.asyncio
async def test_overlapping_jobs_reuse_source_cache_and_partial_results_survive(service):
    scan = focused(service, symbols=["TEST", "OTHER"])
    service.sources.fail.add("OTHER")
    first = await service.run(scan["id"])
    assert first["status"] == "partial"
    assert first["results"][0]["symbol"] == "TEST"
    second = await service.run(scan["id"])
    assert second["cacheHits"] == 1
    assert service.sources.calls.count(("sec", "TEST")) == 1
    assert len(service.store.runs()) == 2


@pytest.mark.asyncio
async def test_cross_process_lock_excludes_even_separate_service(service):
    scan = focused(service)
    other = ScanService(service.runtime, sources=Sources(), pace=0)
    with file_lock(service.store.root / "execution.lock"):
        with pytest.raises(ValueError, match="Another market scan"):
            await other.run(scan["id"])
    assert other.sources.calls == []


@pytest.mark.asyncio
async def test_same_scheduled_slot_cannot_run_twice(service):
    scan = focused(service)
    await service.run(scan["id"], reason="scheduled", scheduled_at="2026-09-03T13:45:00+00:00")
    with pytest.raises(ValueError, match="already run"):
        await service.run(scan["id"], reason="scheduled", scheduled_at="2026-09-03T13:45:00+00:00")


def test_preview_global_work_and_context_are_explicit(service):
    scan = focused(service, sources=["prices", "rates"])
    preview = service.preview(scan)
    assert preview["resolvedSymbols"] == ["TEST"]
    assert preview["contextSymbols"] == ["VOO"]
    assert preview["fetchSymbols"] == ["TEST", "VOO", "global"]
    assert preview["work"][0]["status"] == "initial"


@pytest.mark.parametrize("changes", [{"sources": ["unknown"]}, {"timezone": "bad"}, {"times": ["25:00"]}, {"symbols": ["../bad"]}, {"interpret": True}, {"publishBrief": True}])
def test_invalid_definition_cannot_be_saved(service, changes):
    with pytest.raises(ValueError):
        focused(service, **changes)


@pytest.mark.asyncio
async def test_source_adapters_keep_financials_and_sec_independent_of_prices(service, monkeypatch):
    from copenet.core.market.scans import sources as module
    from copenet.core.market.scans.sources import ScanSources
    from copenet.core.market.models import TickerEvidencePayload
    calls = []
    async def statements(**kwargs):
        calls.append(kwargs)
        return {"observations": []}
    async def evidence(symbol, **kwargs):
        return TickerEvidencePayload(symbol, [], [], "2026-09-03", False)
    monkeypatch.setattr(service.runtime.prices, "refresh", lambda *a, **kw: pytest.fail("Yahoo requested by SEC-only source"))
    monkeypatch.setattr(module, "get_financial_series", statements)
    monkeypatch.setattr(module, "fetch_ticker_evidence", evidence)
    monkeypatch.setattr(module, "_sec_fetcher_class", lambda: object)
    adapter = ScanSources(service.runtime)
    await adapter.acquire("financials", "TEST")
    await adapter.acquire("sec", "TEST")
    assert [call["metric"] for call in calls] == ["revenue", "diluted_eps"]
    assert all(call["frequency"] == "quarterly" for call in calls)
    assert adapter.cached("sec", "TEST", datetime.now(timezone.utc)) is not None


@pytest.mark.asyncio
async def test_failed_source_does_not_replace_good_source_cache(service, monkeypatch):
    from copenet.core.market.scans import sources as module
    from copenet.core.market.scans.sources import ScanSources
    from copenet.core.market.models import TickerEvidencePayload
    warning = []
    async def evidence(symbol, **kwargs):
        return TickerEvidencePayload(symbol, [], [], "2026-09-03", False, warnings=list(warning))
    monkeypatch.setattr(module, "fetch_ticker_evidence", evidence)
    monkeypatch.setattr(module, "_sec_fetcher_class", lambda: object)
    adapter = ScanSources(service.runtime)
    original = await adapter.acquire("sec", "TEST")
    warning.append("SEC temporarily unavailable")
    failed = await adapter.acquire("sec", "TEST")
    assert failed["payload"]["error"] == warning[0]
    assert adapter.cached("sec", "TEST", datetime.now(timezone.utc)) == original


@pytest.mark.asyncio
async def test_cancellation_keeps_partial_results_and_marks_interrupted(service):
    scan = focused(service, symbols=["TEST", "OTHER"])
    original = service.sources.acquire
    async def cancel(source, symbol):
        if symbol == "OTHER":
            raise asyncio.CancelledError
        return await original(source, symbol)
    service.sources.acquire = cancel
    with pytest.raises(asyncio.CancelledError):
        await service.run(scan["id"])
    saved = service.store.runs()[0]
    assert saved["status"] == "interrupted"
    assert saved["results"][0]["symbol"] == "TEST"


def test_crash_record_is_recovered_without_replaying_fetches(service):
    service.store.save_run({"id": "test", "scanId": "morning", "status": "running", "startedAt": "2026-09-03T09:45:00+00:00"})
    restarted = ScanService(service.runtime, sources=Sources(), pace=0)
    assert restarted.store.runs()[0]["status"] == "interrupted"
    assert restarted.sources.calls == []


@pytest.mark.asyncio
async def test_morning_publication_uses_acquired_sources_without_hidden_second_sweep(service, monkeypatch):
    from copenet.core.market import dashboard_runtime
    monkeypatch.setattr(dashboard_runtime, "load_webull_snapshot", lambda: None)
    async def forbidden(*args, **kwargs):
        pytest.fail("Dashboard projection requested SEC evidence independently")
    monkeypatch.setattr(dashboard_runtime, "fetch_evidence", forbidden)
    monkeypatch.setattr(service.runtime.prices, "refresh", lambda *a, **kw: pytest.fail("Unexpected price acquisition"))
    plan = service.preview(service.store.get("morning"))
    run = await service.run("morning")
    assert run["status"] == "completed"
    assert run["brief"]["briefDate"]
    assert service.runtime.store.load_morning_brief() == run["brief"]
    assert len(service.sources.calls) == len(plan["work"])


@pytest.mark.asyncio
async def test_partial_price_scan_does_not_stamp_stale_snapshot_as_new_brief(service, monkeypatch):
    from copenet.core.market import dashboard_runtime
    monkeypatch.setattr(dashboard_runtime, "load_webull_snapshot", lambda: None)
    service.runtime.store.save_morning_brief({"briefDate": "2026-01-01", "headline": "Previous coherent read"})
    original = service.runtime.store.load_dashboard()
    original.macro.as_of = "2026-01-01T00:00:00+00:00"
    service.runtime.store.save_dashboard(original)
    service.sources.fail.add("VOO")
    run = await service.run("morning")
    assert run["status"] == "partial"
    assert not any(error["source"] == "processing" for error in run["errors"]), run["errors"]
    assert "brief" not in run
    assert service.runtime.store.load_morning_brief()["headline"] == "Previous coherent read"
    dashboard = service.runtime.store.load_dashboard_wire()
    assert dashboard["macro"]["status"] == "stale"
    assert dashboard["macro"]["asOf"] == "2026-01-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_simultaneous_scheduled_jobs_wait_and_reuse_cache(service):
    first = focused(service, name="One")
    second = focused(service, name="Two")
    entered, release = asyncio.Event(), asyncio.Event()
    acquire = service.sources.acquire
    async def slow(source, symbol):
        entered.set()
        await release.wait()
        return await acquire(source, symbol)
    service.sources.acquire = slow
    one = asyncio.create_task(service.run(first["id"], reason="scheduled", scheduled_at="2026-09-03T13:45:00+00:00"))
    await entered.wait()
    two = asyncio.create_task(service.run(second["id"], reason="scheduled", scheduled_at="2026-09-03T13:45:00+00:00"))
    await asyncio.sleep(0)
    assert not two.done()
    release.set()
    results = await asyncio.gather(one, two)
    assert [run["status"] for run in results] == ["completed", "completed"]
    assert results[1]["cacheHits"] == 1
    assert service.sources.calls == [("sec", "TEST")]


def test_post_close_scan_rejects_preclose_cache_even_inside_ttl():
    from types import SimpleNamespace
    from copenet.core.market.scans.sources import price_cache_is_fresh
    for stamp, now in [("2026-09-03T19:59:00+00:00", "2026-09-03T20:05:00+00:00"), ("2026-11-27T17:59:00+00:00", "2026-11-27T18:05:00+00:00")]:
        assert not price_cache_is_fresh(SimpleNamespace(updated_at=stamp), datetime.fromisoformat(now))
    assert price_cache_is_fresh(SimpleNamespace(updated_at="2026-09-03T20:01:00+00:00"), datetime.fromisoformat("2026-09-03T20:05:00+00:00"))


@pytest.mark.asyncio
async def test_fresh_price_fetch_timestamp_is_checked_after_acquisition(service, monkeypatch):
    from types import SimpleNamespace
    from copenet.core.market.scans.sources import ScanSources
    def refresh(*args, **kwargs):
        return SimpleNamespace(updated_at=datetime.now(timezone.utc).isoformat(), bars=[1])
    monkeypatch.setattr(service.runtime.prices, "refresh", refresh)
    result = await ScanSources(service.runtime).acquire("prices", "TEST")
    assert result["bars"] == 1


def test_queued_same_slot_reuses_prices_after_interactive_ttl(service, monkeypatch):
    from types import SimpleNamespace
    from copenet.core.market.scans.sources import ScanSources
    monkeypatch.setattr(service.runtime.prices, "load", lambda _: SimpleNamespace(updated_at="2026-09-03T13:46:00+00:00"))
    adapter = ScanSources(service.runtime)
    now = datetime.fromisoformat("2026-09-03T14:30:00+00:00")
    slot = datetime.fromisoformat("2026-09-03T13:45:00+00:00")
    assert adapter.cached("prices", "TEST", now) is None
    assert adapter.cached("prices", "TEST", now, since=slot) is not None


def test_invalid_linked_watchlist_symbol_blocks_before_cache_path_access(service):
    service.runtime.watchlists.add("../outside")
    scan = focused(service, watchlists=["Default"])
    plan = service.preview(scan)
    assert any("invalid symbol" in issue for issue in plan["issues"])
    assert "../OUTSIDE" not in plan["resolvedSymbols"]


@pytest.mark.asyncio
async def test_state_is_compact_and_full_run_is_loaded_only_on_demand(service, monkeypatch):
    from copenet.core.market.scans import store as module
    scan = focused(service)
    run = await service.run(scan["id"])
    run["results"][0]["payload"]["largeSourceBody"] = "synthetic source detail " * 1000
    service.store.save_run(run)
    paths = []
    read = module.read_json
    def track(path, fallback):
        paths.append(path)
        return read(path, fallback)
    monkeypatch.setattr(module, "read_json", track)
    state = service.state()
    assert not any(path.parent.name == "runs" for path in paths)
    assert "results" not in state["runs"][0]
    row = next(item for item in state["scans"] if item["id"] == scan["id"])
    assert "results" not in row["lastRun"]
    assert service.store.run(run["id"])["results"][0]["payload"]["largeSourceBody"]


def test_state_reuses_source_freshness_between_overlapping_scan_rows(service):
    focused(service, name="First")
    focused(service, name="Second")
    calls = []
    cached = service.sources.cached
    def track(source, symbol, now, **kwargs):
        calls.append((source, symbol))
        return cached(source, symbol, now, **kwargs)
    service.sources.cached = track
    service.state()
    assert calls.count(("sec", "TEST")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["definition", "watchlist"])
async def test_manual_run_rejects_scope_widening_after_preview(service, change):
    scan = focused(service, watchlists=["Default"])
    token = service.preview(scan)["scopeToken"]
    if change == "definition":
        service.store.save({**scan, "symbols": ["TEST", "OTHER"]})
    else:
        service.runtime.watchlists.add("OTHER")
    with pytest.raises(ValueError, match="scope changed after preview"):
        await service.run(scan["id"], expected_scope_token=token)
    assert service.sources.calls == []
    assert service.store.runs() == []


@pytest.mark.asyncio
async def test_preview_token_ignores_cache_freshness_changes(service):
    scan = focused(service)
    before = service.preview(scan)
    service.sources.cache["sec", "TEST"] = {"updatedAt": datetime.now(timezone.utc).isoformat(), "payload": {"evidence": []}}
    after = service.preview(scan)
    assert before["cacheHits"] != after["cacheHits"]
    assert before["scopeToken"] == after["scopeToken"]
    assert (await service.run(scan["id"], expected_scope_token=before["scopeToken"]))["status"] == "completed"


@pytest.mark.asyncio
async def test_run_rpc_requires_current_scope_confirmation_before_fetch(service):
    from types import SimpleNamespace
    from copenet.host.rpc_market_scans import handle_market_scans_run
    scan = focused(service)
    orchestrator = SimpleNamespace(_market_scan_service=service)
    async def send(frame):
        pytest.fail("Unconfirmed run should not return success")
    with pytest.raises(ValueError, match="Preview"):
        await handle_market_scans_run("run", {"id": scan["id"]}, send, orchestrator)
    with pytest.raises(ValueError, match="scope changed"):
        await handle_market_scans_run("run", {"id": scan["id"], "scopeToken": "0" * 64}, send, orchestrator)
    assert service.sources.calls == []
