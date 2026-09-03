"""One durable alert store for chart price levels and technical indicator conditions."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, replace
import fcntl
import json
from pathlib import Path
import threading
from typing import Any

from copenet.core._json_store import append_jsonl, read_json, write_json_atomic
from .alert_rules import AlertRule, migrate_price_rule, now_iso, validate_rule


class AlertStore:
    def __init__(self, market_root: Path):
        self.root = market_root / 'alerts'
        self._path = self.root / 'rules.json'
        self._events_path = self.root / 'events.jsonl'
        self._lock = threading.RLock()

    @contextmanager
    def transaction(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with self._lock, (self.root / 'rules.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def list(self, *, symbol: str | None = None) -> list[AlertRule]:
        with self.transaction():
            rules = self._load()
        return sorted([rule for rule in rules if symbol is None or rule.symbol == symbol.upper()], key=lambda rule: rule.createdAt, reverse=True)

    def save(self, raw: dict[str, Any]) -> AlertRule:
        with self.transaction():
            rules = self._load()
            previous = next((rule for rule in rules if rule.alertId == raw.get('alertId')), None)
            if raw.get('alertId') and previous is None:
                raise ValueError('Alert no longer exists')
            if previous and raw.get('revision') != previous.revision:
                raise ValueError('Alert changed elsewhere; reload before saving')
            if raw.get('enabled', True) and sum(rule.enabled for rule in rules if not previous or rule.alertId != previous.alertId) >= 500:
                raise ValueError('Enabled alert limit reached (500); pause an alert before arming another')
            rule = validate_rule(raw, previous)
            self._save([item for item in rules if item.alertId != rule.alertId] + [rule])
            return rule

    def cancel(self, alert_id: str) -> AlertRule:
        with self.transaction():
            rules = self._load()
            for index, rule in enumerate(rules):
                if rule.alertId == alert_id:
                    updated = replace(rule, enabled=False, status='cancelled', updatedAt=now_iso(), revision=rule.revision + 1)
                    rules[index] = updated
                    self._save(rules)
                    return updated
        raise ValueError('Alert no longer exists')

    def events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.transaction():
            return self._events()[-limit:][::-1]

    def _events(self) -> list[dict[str, Any]]:
        if not self._events_path.exists():
            return []
        rows = []
        with self._events_path.open() as handle:
            for line in handle:
                if not line.endswith('\n'):
                    raise ValueError('Alert evidence log has an interrupted write; preserve and repair it before continuing')
                rows.append(json.loads(line))
        return rows

    def _append_event(self, event: dict[str, Any]) -> dict[str, Any]:
        existing = next((row for row in self._events() if row.get('eventId') == event['eventId']), None)
        if existing is not None:
            return existing
        append_jsonl(self._events_path, event)
        return event

    def _load(self) -> list[AlertRule]:
        payload = read_json(self._path, {'version': 2, 'alerts': []})
        if not isinstance(payload, dict) or not isinstance(payload.get('alerts'), list):
            raise ValueError('Invalid alert store')
        if payload.get('version') is None:
            rules = [migrate_price_rule(row) for row in payload['alerts']]
            self._save(rules)
            return rules
        if payload.get('version') != 2:
            raise ValueError('Unsupported alert store version; no data was changed')
        return [AlertRule(**row) for row in payload['alerts']]

    def _save(self, rules: list[AlertRule]) -> None:
        write_json_atomic(self._path, {'version': 2, 'alerts': [asdict(rule) for rule in rules]})


def resolve_alert_store(runtime) -> AlertStore:
    store = getattr(runtime, '_alert_store', None)
    if store is None:
        store = AlertStore(runtime.store.root_dir)
        runtime._alert_store = store
    return store


def delivery_rule_active(root: Path, alert_id: str, revision: int) -> bool:
    return any(rule.alertId == alert_id and rule.revision == revision and rule.status not in {'paused', 'cancelled'}
               for rule in AlertStore(root).list())
