import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from ledgerly.cli import main


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = str(Path(self._tmp.name) / "ledger.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_add_then_list_and_balance(self):
        code, out, _ = run_cli("--store", self.store, "add", "2026-08-01", "2400", "Paycheck", "--category", "income")
        self.assertEqual(code, 0)
        self.assertIn("added", out)
        code, out, _ = run_cli("--store", self.store, "add", "2026-08-04", "-47.30", "Groceries", "--category", "food")
        self.assertEqual(code, 0)
        code, out, _ = run_cli("--store", self.store, "list")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 2)
        code, out, _ = run_cli("--store", self.store, "balance")
        self.assertEqual((code, out.strip()), (0, "$2,352.70"))

    def test_list_csv_output(self):
        run_cli("--store", self.store, "add", "2026-08-04", "-47.30", "Groceries", "--category", "food")
        code, out, _ = run_cli("--store", self.store, "list", "--csv")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "date,amount,description,category")

    def test_missing_store_is_a_clear_error(self):
        code, out, err = run_cli("--store", self.store, "list")
        self.assertEqual(code, 2)
        self.assertIn("no ledger at", err)
        self.assertEqual(out, "")

    def test_corrupt_store_is_a_store_error(self):
        Path(self.store).write_text("{not json", encoding="utf-8")
        code, _, err = run_cli("--store", self.store, "balance")
        self.assertEqual(code, 2)
        self.assertIn("cannot read ledger", err)

    def test_remove_unknown_id(self):
        run_cli("--store", self.store, "add", "2026-08-04", "-1", "x")
        code, _, err = run_cli("--store", self.store, "remove", "nope")
        self.assertEqual(code, 1)
        self.assertIn("no transaction with id", err)

    def test_import_csv_reports_counts(self):
        csv_path = Path(self._tmp.name) / "bank.csv"
        csv_path.write_text("date,amount,description\n2026-08-20,-9.99,Streaming\n2026-08-20,-9.99,streaming\n", encoding="utf-8")
        code, out, _ = run_cli("--store", self.store, "import-csv", str(csv_path))
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "imported 1 transaction(s), skipped 1 duplicate(s)")
        saved = json.loads(Path(self.store).read_text(encoding="utf-8"))
        self.assertEqual(len(saved["transactions"]), 1)


if __name__ == "__main__":
    unittest.main()
