"""Account-scoped ticker context from saved broker data; never acquires market data."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math
from zoneinfo import ZoneInfo

from .price_cache import PriceHistory
from .webull.client import account_fingerprint, selected_account
from .webull.sync import load_snapshot
from .webull.orders import load_fills

_NEW_YORK = ZoneInfo('America/New_York')


def _timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp if stamp.tzinfo is not None else None
    except ValueError:
        return None


def _number(value) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _account_matches(payload: dict | None, account_id: str | None) -> bool:
    return bool(payload and account_id and payload.get('account_fingerprint') == account_fingerprint(account_id))


def _split_after_snapshot(snapshot: dict, history: PriceHistory | None) -> bool:
    stamp = _timestamp(snapshot.get('synced_at'))
    if stamp is None:
        return True
    session_date = stamp.astimezone(_NEW_YORK).date().isoformat()
    return bool(history and any(day > session_date for day, _ in history.splits))


def position_context(symbol: str, snapshot: dict | None, account_id: str | None,
                     history: PriceHistory | None = None) -> dict | None:
    if not _account_matches(snapshot, account_id) or _split_after_snapshot(snapshot, history):
        return None
    positions = [row for row in snapshot['positions'] if isinstance(row, dict)
                 and row.get('symbol') == symbol and row.get('asset_type') == 'EQUITY'
                 and _number(row.get('quantity')) and row['quantity'] != 0]
    # Only exact, explicit equity identity can own the underlying's position layer.
    if len(positions) != 1:
        return None
    row = positions[0]
    context = {key: row.get(key) for key in (
        'symbol', 'quantity', 'avg_cost', 'last_price', 'market_value', 'unrealized_pl',
        'unrealized_pl_pct', 'allocation_pct', 'price_source', 'warnings',
    )}
    for key in ('avg_cost', 'last_price', 'market_value', 'unrealized_pl', 'unrealized_pl_pct', 'allocation_pct'):
        if not _number(context[key]):
            context[key] = None
    return deepcopy({**context, 'synced_at': snapshot['synced_at'], 'currency': snapshot.get('currency')})


def ticker_position(symbol: str, history: PriceHistory | None = None) -> dict:
    account = selected_account()
    account_id = account['accountId'] if account else None
    snapshot = load_snapshot()
    saved = load_fills()
    warnings = []
    if not account_id:
        warnings.append('No Webull account is selected. Position data is unavailable.')
    elif snapshot is None:
        warnings.append('No saved position snapshot is available. Sync positions for the selected account.')
    if snapshot and not _account_matches(snapshot, account_id):
        warnings.append('Sync positions for the selected account before displaying position data.')
        snapshot = None
    if saved and not _account_matches(saved, account_id):
        warnings.append('Sync fill history for the selected account before displaying recorded orders.')
        saved = None
    if snapshot:
        warnings.extend(snapshot.get('warnings', []))
        if _split_after_snapshot(snapshot, history):
            warnings.append('Position date or share basis is stale. Sync positions before displaying the cost line.')
    position = position_context(symbol, snapshot, account_id, history)
    fills = []
    seen = set()
    if saved:
        warnings.extend(saved.get('warnings', []))
        for row in saved['fills']:
            if not isinstance(row, dict) or row.get('symbol') != symbol or row.get('instrument_type') != 'EQUITY':
                continue
            identity = row.get('order_id')
            if not isinstance(identity, str) or not identity or identity in seen:
                continue
            stamp = _timestamp(row.get('filled_at'))
            if stamp is None or not _number(row.get('quantity')) or row['quantity'] <= 0 or row.get('side') not in {'BUY', 'SELL', 'SHORT'}:
                warnings.append('An invalid recorded order cannot be placed on the chart.')
                continue
            seen.add(identity)
            # An order aggregate is located at its last execution's NY session.
            day = stamp.astimezone(_NEW_YORK).date().isoformat()
            fills.append({
                'id': identity, 'side': row['side'], 'quantity': row['quantity'],
                'price': row.get('price') if _number(row.get('price')) else None,
                'filledAt': row['filled_at'], 'sessionDate': day,
                'priceSource': row.get('price_source', 'fill'),
            })
    fills.sort(key=lambda row: _timestamp(row['filledAt']))
    return {'symbol': symbol, 'position': position, 'syncedAt': snapshot['synced_at'] if snapshot else None,
            'fillsSyncedAt': saved.get('synced_at') if saved else None, 'fills': fills[-2000:],
            'fillCount': len(fills), 'warnings': list(dict.fromkeys(warnings)),
            'historyNote': 'Recorded order aggregates at original trade prices and last execution times. Not historical position valuation.'}
