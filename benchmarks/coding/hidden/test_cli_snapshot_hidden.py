"""Hidden behavior snapshot for the refactor-preserve task.

Every handler's observable behavior on a missing or corrupt store must be
unchanged by the refactor: `add` and `import-csv` create a missing store, the
read-only commands report it, and every command reports a corrupt store the
same way.
"""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from ledgerly.cli import main


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class MissingStoreSnapshot(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = str(Path(self._tmp.name) / "ledger.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_read_commands_report_missing_store_with_exit_2(self):
        for argv in (["list"], ["remove", "x"], ["balance"], ["report", "--month", "2026-08"]):
            with self.subTest(argv=argv):
                code, out, err = run_cli("--store", self.store, *argv)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertEqual(err.strip(), f"error: no ledger at {self.store}")

    def test_add_creates_a_missing_store(self):
        code, out, err = run_cli("--store", self.store, "add", "2026-08-04", "-1", "x")
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith("added "))
        self.assertTrue(Path(self.store).exists())

    def test_import_csv_creates_a_missing_store(self):
        csv_path = Path(self._tmp.name) / "bank.csv"
        csv_path.write_text("date,amount,description\n2026-08-20,-9.99,Streaming\n", encoding="utf-8")
        code, out, err = run_cli("--store", self.store, "import-csv", str(csv_path))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.strip(), "imported 1 transaction(s), skipped 0 duplicate(s)")

    def test_import_csv_missing_csv_after_store_check(self):
        code, out, err = run_cli("--store", self.store, "import-csv", str(Path(self._tmp.name) / "nope.csv"))
        self.assertEqual(code, 2)
        self.assertIn("no CSV at", err)


class CorruptStoreSnapshot(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = str(Path(self._tmp.name) / "ledger.json")
        Path(self.store).write_text("{not json", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_every_command_reports_corrupt_store_with_exit_2(self):
        csv_path = Path(self._tmp.name) / "bank.csv"
        csv_path.write_text("date,amount,description\n2026-08-20,-9.99,Streaming\n", encoding="utf-8")
        for argv in (
            ["add", "2026-08-04", "-1", "x"],
            ["list"],
            ["remove", "x"],
            ["balance"],
            ["report", "--month", "2026-08"],
            ["import-csv", str(csv_path)],
        ):
            with self.subTest(argv=argv):
                code, out, err = run_cli("--store", self.store, *argv)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertTrue(err.startswith("error: cannot read ledger"), err)


if __name__ == "__main__":
    unittest.main()
