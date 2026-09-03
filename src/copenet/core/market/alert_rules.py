"""Canonical alert definition and validation at RPC/persistence boundaries."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4

from .alert_evaluator import evaluator_request

# Provider aliases are not a security/market classification. In particular a future
# alias for a US ETF must not accidentally make it ineligible for alerts.
NON_EQUITY_SESSION_SYMBOLS = {'DXY', 'VIX', 'SOX', 'TNX', 'BTCUSD', 'ETHUSD'}


def supported_symbol(symbol: str) -> bool:
    return bool(re.fullmatch(r'[A-Z][A-Z0-9]{0,9}(?:[.-][AB])?', symbol)) and symbol not in NON_EQUITY_SESSION_SYMBOLS


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AlertRule:
    alertId: str
    revision: int
    symbol: str
    timeframe: str
    scanId: str
    enabled: bool
    oneShot: bool
    direction: str
    left: dict[str, Any]
    right: dict[str, Any]
    destinationIds: list[str]
    telegramAuthorized: bool
    status: str
    createdAt: str
    updatedAt: str
    lastEvaluatedAt: str | None = None
    lastCandleAt: str | None = None
    observation: dict[str, Any] | None = None
    error: str | None = None
    baseline: dict[str, Any] | None = None

    def to_wire(self) -> dict[str, Any]:
        wire = asdict(self)
        wire.pop('baseline')
        return wire


def validate_rule(raw: dict[str, Any], previous: AlertRule | None = None) -> AlertRule:
    symbol = str(raw.get('symbol', '')).strip().upper()
    if not supported_symbol(symbol):
        raise ValueError('Alerts support US-listed equity/ETF symbols only')
    timeframe = raw.get('timeframe', 'daily')
    if timeframe not in {'daily', 'weekly', 'monthly'}:
        raise ValueError('Choose daily, weekly, or monthly completed candles')
    if raw.get('direction') not in {'above', 'below'}:
        raise ValueError('Choose crosses above or crosses below')
    scan_id = raw.get('scanId', 'morning')
    if not isinstance(scan_id, str) or not scan_id.strip():
        raise ValueError('An evaluation scan is required')
    destinations = raw.get('destinationIds', [])
    if not isinstance(destinations, list) or any(not isinstance(value, str) or not value.strip() for value in destinations) or len(destinations) > 10:
        raise ValueError('Select valid notification destinations')
    for key in ('enabled', 'oneShot', 'telegramAuthorized'):
        if key in raw and not isinstance(raw[key], bool):
            raise ValueError(f'{key} must be a boolean')
    operands = evaluator_request({'action': 'validate', 'left': raw.get('left'), 'right': raw.get('right')})
    now = now_iso()
    enabled = raw.get('enabled', True)
    return AlertRule(
        alertId=previous.alertId if previous else f'alert-{uuid4().hex[:12]}',
        revision=previous.revision + 1 if previous else 1,
        symbol=symbol, timeframe=timeframe, scanId=scan_id.strip(), enabled=enabled,
        oneShot=raw.get('oneShot', True), direction=raw['direction'], left=operands['left'], right=operands['right'],
        destinationIds=list(dict.fromkeys(destinations)), telegramAuthorized=raw.get('telegramAuthorized', False),
        status='baseline_pending' if enabled else 'paused', createdAt=previous.createdAt if previous else now, updatedAt=now,
    )


def migrate_price_rule(raw: dict[str, Any]) -> AlertRule:
    """One-time persisted migration. Old intraday references cannot seed a close baseline."""
    status = raw['status']
    supported = supported_symbol(raw['symbol'])
    return AlertRule(alertId=raw['alert_id'], revision=1, symbol=raw['symbol'], timeframe='daily',
        scanId='morning', enabled=status == 'active' and supported, oneShot=True, direction=raw['direction'],
        left={'kind': 'price'}, right={'kind': 'constant', 'value': float(raw['threshold'])},
        destinationIds=[], telegramAuthorized=False, status=('baseline_pending' if supported else 'paused') if status == 'active' else status,
        error=None if supported else 'This migrated symbol is outside the supported US equity/ETF calendar; alert paused',
        createdAt=raw['created_at'], updatedAt=now_iso())
