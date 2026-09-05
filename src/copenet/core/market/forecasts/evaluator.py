"""Deterministic, replayable simulated trades and dated directional forecasts."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from .candles import digest, forecast_candles, history_revision

POLICY_VERSION = 'daily-ohlcv-1'
TERMINAL_STATES = {'target_complete', 'stopped', 'deadline_exit', 'expired_unfilled', 'gapped_past_setup', 'ambiguous', 'no_setup'}


def evaluate_forecast(forecast: dict, history, now: datetime) -> dict:
    """Replay only captured completed bars; callers persist the returned evidence atomically."""
    candles = forecast_candles(forecast, history, now)
    previous = forecast.get('evaluation') or {}
    ta = forecast['members'].get('ta', {}).get('result')
    result = {'policyVersion': POLICY_VERSION, 'state': 'waiting_entry' if ta and ta['kind'] == 'setup' else 'no_setup' if ta else 'unavailable',
              'health': candles.health, 'reason': candles.reason, 'events': [], 'horizons': {},
              'consumedBars': candles.bars, 'source': candles.source, 'barsHash': digest(candles.bars),
              'evaluatedAt': now.isoformat(), 'entryPrice': None, 'entryDate': None,
              'exitDate': None, 'remainingFraction': 0.0, 'realizedPnl': None, 'plannedRiskR': None,
              'holdingSessions': None, 'activationDate': candles.sessions[0]['date'] if candles.sessions else None}
    # Once a consumed revision changes, do not blend corrected history with old outcomes.
    revised = history_revision(previous.get('consumedBars', []), candles.bars)
    if candles.health in {'revision_review', 'unsupported'} or revised or previous.get('health') == 'revision_review':
        if previous:
            result = deepcopy(previous)
        result.update(health='revision_review' if revised or previous.get('health') == 'revision_review' else candles.health,
                      reason='Previously consumed history changed or became unavailable; original evaluation retained' if revised else previous.get('reason') or candles.reason,
                      evaluatedAt=now.isoformat())
        if result['health'] == 'revision_review':
            identity = digest([forecast['forecastId'], 'revision_notice', digest(candles.bars), candles.source.get('splitFingerprint')])
            if not any(item['eventId'] == identity for item in result['events']):
                result['events'].append({'eventId': identity, 'type': 'revision_notice', 'date': now.date().isoformat(),
                                         'recordedAt': now.isoformat(), 'reason': result['reason'], 'policyVersion': POLICY_VERSION})
        return result

    # Reversing a split may differ by a floating-point ulp. Keep exact already-consumed
    # numbers after the revision check so event identities and fills remain immutable.
    known_bars = {bar['date']: bar for bar in previous.get('consumedBars', [])}
    candles.bars[:] = [known_bars.get(bar['date'], bar) for bar in candles.bars]
    result['barsHash'] = digest(candles.bars)
    previous_events = {item['eventId']: item for item in previous.get('events', [])}
    def event(kind, bar, **fields):
        identity = [forecast['forecastId'], POLICY_VERSION, kind, bar['date'], fields.get('targetIndex')]
        event_id = digest(identity)
        recorded = previous_events.get(event_id, {}).get('recordedAt', now.isoformat())
        result['events'].append({'eventId': event_id, 'type': kind, 'date': bar['date'],
                                 'recordedAt': recorded, 'sessionClose': bar['sessionClose'],
                                 'policyVersion': POLICY_VERSION, **fields})

    # Split reversal can introduce tiny floating differences. Once verified equal,
    # replay the exact retained rows so existing event prices stay byte-for-byte stable.
    retained = {bar['date']: bar for bar in previous.get('consumedBars', [])}
    candles.bars[:] = [retained.get(bar['date'], bar) for bar in candles.bars]
    result['consumedBars'] = candles.bars
    result['barsHash'] = digest(candles.bars)
    if ta and ta['kind'] == 'setup':
        _evaluate_trade(ta, forecast['entryExpirySessions'], candles, result, event)
    _evaluate_horizons(forecast, candles, now, result)
    return result


def _evaluate_trade(setup, entry_expiry, candles, result, event):
    sign = 1 if setup['direction'] == 'long' else -1
    entry, stop = setup['entry']['price'], setup['stop']
    risk = abs(entry - stop)
    targets = setup['targets']
    filled = set()
    pnl = 0.0
    entry_index = None
    deadline_date = candles.endpoints['8w']['date']

    def exit_fraction(kind, bar, price, fraction, target_index=None):
        nonlocal pnl
        pnl += sign * (price - result['entryPrice']) * fraction
        result['remainingFraction'] = max(0.0, result['remainingFraction'] - fraction)
        event(kind, bar, price=price, fraction=fraction, **({'targetIndex': target_index} if target_index is not None else {}))
        result['realizedPnl'] = pnl
        if result['remainingFraction'] < 1e-9:
            result['remainingFraction'] = 0.0
            result['state'] = 'target_complete' if kind == 'target' else 'stopped' if kind == 'stop' else 'deadline_exit'
            result['exitDate'] = bar['date']
            result['plannedRiskR'] = pnl / risk

    for index, bar in enumerate(candles.bars):
        if result['state'] in TERMINAL_STATES:
            break
        opened, favorable, adverse = sign * bar['o'], sign * (bar['h'] if sign == 1 else bar['l']), sign * (bar['l'] if sign == 1 else bar['h'])
        stop_hit = adverse <= sign * stop
        pending = [(i, target) for i, target in enumerate(targets) if i not in filled]
        intrabar_entry = False
        if result['state'] == 'waiting_entry':
            opening_entry = opened <= sign * entry if setup['entry']['kind'] == 'limit' else opened >= sign * entry
            touching_entry = adverse <= sign * entry if setup['entry']['kind'] == 'limit' else favorable >= sign * entry
            if opening_entry or touching_entry:
                price = bar['o'] if opening_entry else entry
                if opening_entry and (opened <= sign * stop or any(opened >= sign * target['price'] for _, target in pending)):
                    result['state'] = 'gapped_past_setup'
                    event('gapped_past_setup', bar, price=price, reason='Opening entry crossed the protective stop or a profit target')
                    break
                intrabar_entry = not opening_entry
                result.update(state='active', entryPrice=price, entryDate=bar['date'], remainingFraction=1.0, realizedPnl=0.0)
                entry_index = index
                event('entry', bar, price=price, fraction=1.0, timing='intrabar' if intrabar_entry else 'open')
            elif index + 1 >= entry_expiry or bar['date'] == deadline_date:
                result['state'] = 'expired_unfilled'
                event('expired_unfilled', bar)
                break
            else:
                continue
        result['holdingSessions'] = index - entry_index + 1
        touches_target = any(favorable >= sign * target['price'] for _, target in pending)
        if intrabar_entry and (stop_hit or touches_target):
            result.update(state='ambiguous', plannedRiskR=None, realizedPnl=None)
            event('ambiguous', bar, reason='intrabar_entry_exit', candidateStop=stop_hit,
                  candidateTargets=[i for i, target in pending if favorable >= sign * target['price']])
            break
        # The open has known ordering before every intrabar range event.
        if not intrabar_entry:
            if opened <= sign * stop:
                exit_fraction('stop', bar, bar['o'], result['remainingFraction'])
                break
            for target_index, target in pending:
                if opened >= sign * target['price']:
                    exit_fraction('target', bar, target['price'], target['fraction'], target_index)
                    filled.add(target_index)
            if result['state'] == 'target_complete':
                break
        pending = [(i, target) for i, target in enumerate(targets) if i not in filled]
        touches_target = any(favorable >= sign * target['price'] for _, target in pending)
        if stop_hit and touches_target:
            result.update(state='ambiguous', plannedRiskR=None)
            event('ambiguous', bar, reason='carried_position_stop_target', candidateStop=True,
                  candidateTargets=[i for i, target in pending if favorable >= sign * target['price']])
            break
        if stop_hit:
            exit_fraction('stop', bar, stop, result['remainingFraction'])
            break
        for target_index, target in pending:
            if favorable >= sign * target['price']:
                exit_fraction('target', bar, target['price'], target['fraction'], target_index)
                filled.add(target_index)
        if result['state'] == 'target_complete':
            break
        if bar['date'] == deadline_date:
            exit_fraction('deadline', bar, bar['c'], result['remainingFraction'])
            break


def _evaluate_horizons(forecast, candles, now, result):
    by_day = {bar['date']: bar for bar in candles.bars}
    ta = forecast['members'].get('ta', {}).get('result')
    directions = {'ta': ('bullish' if ta['direction'] == 'long' else 'bearish') if ta['kind'] == 'setup' else 'abstain'} if ta else {}
    plain = forecast['members'].get('directional', {}).get('result')
    if plain:
        directions['directional'] = plain['direction']
    for horizon, endpoint in candles.endpoints.items():
        bar = by_day.get(endpoint['date'])
        ready = now >= datetime.fromisoformat(endpoint['dueAt']) and bar is not None
        value = {'dueAt': endpoint['dueAt'], 'endpointDate': endpoint['date'],
                 'endpointCloseAt': endpoint['close'], 'status': 'resolved' if ready else 'pending',
                 'referenceClose': forecast['referenceClose'], 'endpointClose': bar['c'] if ready else None,
                 'priceReturn': bar['c'] / forecast['referenceClose'] - 1 if ready else None, 'members': {}}
        for role, direction in directions.items():
            change = value['priceReturn']
            outcome = 'pending' if not ready else 'abstain' if direction == 'abstain' else 'push' if direction == 'neutral' or change == 0 else 'correct' if (change > 0) == (direction == 'bullish') else 'incorrect'
            value['members'][role] = {'direction': direction, 'outcome': outcome}
        result['horizons'][horizon] = value
