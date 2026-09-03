"""Deterministic crossing state machine. Acquisition and delivery belong outside it."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json

from .alert_candles import completed_candles
from .alert_evaluator import evaluator_request
from .alert_rules import AlertRule
from .alerts import resolve_alert_store
from .price_history import split_fingerprint, chart_history_window


def _hash(bars) -> str:
    return hashlib.sha256(json.dumps([asdict(bar) for bar in bars], sort_keys=True).encode()).hexdigest()


def _condition(rule: AlertRule) -> str:
    def label(operand):
        if operand['kind'] == 'price':
            return 'Close'
        if operand['kind'] == 'constant':
            return f"{operand['value']:g}"
        settings = ', '.join(f'{key}={value}' for key, value in operand['config'].items())
        return f"{operand['indicatorId'].upper()}({settings}) {operand['output']}"
    return f"{label(rule.left)} crosses {rule.direction} {label(rule.right)}"


def evaluate_scan_alerts(runtime, scan_id, symbols, *, now=None, alert_ids=None):
    now = now or datetime.now(timezone.utc)
    store = resolve_alert_store(runtime)
    emitted = []
    with store.transaction():
        rules = store._load()
        updated = []
        for rule in rules:
            if not rule.enabled or rule.scanId != scan_id or rule.symbol not in symbols or (alert_ids is not None and rule.alertId not in alert_ids):
                updated.append(rule)
                continue
            try:
                history = runtime.prices.load(rule.symbol)
                if history is None:
                    replacement, event = replace(rule, status='missing_history', error='Run the linked price scan to load history', lastEvaluatedAt=now.isoformat()), None
                else:
                    replacement, event = _evaluate(rule, history, now)
            except Exception as exc:
                replacement, event = replace(rule, status='error', error=str(exc), lastEvaluatedAt=now.isoformat()), None
            if event:
                # Durable evidence precedes state advancement. Stable ID makes retry safe.
                emitted.append(store._append_event(event))
            updated.append(replacement)
        store._save(updated)
    return emitted


def _evaluate(rule, history, now):
    candles = completed_candles(history, rule.timeframe, now)
    observed = replace(rule, lastEvaluatedAt=now.isoformat(), error=candles.error, status=candles.status)
    if candles.status != 'ready':
        return observed, None
    # Slice before removing the forming tail, exactly as chart transport does. Slicing
    # completed bars alone would give daily EMA a different oldest seed at 09:45.
    window = chart_history_window(history.derive(timeframe=rule.timeframe), rule.timeframe)
    window_times = {bar.t for bar in window}
    calculation_bars = [bar for bar in candles.bars if bar.t in window_times]
    points = evaluator_request({'action': 'evaluate', 'timeframe': rule.timeframe,
        'bars': [asdict(bar) for bar in calculation_bars], 'left': rule.left, 'right': rule.right})['points']
    latest = points[-1]
    if latest['left'] is None or latest['right'] is None:
        return replace(observed, status='warming_up', error='Not enough completed candles for the selected indicator settings'), None
    fingerprint = split_fingerprint(history.splits)
    baseline = {**latest, 'splitFingerprint': fingerprint, 'historyHash': _hash(candles.bars)}
    observation = {**latest, 'candleCloseAt': candles.close_times[latest['t']], 'priceBasis': 'split_adjusted'}
    observed = replace(observed, observation=observation, lastCandleAt=observation['candleCloseAt'], status='active', error=None, baseline=baseline)
    previous = rule.baseline
    if previous is None or latest['t'] <= previous['t']:
        return observed, None
    prefix = [bar for bar in candles.bars if bar.t <= previous['t']]
    contiguous = len(points) > 1 and points[-2]['t'] == previous['t']
    if not contiguous or previous['splitFingerprint'] != fingerprint or previous['historyHash'] != _hash(prefix):
        return replace(observed, status='rebaselined', error='Baseline reset after a missed candle, split, or history revision; no retrospective alert'), None
    # Rolling daily windows may change an EMA seed. The crossing must be the one the
    # current chart draws, not a mixture of values calculated from two different windows.
    prior_point = points[-2]
    if prior_point['left'] is None or prior_point['right'] is None:
        return observed, None
    crossed = (prior_point['left'] <= prior_point['right'] and latest['left'] > latest['right']) if rule.direction == 'above' else (prior_point['left'] >= prior_point['right'] and latest['left'] < latest['right'])
    if not crossed:
        return observed, None
    observed = replace(observed, status='triggered' if rule.oneShot else 'active', enabled=not rule.oneShot)
    event = {'eventId': f"market-alert-{rule.alertId}-{rule.revision}-{latest['t']}",
        'alertId': rule.alertId, 'revision': rule.revision, 'symbol': rule.symbol,
        'timeframe': rule.timeframe, 'condition': _condition(rule), 'leftValue': latest['left'],
        'rightValue': latest['right'], 'candleCloseAt': observation['candleCloseAt'],
        'evaluatedAt': now.isoformat(), 'scanId': rule.scanId, 'destinationIds': rule.destinationIds,
        'rule': observed.to_wire()}
    return observed, event
