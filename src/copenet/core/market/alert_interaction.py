"""Scan-observed interactions with stable previous-period signals and close followups."""
from dataclasses import asdict, replace
import hashlib
import json

from .alert_candles import completed_candles
from .alert_conditions import calculate, chart_snapshot, condition_label, confirmation_label, confirmation_result, reached, operand_label
from .alert_forming import forming_candle
from .price_history import chart_history_window, split_fingerprint


_PRICE_FIELDS = {'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c'}


def _hash(bars):
    return hashlib.sha256(json.dumps([asdict(bar) for bar in bars], sort_keys=True).encode()).hexdigest()


def _event(rule, point, close_at, now, phase, bars, points, *, observed_at, pending=None):
    event = {'eventId': f"market-alert-{rule.alertId}-{rule.revision}-{point['t']}-{phase}",
        'alertId': rule.alertId, 'revision': rule.revision, 'symbol': rule.symbol,
        'timeframe': rule.timeframe, 'condition': condition_label(rule) if phase == 'interaction' else confirmation_label(rule), 'phase': phase,
        'interactionCondition': condition_label(rule), 'confirmationCondition': confirmation_label(rule), 'observedAt': observed_at,
        'leftValue': point['left'], 'rightValue': point['right'], 'candleCloseAt': close_at,
        'evaluatedAt': now.isoformat(), 'scanId': rule.scanId, 'destinationIds': rule.destinationIds,
        'rule': rule.to_wire(), 'observationSource': 'linked_scan',
        'reference': 'previous_completed' if phase == 'interaction' else 'completed'}
    if pending:
        event['interactionEventId'] = pending['eventId']
        event['interactionReference'] = pending['right']
    if rule.includeChart:
        event['chartSnapshot'] = chart_snapshot(bars, points, event['reference'])
        pair = {'left': rule.left, 'right': rule.right} if phase == 'interaction' else rule.confirmation or {'left': {'kind': 'price', 'field': 'close'}, 'right': rule.right}
        event['chartSnapshot'].update(leftLabel=operand_label(pair['left']), rightLabel=operand_label(pair['right']))
    return event


def evaluate_interaction(rule, history, now):
    candles = completed_candles(history, rule.timeframe, now)
    observed = replace(rule, lastEvaluatedAt=now.isoformat(), error=candles.error, status=candles.status)
    if candles.status != 'ready':
        return observed, []
    window = chart_history_window(history.derive(timeframe=rule.timeframe), rule.timeframe)
    times = {bar.t for bar in window}
    bars = [bar for bar in candles.bars if bar.t in times]
    points = calculate(bars, rule)
    latest = points[-1]
    if latest['right'] is None:
        return replace(observed, status='warming_up', error='Not enough completed candles for the signal'), []
    previous = rule.baseline
    fingerprint = split_fingerprint(history.splits)
    state = {'t': latest['t'], 'historyHash': _hash(candles.bars), 'splitFingerprint': fingerprint,
             'period': None, 'pending': None, 'latched': False}
    reset_reason = None
    if previous:
        prefix = [bar for bar in candles.bars if bar.t <= previous['t']]
        contiguous = latest['t'] == previous['t'] or len(points) > 1 and points[-2]['t'] == previous['t']
        if not contiguous or fingerprint != previous['splitFingerprint'] or _hash(prefix) != previous['historyHash']:
            reset_reason = 'Baseline reset after a missed candle, split, or history revision; pending confirmation discarded'
            previous = None
        else:
            state.update({key: previous.get(key) for key in ('period', 'pending', 'latched')})
    events = []
    pending = state['pending']
    if pending and pending['t'] <= latest['t']:
        # Only the immediately completed period is eligible. Never confirm a missed period.
        if pending['t'] == latest['t']:
            confirmed_points = calculate(bars, rule, confirmation=True)
            point = confirmed_points[-1]
            phase = confirmation_result(rule, point)
            events.append(_event(observed, point, candles.close_times[point['t']], now, phase,
                                 bars, confirmed_points, observed_at=history.updated_at, pending=pending))
            state['pending'] = None
            if rule.oneShot:
                return replace(observed, enabled=False, status='triggered', baseline=state,
                    lastCandleAt=candles.close_times[point['t']], observation={**point, 'phase': phase,
                    'candleCloseAt': candles.close_times[point['t']], 'priceBasis': 'split_adjusted'}), events
        else:
            state['pending'] = None
            reset_reason = 'The interaction period was missed; no retrospective confirmation'
    forming = forming_candle(history, rule.timeframe, now)
    observed = replace(observed, baseline=state, lastCandleAt=candles.close_times[latest['t']],
        status='waiting_interaction', error=forming.error,
        observation={**latest, 'candleCloseAt': candles.close_times[latest['t']], 'priceBasis': 'split_adjusted'})
    if forming.bar:
        bar = forming.bar
        period = state['period']
        reference = period['right'] if period and period['t'] == bar.t else latest['right']
        point = {'t': bar.t, 'left': getattr(bar, _PRICE_FIELDS[rule.left.get('field', 'close')]), 'right': reference}
        matching = reached(point['left'], point['right'], rule.direction)
        # Arm from what is observed now, not an already-existing historical touch.
        if previous is None:
            state['latched'] = matching
        elif not matching:
            state['latched'] = False
        elif not state['latched'] and not state['pending']:
            event = _event(observed, point, forming.close_at, now, 'interaction', bars + [bar], points + [point], observed_at=history.updated_at)
            events.append(event)
            state['pending'] = {**point, 'eventId': event['eventId']}
            state['latched'] = True
        state['period'] = {'t': bar.t, 'right': reference}
        observed = replace(observed, observation={**point, 'phase': 'interaction', 'candleCloseAt': forming.close_at,
            'priceBasis': 'split_adjusted', 'reference': 'previous_completed', 'cacheUpdatedAt': history.updated_at})
    if state['pending']:
        observed = replace(observed, status='waiting_confirmation')
    if reset_reason:
        observed = replace(observed, status='rebaselined', error=reset_reason)
    return observed, events
