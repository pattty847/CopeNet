"""Bounded setup/outcome chart projection from frozen and evaluated evidence only."""
from datetime import datetime, timedelta
import json


def forecast_chart(chart_store, record):
    if record['status'] != 'published' or record['members'].get('ta', {}).get('result', {}).get('kind') != 'setup':
        return None
    with chart_store.connect() as db:
        row = db.execute('SELECT r.body FROM resources r JOIN observation_resources o ON r.id=o.resource_id '
                         'WHERE o.observation_id=? AND o.resource_key=?',
                         (record['observationId'], 'candles:D')).fetchone()
    published = datetime.fromisoformat(record['publishedAt'])
    evaluation = record.get('evaluation') or {}
    cutoff = record['provenance']['completedThrough']
    historical = [] if row is None else [bar for bar in json.loads(row['body'])['rows'] if bar['t'] <= cutoff][-60:]
    # consumedBars already use publication prices, enforce completed sessions and stop
    # at coverage gaps. Reuse that evidence, including retained rows under source review.
    outcome = evaluation.get('consumedBars', [])
    return {'publishedAt': published.timestamp(), 'deadlineAt': (published + timedelta(days=56)).timestamp(),
            'history': [{'t': bar['t'], 'close': bar['c']} for bar in historical],
            'outcome': [{'t': datetime.fromisoformat(bar['sessionClose']).timestamp(), 'close': bar['c']} for bar in outcome],
            'health': evaluation.get('health', 'unevaluated'), 'reason': evaluation.get('reason'),
            'basis': 'publication', 'historyAvailable': bool(historical)}
