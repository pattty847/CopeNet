from decimal import Decimal
import unittest

from ledgerly import Ledger, Transaction
from ledgerly.reports import CSV_COLUMNS, category_totals, format_money, to_csv


def tx(day: str, amount: str, description: str = "x", category: str = "other") -> Transaction:
    return Transaction(date=day, amount=amount, description=description, category=category)


class CategoryTotalsTests(unittest.TestCase):
    def test_a_sums_by_category(self):
        totals = category_totals([tx("2026-08-01", "-10", "a", "food"), tx("2026-08-02", "-5", "b", "food"), tx("2026-08-03", "-7", "c", "rent")])
        self.assertEqual(totals["food"], Decimal("-15.00"))
        self.assertEqual(totals["rent"], Decimal("-7.00"))

    def test_b_starts_from_an_empty_dict_each_call(self):
        totals = category_totals([tx("2026-08-01", "-3", "a", "transport")])
        self.assertEqual(totals, {"transport": Decimal("-3.00")})

    def test_c_accumulates_into_a_provided_dict(self):
        running = {"food": Decimal("-1.00")}
        category_totals([tx("2026-08-01", "-2", "a", "food")], running)
        self.assertEqual(running, {"food": Decimal("-3.00")})


class FormattingTests(unittest.TestCase):
    def test_format_money(self):
        self.assertEqual(format_money(Decimal("1234.5")), "$1,234.50")
        self.assertEqual(format_money(Decimal("-4")), "-$4.00")

    def test_to_csv_header_and_rows(self):
        text = to_csv([tx("2026-08-04", "-47.30", "Groceries", "food")])
        lines = text.splitlines()
        self.assertEqual(lines[0], ",".join(CSV_COLUMNS))
        self.assertEqual(lines[0], "date,amount,description,category")
        self.assertEqual(lines[1], "2026-08-04,-47.30,Groceries,food")


if __name__ == "__main__":
    unittest.main()
