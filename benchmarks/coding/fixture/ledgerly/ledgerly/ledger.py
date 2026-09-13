"""In-memory ledger operations."""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from .models import Transaction, parse_date


def month_bounds(month: str) -> tuple[date, date]:
    """Return the first and last day of a 'YYYY-MM' month."""
    try:
        year_text, month_text = month.strip().split("-")
        year, month_number = int(year_text), int(month_text)
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"invalid month: {month!r} (expected YYYY-MM)") from exc
    if not 1 <= month_number <= 12:
        raise ValueError(f"invalid month: {month!r} (expected YYYY-MM)")
    last_day = calendar.monthrange(year, month_number)[1]
    return date(year, month_number, 1), date(year, month_number, last_day)


class Ledger:
    """Ordered collection of transactions with query helpers."""

    def __init__(self, transactions: list[Transaction] | None = None) -> None:
        self._transactions: list[Transaction] = []
        self._ids: set[str] = set()
        for tx in transactions or []:
            self.add(tx)

    def __len__(self) -> int:
        return len(self._transactions)

    def transactions(self) -> tuple[Transaction, ...]:
        """Every transaction in insertion order."""
        return tuple(self._transactions)

    def add(self, tx: Transaction) -> Transaction:
        if tx.id in self._ids:
            raise ValueError(f"duplicate transaction id: {tx.id}")
        self._transactions.append(tx)
        self._ids.add(tx.id)
        return tx

    def remove(self, tx_id: str) -> bool:
        """Remove by id; return whether anything was removed."""
        if tx_id not in self._ids:
            return False
        self._transactions = [tx for tx in self._transactions if tx.id != tx_id]
        self._ids.discard(tx_id)
        return True

    def balance(self, *, until: date | str | None = None) -> Decimal:
        """Sum of all amounts, optionally only up to and including `until`."""
        limit = parse_date(until) if until is not None else None
        total = Decimal("0.00")
        for tx in self._transactions:
            if limit is not None and tx.date > limit:
                continue
            total += tx.amount
        return total

    def between(self, start: date | str, end: date | str) -> list[Transaction]:
        """Transactions dated within [start, end], both ends inclusive."""
        first, last = parse_date(start), parse_date(end)
        if last < first:
            raise ValueError("end date is before start date")
        return [tx for tx in self._transactions if first <= tx.date <= last]

    def in_month(self, month: str) -> list[Transaction]:
        """Transactions in a 'YYYY-MM' month."""
        first, last = month_bounds(month)
        return self.between(first, last)

    def summary(self, month: str) -> dict:
        """Income, expenses, net and count for one month."""
        rows = self.in_month(month)
        income = sum((tx.amount for tx in rows if tx.amount > 0), Decimal("0.00"))
        expenses = sum((-tx.amount for tx in rows if tx.amount < 0), Decimal("0.00"))
        return {
            "month": month,
            "income": income,
            "expenses": expenses,
            "net": income - expenses,
            "count": len(rows),
        }
