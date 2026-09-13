from decimal import Decimal
import unittest

from ledgerly import Ledger, Transaction
from ledgerly.importers import ImportError_, import_csv, map_columns, parse_rows

BANK_CSV = "Posted,Amt,Memo\n2026-08-04,-47.30,Groceries\n2026-08-18,-12.00,coffee   shop\n"


class ColumnMappingTests(unittest.TestCase):
    def test_maps_aliases_case_insensitively(self):
        self.assertEqual(map_columns(["Posted", "Amt", "Memo"]), {"date": 0, "amount": 1, "description": 2})
        self.assertEqual(map_columns(["description", "DATE", "amount"]), {"date": 1, "amount": 2, "description": 0})

    def test_missing_column_is_an_import_error(self):
        with self.assertRaises(ImportError_):
            map_columns(["date", "memo"])


class ParseRowsTests(unittest.TestCase):
    def test_parses_rows_with_category(self):
        rows = parse_rows(BANK_CSV, category="food")
        self.assertEqual([r.amount for r in rows], [Decimal("-47.30"), Decimal("-12.00")])
        self.assertTrue(all(r.category == "food" for r in rows))

    def test_bad_row_reports_line_number(self):
        with self.assertRaises(ImportError_) as caught:
            parse_rows("date,amount,description\n2026-08-04,abc,Groceries\n")
        self.assertIn("line 2", str(caught.exception))


class ImportTests(unittest.TestCase):
    def test_import_adds_new_rows(self):
        ledger = Ledger()
        result = import_csv(ledger, BANK_CSV, category="food")
        self.assertEqual(result.added_count, 2)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(len(ledger), 2)

    def test_import_skips_rows_already_in_ledger(self):
        ledger = Ledger([Transaction(date="2026-08-04", amount="-47.30", description="Groceries", category="food")])
        result = import_csv(ledger, BANK_CSV, category="food")
        self.assertEqual(result.added_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(len(ledger), 2)

    def test_import_dedupes_case_and_whitespace_insensitively(self):
        ledger = Ledger([Transaction(date="2026-08-18", amount="-12.00", description="Coffee Shop", category="food")])
        result = import_csv(ledger, BANK_CSV, category="food")
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual([t.description for t in ledger.transactions()], ["Coffee Shop", "Groceries"])

    def test_import_keeps_same_amount_on_different_dates(self):
        csv_text = "date,amount,description\n2026-08-20,-9.99,Streaming\n2026-08-21,-9.99,Streaming\n"
        ledger = Ledger()
        result = import_csv(ledger, csv_text)
        self.assertEqual(result.added_count, 2)

    def test_import_dedupes_within_one_file(self):
        csv_text = "date,amount,description\n2026-08-20,-9.99,Streaming\n2026-08-20,-9.99,streaming\n"
        result = import_csv(Ledger(), csv_text)
        self.assertEqual((result.added_count, result.skipped_count), (1, 1))


if __name__ == "__main__":
    unittest.main()
