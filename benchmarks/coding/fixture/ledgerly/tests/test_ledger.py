from datetime import date
from decimal import Decimal
import unittest

from ledgerly import Ledger, Transaction
from ledgerly.ledger import month_bounds


def tx(day: str, amount: str, description: str = "x", category: str = "other") -> Transaction:
    return Transaction(date=day, amount=amount, description=description, category=category)


class LedgerBasicsTests(unittest.TestCase):
    def test_add_and_remove(self):
        ledger = Ledger()
        first = ledger.add(tx("2026-08-01", "10"))
        ledger.add(tx("2026-08-02", "20"))
        self.assertEqual(len(ledger), 2)
        self.assertTrue(ledger.remove(first.id))
        self.assertFalse(ledger.remove(first.id))
        self.assertEqual([t.amount for t in ledger.transactions()], [Decimal("20.00")])

    def test_rejects_duplicate_ids(self):
        ledger = Ledger()
        first = ledger.add(tx("2026-08-01", "10"))
        with self.assertRaises(ValueError):
            ledger.add(Transaction(id=first.id, date="2026-08-02", amount="1", description="dup"))

    def test_balance_and_balance_until(self):
        ledger = Ledger([tx("2026-07-31", "100"), tx("2026-08-01", "-40"), tx("2026-08-15", "-10")])
        self.assertEqual(ledger.balance(), Decimal("50.00"))
        self.assertEqual(ledger.balance(until="2026-08-01"), Decimal("60.00"))


class DateRangeTests(unittest.TestCase):
    def test_month_bounds(self):
        self.assertEqual(month_bounds("2026-02"), (date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(month_bounds("2028-02"), (date(2028, 2, 1), date(2028, 2, 29)))
        with self.assertRaises(ValueError):
            month_bounds("2026-13")

    def test_between_is_inclusive_of_both_ends(self):
        ledger = Ledger([tx("2026-08-01", "1"), tx("2026-08-15", "2"), tx("2026-08-31", "3"), tx("2026-09-01", "4")])
        rows = ledger.between("2026-08-01", "2026-08-31")
        self.assertEqual([t.amount for t in rows], [Decimal("1.00"), Decimal("2.00"), Decimal("3.00")])

    def test_in_month_includes_last_day(self):
        ledger = Ledger([tx("2026-07-31", "-14.50", "Coffee"), tx("2026-08-01", "2400", "Pay", "income")])
        july = ledger.in_month("2026-07")
        self.assertEqual([t.description for t in july], ["Coffee"])
        self.assertEqual([t.description for t in ledger.in_month("2026-08")], ["Pay"])

    def test_between_rejects_reversed_range(self):
        with self.assertRaises(ValueError):
            Ledger().between("2026-08-31", "2026-08-01")


class SummaryTests(unittest.TestCase):
    def test_summary_splits_income_and_expenses(self):
        ledger = Ledger(
            [
                tx("2026-08-01", "2400", "Pay", "income"),
                tx("2026-08-04", "-47.30", "Groceries", "food"),
                tx("2026-08-31", "-12", "Coffee", "food"),
                tx("2026-09-01", "-99", "Next month", "food"),
            ]
        )
        summary = ledger.summary("2026-08")
        self.assertEqual(summary["income"], Decimal("2400.00"))
        self.assertEqual(summary["expenses"], Decimal("59.30"))
        self.assertEqual(summary["net"], Decimal("2340.70"))
        self.assertEqual(summary["count"], 3)


if __name__ == "__main__":
    unittest.main()
