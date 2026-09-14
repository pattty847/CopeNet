"""Synthetic saved-account projections and immutable notification context."""
from copy import deepcopy
from types import SimpleNamespace

from copenet.core.market import positions, position_context as notification
from copenet.core.market.webull.client import account_fingerprint


def snapshot(account='account-1234', **row):
    return {'account_fingerprint': account_fingerprint(account), 'account_id_masked': '***1234',
            'synced_at': '2026-09-01T18:00:00Z', 'currency': 'USD', 'warnings': [],
            'positions': [{'symbol': 'SYNTH', 'asset_type': 'EQUITY', 'quantity': 2,
                           'avg_cost': 10, 'warnings': [], **row}]}


def saved_fills(account='account-1234', rows=None):
    return {'account_fingerprint': account_fingerprint(account), 'account_id_masked': '***1234',
            'synced_at': '2026-09-01T18:00:00Z', 'warnings': [], 'fills': rows or []}


def order(identity='order', **fields):
    return {'order_id': identity, 'symbol': 'SYNTH', 'instrument_type': 'EQUITY',
            'side': 'BUY', 'quantity': 2, 'price': 10, 'filled_at': '2026-09-01T02:00:00Z', **fields}


def install(monkeypatch, snap, fills=None, account='account-1234'):
    monkeypatch.setattr(positions, 'load_snapshot', lambda: snap)
    monkeypatch.setattr(positions, 'load_fills', lambda: fills)
    monkeypatch.setattr(positions, 'selected_account', lambda: {'accountId': account} if account else None)


def test_exact_equity_match_rejects_options_missing_type_and_duplicate_rows():
    for kind in ['OPTION', None, 'ETF', 'STOCK']:
        assert positions.position_context('SYNTH', snapshot(asset_type=kind), 'account-1234') is None
    snap = snapshot()
    snap['positions'].append(deepcopy(snap['positions'][0]))
    assert positions.position_context('SYNTH', snap, 'account-1234') is None
    assert positions.position_context('OTHER', snapshot(), 'account-1234') is None
    assert positions.position_context('SYNTH', snapshot(quantity=0), 'account-1234') is None


def test_matching_short_position_preserves_unknown_fields_and_currency():
    snap = snapshot(quantity=-2)
    snap['currency'] = None
    context = positions.position_context('SYNTH', snap, 'account-1234')
    assert context['quantity'] == -2
    assert context['market_value'] is None
    assert context['currency'] is None


def test_selected_account_isolation_cannot_collide_on_masked_suffix(monkeypatch):
    install(monkeypatch, snapshot(), saved_fills(rows=[order()]), account='other-1234')
    result = positions.ticker_position('SYNTH')
    assert result['position'] is None and result['fills'] == []
    assert result['syncedAt'] is None and result['fillsSyncedAt'] is None
    assert len(result['warnings']) == 2


def test_older_cache_requires_new_sync_instead_of_masked_identity_guess(monkeypatch):
    snap = snapshot()
    del snap['account_fingerprint']
    install(monkeypatch, snap)
    assert positions.ticker_position('SYNTH')['position'] is None


def test_no_selected_account_is_unknown_not_a_zero_position(monkeypatch):
    install(monkeypatch, snapshot(), account=None)
    result = positions.ticker_position('SYNTH')
    assert result['position'] is None
    assert 'No Webull account is selected' in result['warnings'][0]


def test_order_story_rejects_bad_dates_options_and_duplicate_ids(monkeypatch):
    rows = [order(), order(), order('option', instrument_type='OPTION'),
            order('bad', filled_at='bad date'), order('naive', filled_at='2026-09-01T12:00:00')]
    install(monkeypatch, snapshot(), saved_fills(rows=rows))
    result = positions.ticker_position('SYNTH')
    assert result['fillCount'] == 1
    assert result['fills'][0]['sessionDate'] == '2026-08-31'
    assert 'order aggregates' in result['historyNote']
    assert result['warnings']


def test_split_after_snapshot_suppresses_position_without_mutating_holdings(monkeypatch):
    snap = snapshot()
    install(monkeypatch, snap)
    history = SimpleNamespace(splits=[('2026-09-02', 4)])
    result = positions.ticker_position('SYNTH', history)
    assert result['position'] is None
    assert result['warnings']
    assert snap['positions'][0]['quantity'] == 2
    assert positions.ticker_position('SYNTH', SimpleNamespace(splits=[('2026-09-01', 4)]))['position']


def test_invalid_snapshot_date_does_not_crash(monkeypatch):
    snap = snapshot()
    snap['synced_at'] = 'bad date'
    install(monkeypatch, snap)
    result = positions.ticker_position('SYNTH')
    assert result['position'] is None and result['warnings']


def test_position_context_is_frozen_when_snapshot_changes(monkeypatch):
    snap = snapshot()
    monkeypatch.setattr(notification, 'load_snapshot', lambda: snap)
    monkeypatch.setattr(notification, 'selected_account', lambda: {'accountId': 'account-1234'})
    event = {'symbol': 'SYNTH', 'rule': {'includePosition': True}}
    attached = notification.attach_position_context(event)
    snap['positions'][0]['quantity'] = 99
    snap['positions'][0]['warnings'].append('later warning')
    assert attached['position']['quantity'] == 2
    assert attached['position']['warnings'] == []
    assert 'position' not in event


def test_excluded_account_context_does_not_read_account(monkeypatch):
    monkeypatch.setattr(notification, 'load_snapshot', lambda: (_ for _ in ()).throw(AssertionError('read')))
    event = {'symbol': 'SYNTH', 'rule': {'includePosition': False}}
    assert notification.attach_position_context(event) is event
