"""The mini chart projects exact retained evidence and never invents future points."""
from datetime import datetime, timezone
from copenet.core.market.chart_workspace import ChartStore
from copenet.core.market.forecasts.chart import forecast_chart


def test_setup_chart_bounds_history_and_keeps_publication_basis_outcome(tmp_path):
    store = ChartStore(tmp_path / 'chart.sqlite3')
    instrument = {'instrumentId': 'synthetic:TEST', 'symbol': 'TEST', 'assetClass': 'equity', 'source': 'synthetic', 'currency': None}
    document = store.workspace('primary', instrument)['document']
    rows = [{'t': 1700000000 + day * 86400, 'o': 100, 'h': 102, 'l': 99, 'c': 101 + day / 100, 'v': 1000} for day in range(80)]
    observation = store.capture('session', 'capture', {'schemaVersion': 1, 'viewId': 'view', 'viewRevision': 1,
        'instrument': instrument, 'timeframe': 'D', 'range': '1Y', 'viewport': {'from': rows[0]['t'], 'to': rows[-1]['t']},
        'selection': None, 'settings': {'includeAccountContext': False}, 'documentId': document['documentId'], 'documentRevision': 0,
        'resources': [{'key': 'candles:D', 'kind': 'candles', 'label': 'Synthetic', 'status': 'loaded', 'rows': rows, 'metadata': {}}]})
    published = datetime.fromtimestamp(rows[-1]['t'], timezone.utc)
    record = {'status': 'published', 'observationId': observation['observationId'], 'publishedAt': published.isoformat(),
        'provenance': {'completedThrough': rows[-2]['t']}, 'members': {'ta': {'result': {'kind': 'setup'}}}, 'evaluation': None}
    chart = forecast_chart(store, record)
    assert len(chart['history']) == 60
    assert chart['history'][-1] == {'t': rows[-2]['t'], 'close': rows[-2]['c']}
    assert chart['outcome'] == []
    assert chart['deadlineAt'] - chart['publishedAt'] == 56 * 86400
    record['evaluation'] = {'health': 'revision_review', 'reason': 'Retained source revision',
        'consumedBars': [{'sessionClose': '2024-02-06T21:00:00+00:00', 'c': 123.456}]}
    chart = forecast_chart(store, record)
    assert chart['outcome'][0]['close'] == 123.456
    assert chart['health'] == 'revision_review'
    assert chart['reason'] == 'Retained source revision'
