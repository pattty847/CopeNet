"""Deterministic chart images from an alert's frozen evidence; no data acquisition."""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


PHASE_LABELS = {
    'interaction': 'First interaction - awaiting close',
    'confirmed': 'Confirmed at candle close',
    'not_confirmed': 'Not confirmed at candle close',
    'unavailable': 'Confirmation unavailable at candle close',
}


def operand_label(operand: dict) -> str:
    if operand['kind'] == 'price':
        return operand.get('field', 'close').title()
    if operand['kind'] == 'constant':
        return f"Level {operand['value']:g}"
    settings = ', '.join(f'{key}={value}' for key, value in operand['config'].items())
    return f"{operand['indicatorId'].upper()} {operand['output']} ({settings})"


def render_alert_chart(event: dict) -> bytes:
    """An evidence chart, not a screenshot of the operator's account or workspace."""
    snapshot = event['chartSnapshot']
    bars = snapshot['bars'][-80:]
    if not bars:
        raise ValueError('No captured candles for alert chart')
    image = Image.new('RGB', (1200, 820), '#101419')
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=17)
    small = ImageFont.load_default(size=14)
    title = ImageFont.load_default(size=28)

    def label(x, y, text, fill='#9aa6b5', face=small, max_width=1080):
        if draw.textlength(text, font=face) > max_width:
            low, high = 0, len(text)
            while low < high:
                middle = (low + high + 1) // 2
                if draw.textlength(text[:middle] + '…', font=face) <= max_width:
                    low = middle
                else:
                    high = middle - 1
            text = text[:low] + '…'
        draw.text((x, y), text, fill=fill, font=face)

    label(36, 25, f"{event['symbol']}  /  {event['timeframe']}  /  Alert snapshot", '#e5ebf2', title)
    label(36, 66, PHASE_LABELS.get(event.get('phase'), 'Completed candle signal'), '#d6b879', font)
    label(36, 97, event['condition'])
    label(36, 120, f"Observed at {event.get('observedAt') or event['evaluatedAt']}   |   Split-adjusted candles")
    left, right = 60, 1090
    step = (right - left) / len(bars)
    xs = {bar['t']: left + (index + .5) * step for index, bar in enumerate(bars)}

    def axis(values, top, bottom):
        low, high = min(values), max(values)
        padding = max((high - low) * .1, abs(high) * .005, .01)
        low, high = low - padding, high + padding
        def y(value):
            return bottom - (value - low) / (high - low) * (bottom - top)
        for index in range(5):
            value = low + (high - low) * index / 4
            draw.line((left, y(value), right, y(value)), fill='#252d37')
            label(right + 12, y(value) - 7, f'{value:,.2f}', max_width=88)
        return y

    y = axis([bar[key] for bar in bars for key in ('l', 'h')], 168, 454)
    for bar in bars:
        x = xs[bar['t']]
        color = '#70bca8' if bar['c'] >= bar['o'] else '#c78388'
        draw.line((x, y(bar['h']), x, y(bar['l'])), fill=color, width=1)
        top, bottom = sorted((y(bar['o']), y(bar['c'])))
        draw.rectangle((x - max(1, step * .28), top, x + max(1, step * .28), max(top + 1, bottom)), fill=color)
    rule = event.get('rule', {})
    label(36, 480, 'Compared values (separate scale)', '#d8e0e9', font)
    for key, offset, color in [('left', 505, '#91b9ef'), ('right', 528, '#d6b879')]:
        name = snapshot.get(f'{key}Label') or (operand_label(rule[key]) if key in rule else key.title())
        label(36, offset, f'{key.title()}: {name}', color)
    points = [point for point in snapshot['points'] if point['t'] in xs]
    values = [point[key] for point in points for key in ('left', 'right') if point[key] is not None]
    if values:
        sy = axis(values, 570, 696)
        for key, color in [('left', '#91b9ef'), ('right', '#d6b879')]:
            previous = None
            for point in points:
                current = (xs[point['t']], sy(point[key])) if point[key] is not None else None
                if previous is not None and current is not None:
                    draw.line((*previous, *current), fill=color, width=2)
                if current is not None:
                    draw.ellipse((current[0]-2, current[1]-2, current[0]+2, current[1]+2), fill=color)
                previous = current
    else:
        label(60, 610, 'Compared values unavailable')
    for bar, x in [(bars[0], left), (bars[-1], right - 85)]:
        label(x, 712, datetime.fromtimestamp(bar['t'], timezone.utc).strftime('%Y-%m-%d'))
    reference = ('Previous completed indicator values; current candle is provisional'
                 if snapshot['reference'] == 'previous_completed' else 'Completed candle values')
    label(36, 751, f'Reference: {reference}')
    label(36, 779, 'Frozen scan evidence. Detection occurs at scan time; this is not a live quote.')
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()
