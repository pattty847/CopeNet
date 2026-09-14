"""Freeze optional account context before an alert event enters its durable journal."""
from .positions import position_context
from .webull.client import selected_account
from .webull.sync import load_snapshot


def attach_position_context(event: dict, history=None) -> dict:
    if not event['rule'].get('includePosition', False):
        return event
    account = selected_account()
    context = position_context(event['symbol'], load_snapshot(), account['accountId'] if account else None, history)
    return {**event, 'position': context}
