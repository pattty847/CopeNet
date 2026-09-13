"""JSON persistence for a ledger file.

The on-disk shape is `{"schema": 1, "transactions": [record, ...]}`. Writes go
through a temp file and rename so a crash never leaves a half-written ledger.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from .models import Transaction

SCHEMA_VERSION = 1


class StoreError(Exception):
    """Raised when a ledger file cannot be read or has an unexpected shape."""


def load_transactions(path: Path) -> list[Transaction]:
    """Return every transaction in the file, or an empty list if it does not exist."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreError(f"cannot read ledger {path}: {exc}") from exc
    if not isinstance(raw, dict) or "transactions" not in raw:
        raise StoreError(f"ledger {path} has an unexpected shape")
    schema = raw.get("schema")
    if schema != SCHEMA_VERSION:
        raise StoreError(f"ledger {path} has schema {schema!r}; expected {SCHEMA_VERSION}")
    rows = raw["transactions"]
    if not isinstance(rows, list):
        raise StoreError(f"ledger {path} transactions must be a list")
    try:
        return [Transaction.from_record(row) for row in rows]
    except (ValueError, TypeError) as exc:
        raise StoreError(f"ledger {path} contains an invalid transaction: {exc}") from exc


def save_transactions(path: Path, transactions: list[Transaction]) -> None:
    """Atomically write the ledger file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "transactions": [tx.to_record() for tx in transactions],
    }
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
