"""Core value types: transactions, amounts, dates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import uuid

CATEGORIES = ("food", "rent", "transport", "utilities", "income", "other")

_WHITESPACE = re.compile(r"\s+")


def new_transaction_id() -> str:
    return uuid.uuid4().hex[:12]


def parse_amount(text: str | Decimal | int | float) -> Decimal:
    """Parse a money amount into a Decimal with two places.

    Accepts "12.50", "$12.50", "1,250.00", "-4" and numeric types. Rejects
    anything that is not a finite number.
    """
    if isinstance(text, Decimal):
        value = text
    elif isinstance(text, (int, float)):
        value = Decimal(str(text))
    else:
        cleaned = str(text).strip().replace("$", "").replace(",", "")
        if not cleaned:
            raise ValueError("amount is empty")
        try:
            value = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"invalid amount: {text!r}") from exc
    if not value.is_finite():
        raise ValueError(f"invalid amount: {text!r}")
    return value.quantize(Decimal("0.01"))


def parse_date(text: str | date) -> date:
    """Parse an ISO date (YYYY-MM-DD)."""
    if isinstance(text, date):
        return text
    cleaned = str(text).strip()
    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"invalid date: {text!r} (expected YYYY-MM-DD)") from exc


def normalize_description(text: str) -> str:
    """Collapse whitespace and casefold so 'Coffee  Shop' and 'coffee shop' match."""
    return _WHITESPACE.sub(" ", str(text or "")).strip().casefold()


def validate_category(category: str) -> str:
    normalized = str(category or "other").strip().lower()
    if normalized not in CATEGORIES:
        raise ValueError(f"unknown category: {category!r} (expected one of {', '.join(CATEGORIES)})")
    return normalized


@dataclass(frozen=True)
class Transaction:
    """One ledger line. Positive amounts are income, negative amounts are spend."""

    date: date
    amount: Decimal
    description: str
    category: str = "other"
    id: str = field(default_factory=new_transaction_id)

    def __post_init__(self) -> None:
        object.__setattr__(self, "date", parse_date(self.date))
        object.__setattr__(self, "amount", parse_amount(self.amount))
        object.__setattr__(self, "category", validate_category(self.category))
        object.__setattr__(self, "description", str(self.description).strip())
        if not self.description:
            raise ValueError("description is required")

    @property
    def month_key(self) -> str:
        return f"{self.date.year:04d}-{self.date.month:02d}"

    @property
    def is_income(self) -> bool:
        return self.amount > 0

    def to_record(self) -> dict:
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "amount": str(self.amount),
            "description": self.description,
            "category": self.category,
        }

    @classmethod
    def from_record(cls, record: dict) -> "Transaction":
        try:
            return cls(
                id=str(record["id"]),
                date=record["date"],
                amount=record["amount"],
                description=record["description"],
                category=record.get("category", "other"),
            )
        except KeyError as exc:
            raise ValueError(f"transaction record is missing field {exc.args[0]!r}") from exc
