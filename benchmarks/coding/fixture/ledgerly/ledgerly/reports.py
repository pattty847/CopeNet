"""Report rendering: category totals, monthly table, CSV export."""

from __future__ import annotations

import csv
from decimal import Decimal
import io

from .ledger import Ledger
from .models import CATEGORIES, Transaction

CSV_COLUMNS = ("date", "amount", "description", "category")


def category_totals(transactions: list[Transaction], totals: dict | None = None) -> dict[str, Decimal]:
    """Sum amounts per category. Pass an existing dict to accumulate into it."""
    if totals is None:
        totals = {}
    for tx in transactions:
        totals[tx.category] = totals.get(tx.category, Decimal("0.00")) + tx.amount
    return totals


def format_money(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def render_month(ledger: Ledger, month: str) -> str:
    """Render a fixed-width monthly table followed by the net line."""
    rows = ledger.in_month(month)
    totals = category_totals(rows)
    lines = [f"Month {month}", f"{'Category':<12}{'Total':>14}", "-" * 26]
    for category in CATEGORIES:
        value = totals.get(category, Decimal("0.00"))
        if value == 0 and category not in totals:
            continue
        lines.append(f"{category:<12}{format_money(value):>14}")
    summary = ledger.summary(month)
    lines.append("-" * 26)
    lines.append(f"{'Income':<12}{format_money(summary['income']):>14}")
    lines.append(f"{'Expenses':<12}{format_money(-summary['expenses']):>14}")
    lines.append(f"{'Net':<12}{format_money(summary['net']):>14}")
    lines.append(f"{summary['count']} transaction(s)")
    return "\n".join(lines)


def to_csv(transactions: list[Transaction]) -> str:
    """Export transactions as CSV with a fixed header order."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for tx in transactions:
        writer.writerow([tx.date.isoformat(), str(tx.amount), tx.description, tx.category])
    return buffer.getvalue()
