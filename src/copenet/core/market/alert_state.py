"""Read-only linked-scan health projection; scan edits never rewrite alert intent."""
from .scans.resolver import resolve_scope


def project_alert_state(rule, scans: dict, watchlists: list[dict]) -> dict:
    wire = rule.to_wire()
    if not rule.enabled:
        return wire
    scan = scans.get(rule.scanId)
    if scan is None:
        return {**wire, 'status': 'scan_missing', 'error': 'The linked scan was archived; choose another price scan'}
    scope = resolve_scope(scan, watchlists)
    if scope['issues']:
        return {**wire, 'status': 'scan_blocked', 'error': 'Fix the linked scan: ' + '; '.join(scope['issues'])}
    if 'prices' not in scan['sources'] or rule.symbol not in scope['resolvedSymbols']:
        return {**wire, 'status': 'scan_scope_changed', 'error': 'This symbol is no longer in the linked price scan; edit the scan or select another'}
    if not scan['enabled']:
        return {**wire, 'status': 'scan_paused', 'error': 'The linked scan is paused; this alert evaluates only on manual runs until resumed'}
    return wire
