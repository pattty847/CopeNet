"""CSV import with column aliasing and duplicate detection."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import io

from .ledger import Ledger
from .models import Transaction, normalize_description, parse_amount, parse_date

COLUMN_ALIASES = {
    "date": ("date", "posted", "posted_at", "when"),
    "amount": ("amount", "amt", "value", "total"),
    "description": ("description", "memo", "desc", "payee", "narrative"),
}


class ImportError_(ValueError):
    """Raised when a CSV cannot be mapped onto transactions."""


@dataclass
class ImportResult:
    added: list[Transaction] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)

    @property
    def added_count(self) -> int:
        return len(self.added)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def map_columns(header: list[str]) -> dict[str, int]:
    """Resolve which CSV column index carries date, amount and description."""
    normalized = [str(name or "").strip().lower() for name in header]
    mapping: dict[str, int] = {}
    for field_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[field_name] = normalized.index(alias)
                break
        else:
            raise ImportError_(f"CSV is missing a {field_name} column (accepted: {', '.join(aliases)})")
    return mapping


def parse_rows(text: str, *, category: str = "other") -> list[Transaction]:
    """Turn CSV text into transactions. Blank lines are ignored."""
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise ImportError_("CSV is empty")
    mapping = map_columns(rows[0])
    transactions: list[Transaction] = []
    for line_number, row in enumerate(rows[1:], start=2):
        try:
            transactions.append(
                Transaction(
                    date=parse_date(row[mapping["date"]]),
                    amount=parse_amount(row[mapping["amount"]]),
                    description=row[mapping["description"]],
                    category=category,
                )
            )
        except (IndexError, ValueError) as exc:
            raise ImportError_(f"line {line_number}: {exc}") from exc
    return transactions


def dedupe_key(tx: Transaction) -> tuple:
    """Two rows are the same transaction when date, amount and normalized description match."""
    return (tx.date, tx.amount, normalize_description(tx.description))


def import_csv(ledger: Ledger, text: str, *, category: str = "other") -> ImportResult:
    """Add every new row from `text` to `ledger`, skipping rows it already has."""
    result = ImportResult()
    seen = {dedupe_key(tx) for tx in ledger.transactions()}
    for tx in parse_rows(text, category=category):
        key = dedupe_key(tx)
        if key in seen:
            result.skipped.append(tx.to_record())
            continue
        seen.add(key)
        ledger.add(tx)
        result.added.append(tx)
    return result
