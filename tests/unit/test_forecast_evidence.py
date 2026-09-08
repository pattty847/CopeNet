"""Frozen render inputs retain their own cache revision through forecast publication."""
from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from copenet.core.market.chart_prices import candle_hash, chart_price_snapshot
from copenet.core.market.chart_workspace import ChartStore
from copenet.core.market.forecasts.evidence import publication_evidence
from copenet.core.market.models import MarketBar
from copenet.core.market.price_cache import PriceHistory
from copenet.core.market.price_history import utc_midnight


NOW = datetime(2024, 1, 5, 22, tzinfo=timezone.utc)


def runtime():
    bars = [MarketBar(utc_midnight(datetime(2024, 1, day).date()), 100.0, 102.0, 99.0, 101.0, 1000) for day in (2, 3, 4, 5)]
    history = PriceHistory('SYN', bars, [], [], NOW.isoformat())
    calls = []
    prices = SimpleNamespace(refresh=lambda symbol: calls.append(('refresh', symbol)),
                             load=lambda symbol: calls.append(('load', symbol)) or history)
    return SimpleNamespace(prices=prices, store=SimpleNamespace(load_bars=lambda *args: [])), history, calls


def capture(tmp_path, runtime, mutate=None):
    series, provenance = chart_price_snapshot(runtime, 'SYN', now=NOW)
    store = ChartStore(tmp_path / 'chart.sqlite3')
    instrument = {'instrumentId': 'synthetic:SYN', 'symbol': 'SYN', 'assetClass': 'equity', 'source': 'synthetic', 'currency': None}
    document = store.workspace('primary', instrument)['document']
    raw = {'schemaVersion': 1, 'viewId': 'view', 'viewRevision': 1, 'instrument': instrument, 'timeframe': 'D',
           'range': '1Y', 'viewport': {'from': series['daily'][0].t, 'to': series['daily'][-1].t}, 'selection': None,
           'settings': {'includeAccountContext': False}, 'documentId': document['documentId'], 'documentRevision': 0,
           'resources': [{'key': 'candles:D', 'kind': 'candles', 'label': 'Synthetic candles', 'status': 'loaded',
                          'rows': [asdict(bar) for bar in series['daily']], 'metadata': {'priceProvenance': provenance}}]}
    if mutate:
        mutate(raw)
    observation = store.capture('session', 'capture', raw)
    return store, {'observationId': observation['observationId'], 'sessionKey': 'session'}


def test_all_chart_timeframes_share_one_cache_revision():
    host, _, calls = runtime()
    series, provenance = chart_price_snapshot(host, 'SYN', now=NOW)
    assert calls == [('refresh', 'SYN'), ('load', 'SYN')]
    assert len(series['daily']) == 4 and len(series['weekly']) == 1
    assert provenance['completionStatus'] == 'ready'
    assert provenance['completedCloseAt'] == '2024-01-05T21:00:00+00:00'


def test_fallback_bars_never_claim_cache_provenance():
    host, history, _ = runtime()
    host.prices.load = lambda symbol: None
    host.store.load_bars = lambda *args: history.bars
    series, provenance = chart_price_snapshot(host, 'SYN', now=NOW)
    assert series['daily'] == history.bars
    assert provenance is None


def test_publication_reads_existing_revision_without_acquisition(tmp_path):
    host, _, calls = runtime()
    store, record = capture(tmp_path, host)
    calls.clear()
    evidence = publication_evidence(store, record, host, NOW)
    assert calls == [('load', 'SYN')]
    assert evidence['referenceClose'] == 101
    assert evidence['evidenceCutoff'] == '2024-01-05T21:00:00+00:00'


@pytest.mark.parametrize('change,message', [
    (lambda raw: raw['resources'][0].update(status='stale'), 'loaded candles'),
    (lambda raw: raw['resources'][0]['rows'][0].update(c=123), 'differs from its provenance'),
    (lambda raw: raw['settings'].update(comparisonMode=True), 'single-price chart'),
    (lambda raw: raw['resources'][0]['metadata']['priceProvenance'].update(calendar=None), 'unsupported price basis'),
])
def test_invalid_capture_cannot_be_published(tmp_path, change, message):
    host, _, _ = runtime()
    store, record = capture(tmp_path, host, change)
    with pytest.raises(ValueError, match=message):
        publication_evidence(store, record, host, NOW)


def test_source_correction_after_capture_blocks_publication(tmp_path):
    host, history, _ = runtime()
    store, record = capture(tmp_path, host)
    history.bars[0] = MarketBar(history.bars[0].t, 100, 110, 99, 109, 1000)
    with pytest.raises(ValueError, match='differ from the cached revision'):
        publication_evidence(store, record, host, NOW)


def test_split_after_capture_blocks_publication(tmp_path):
    host, history, _ = runtime()
    store, record = capture(tmp_path, host)
    history.splits.append(('2024-01-05', 2))
    with pytest.raises(ValueError, match='split history changed'):
        publication_evidence(store, record, host, NOW)


def test_integral_browser_numbers_have_identical_candle_hash():
    assert candle_hash([{'t': 1, 'o': 100, 'h': 101, 'l': 99, 'c': 100, 'v': 0}]) == candle_hash([
        {'t': 1.0, 'o': 100.0, 'h': 101.0, 'l': 99.0, 'c': 100.0, 'v': 0.0}])
