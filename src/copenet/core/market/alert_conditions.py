"""Shared rule descriptions and historical comparisons for monitors and rehearsal."""
from dataclasses import asdict

from .alert_evaluator import evaluator_request


def operand_label(operand):
    if operand['kind'] == 'price':
        return operand.get('field', 'close').capitalize()
    if operand['kind'] == 'constant':
        return f"{operand['value']:g}"
    settings = ', '.join(f'{key}={value}' for key, value in operand['config'].items())
    return f"{operand['indicatorId'].upper()}({settings}) {operand['output']}"


def condition_label(rule):
    verb = 'reaches or moves' if rule.triggerMode == 'interaction' else 'crosses'
    return f"{operand_label(rule.left)} {verb} {rule.direction} {operand_label(rule.right)}"


def confirmation_label(rule):
    pair = rule.confirmation or {'left': {'kind': 'price', 'field': 'close'}, 'right': rule.right, 'direction': rule.direction}
    return f"{operand_label(pair['left'])} is at or {pair['direction']} {operand_label(pair['right'])} at candle close"


def reached(left, right, direction):
    if left is None or right is None:
        return False
    return left >= right if direction == 'above' else left <= right


def calculate(bars, rule, *, confirmation=False):
    pair = rule.confirmation if confirmation and rule.confirmation else {
        'left': {'kind': 'price', 'field': 'close'} if confirmation else rule.left,
        'right': rule.right,
    }
    return evaluator_request({'action': 'evaluate', 'timeframe': rule.timeframe,
        'bars': [asdict(bar) for bar in bars], 'left': pair['left'], 'right': pair['right']})['points']


def chart_snapshot(bars, points, reference):
    return {'bars': [asdict(bar) for bar in bars[-80:]], 'points': points[-80:],
            'priceBasis': 'split_adjusted', 'reference': reference}


def confirmation_result(rule, point):
    direction = rule.confirmation['direction'] if rule.confirmation else rule.direction
    if point['left'] is None or point['right'] is None:
        return 'unavailable'
    return 'confirmed' if reached(point['left'], point['right'], direction) else 'not_confirmed'
