"""Vendor revisions to bars a forecast has already been evaluated on.

The current cache is authoritative. Every evaluation replays the whole trade from it, and
a revision is judged by what it did to the result, not by how large it was: a two-cent
correction to a low that no level sat near changes nothing and passes quietly, while one
that moves a fill, an exit or a resolved horizon is accepted AND recorded as a visible
`revision` event carrying the old and new outcome. A fixed price tolerance would be
arbitrary (two cents is nothing at $160 and a trigger at $3) and would still freeze on the
first revision that mattered.

Volume is never compared: the trade and the horizons read only open, high, low and close,
and vendors revise daily volume after the close as a matter of routine.
"""
from __future__ import annotations

import math

from .candles import digest

PRICE_FIELDS = ('o', 'h', 'l', 'c')
_FIELD_NAMES = {'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close'}


def same_prices(old: dict, new: dict) -> bool:
    # The tight tolerance only absorbs float arithmetic from reversing a later split.
    return all(math.isclose(old[key], new[key], rel_tol=1e-10, abs_tol=1e-10) for key in PRICE_FIELDS)


def missing_sessions(previous: list[dict], current: list[dict]) -> list[str]:
    """Sessions evaluated before that the current bars no longer reach: a gap, not a revision."""
    present = {bar['date'] for bar in current}
    return [bar['date'] for bar in previous if bar['date'] not in present]


def bar_revisions(previous: list[dict], current: list[dict]) -> list[dict]:
    by_day = {bar['date']: bar for bar in current}
    changes = []
    for old in previous:
        new = by_day.get(old['date'])
        if new is None or same_prices(old, new):
            continue
        for key in PRICE_FIELDS:
            if not math.isclose(old[key], new[key], rel_tol=1e-10, abs_tol=1e-10):
                changes.append({'date': old['date'], 'field': _FIELD_NAMES[key], 'before': old[key], 'after': new[key]})
    return changes


def outcome_view(evaluation: dict, through_date: str | None) -> dict:
    """What a revision could have changed: trade events on already-evaluated sessions and
    horizons that had already resolved."""
    events = [{key: item.get(key) for key in ('type', 'date', 'price', 'fraction', 'targetIndex')}
              for item in evaluation.get('events', [])
              if item['type'] not in {'revision', 'revision_notice'} and through_date is not None and item['date'] <= through_date]
    horizons = {name: {'endpointClose': value.get('endpointClose'),
                       'outcomes': {role: member.get('outcome') for role, member in value.get('members', {}).items()}}
                for name, value in evaluation.get('horizons', {}).items() if value.get('status') == 'resolved'}
    return {'events': events, 'horizons': horizons, 'state': evaluation.get('state')}


def outcome_changed(before: dict, after: dict) -> bool:
    if before['events'] != after['events']:
        return True
    return any(after['horizons'].get(name) != value for name, value in before['horizons'].items())


def revision_event(forecast_id: str, changes: list[dict], before: dict, after: dict, now, policy_version: str) -> dict:
    bars = '; '.join(f"{item['date']} {item['field']} {item['before']:g} → {item['after']:g}" for item in changes)
    return {'eventId': digest([forecast_id, 'revision', changes]), 'type': 'revision', 'date': now.date().isoformat(),
            'recordedAt': now.isoformat(), 'policyVersion': policy_version,
            'reason': f'The vendor revised bars this forecast had already been evaluated on ({bars}), and the replay '
                      f'on the corrected bars changed the recorded outcome from {before["state"]} to {after["state"]}.',
            'bars': changes, 'before': before, 'after': after}
