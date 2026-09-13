from datetime import date
from decimal import Decimal
import unittest

from ledgerly.models import Transaction, normalize_description, parse_amount, parse_date


class ParseAmountTests(unittest.TestCase):
    def test_plain_and_formatted_amounts(self):
        self.assertEqual(parse_amount("12.5"), Decimal("12.50"))
        self.assertEqual(parse_amount("$1,250.00"), Decimal("1250.00"))
        self.assertEqual(parse_amount("-4"), Decimal("-4.00"))
        self.assertEqual(parse_amount(3), Decimal("3.00"))

    def test_rejects_garbage(self):
        for bad in ("", "abc", "1.2.3", "NaN", "inf"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_amount(bad)


class ParseDateTests(unittest.TestCase):
    def test_iso_dates(self):
        self.assertEqual(parse_date("2026-08-04"), date(2026, 8, 4))
        self.assertEqual(parse_date(date(2026, 1, 2)), date(2026, 1, 2))

    def test_rejects_other_formats(self):
        with self.assertRaises(ValueError):
            parse_date("08/04/2026")


class NormalizeDescriptionTests(unittest.TestCase):
    def test_collapses_whitespace_and_case(self):
        self.assertEqual(normalize_description("  Coffee   Shop "), "coffee shop")
        self.assertEqual(normalize_description("COFFEE SHOP"), normalize_description("coffee shop"))


class TransactionTests(unittest.TestCase):
    def test_round_trips_through_record(self):
        tx = Transaction(date="2026-08-04", amount="-47.3", description=" Groceries ", category="food")
        again = Transaction.from_record(tx.to_record())
        self.assertEqual(again, tx)
        self.assertEqual(again.description, "Groceries")
        self.assertEqual(again.month_key, "2026-08")

    def test_rejects_unknown_category_and_blank_description(self):
        with self.assertRaises(ValueError):
            Transaction(date="2026-08-04", amount="1", description="x", category="fun")
        with self.assertRaises(ValueError):
            Transaction(date="2026-08-04", amount="1", description="   ")


if __name__ == "__main__":
    unittest.main()
