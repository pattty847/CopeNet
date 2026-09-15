"""Read-only historical rule rehearsal: the chart registry, no acquisition or delivery."""
from datetime import datetime, timezone

from .alert_candles import completed_candles
from .alert_conditions import calculate, confirmation_result, reached
from .price_history import chart_history_window


def rehearse_rule(rule, history, *, now=None):
    now = now or datetime.now(timezone.utc)
    result = {'symbol': rule.symbol, 'timeframe': rule.timeframe, 'matches': [], 'candles': 0,
              'matchCount': 0, 'status': 'missing_history', 'error': 'No cached price history',
              'note': 'Historical conditions only; scan timing and intraperiod paths cannot be reconstructed. This is not a profitability backtest.'}
    if history is None:
        return result
    candles = completed_candles(history, rule.timeframe, now)
    if candles.status not in {'ready', 'stale'}:
        return {**result, 'status': candles.status, 'error': candles.error}
    times = {bar.t for bar in chart_history_window(history.derive(timeframe=rule.timeframe), rule.timeframe)}
    bars = [bar for bar in candles.bars if bar.t in times]
    points = calculate(bars, rule)
    confirmations = calculate(bars, rule, confirmation=True) if rule.triggerMode == 'interaction' else []
    matches, eligible = [], 0
    latched = False
    for index in range(1, len(points)):
        prior, point = points[index - 1], points[index]
        if any(value is None for value in (prior['left'], prior['right'], point['left'], point['right'])):
            continue
        eligible += 1
        if rule.triggerMode == 'interaction':
            matching = reached(point['left'], prior['right'], rule.direction)
            hit = matching and not latched
            latched = matching
            reference = prior['right']
        else:
            hit = (prior['left'] <= prior['right'] and point['left'] > point['right']) if rule.direction == 'above' else (prior['left'] >= prior['right'] and point['left'] < point['right'])
            reference = point['right']
        if hit:
            matches.append({'t': point['t'], 'candleCloseAt': candles.close_times[point['t']],
                'leftValue': point['left'], 'rightValue': reference,
                'phase': confirmation_result(rule, confirmations[index]) if confirmations else 'confirmed'})
    return {**result, 'status': candles.status, 'error': candles.error, 'matches': matches[-100:][::-1],
            'candles': eligible, 'matchCount': len(matches), 'from': bars[0].t if bars else None,
            'through': bars[-1].t if bars else None, 'cacheUpdatedAt': history.updated_at}
