"""Hidden acceptance tests for the feature-multifile task (tags on transactions)."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from ledgerly import Ledger, Transaction
from ledgerly.cli import main
from ledgerly.storage import load_transactions, save_transactions


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TagModelTests(unittest.TestCase):
    def test_default_is_empty_tuple(self):
        tx = Transaction(date="2026-08-04", amount="-1", description="x")
        self.assertEqual(tx.tags, ())

    def test_tags_are_lowercased_stripped_and_deduplicated_in_order(self):
        tx = Transaction(date="2026-08-04", amount="-1", description="x", tags=(" Work ", "travel", "work"))
        self.assertEqual(tx.tags, ("work", "travel"))

    def test_record_round_trip_carries_tags(self):
        tx = Transaction(date="2026-08-04", amount="-1", description="x", tags=("a", "b"))
        record = tx.to_record()
        self.assertEqual(list(record["tags"]), ["a", "b"])
        self.assertEqual(Transaction.from_record(record).tags, ("a", "b"))

    def test_old_records_without_tags_still_load(self):
        record = {"id": "abc123", "date": "2026-08-04", "amount": "-1.00", "description": "x", "category": "food"}
        self.assertEqual(Transaction.from_record(record).tags, ())


class TagLedgerTests(unittest.TestCase):
    def test_with_tag_filters_case_insensitively(self):
        ledger = Ledger(
            [
                Transaction(date="2026-08-01", amount="-1", description="a", tags=("work",)),
                Transaction(date="2026-08-02", amount="-2", description="b", tags=("home",)),
                Transaction(date="2026-08-03", amount="-3", description="c", tags=("work", "home")),
            ]
        )
        self.assertEqual([t.description for t in ledger.with_tag("WORK")], ["a", "c"])
        self.assertEqual([t.description for t in ledger.with_tag("home")], ["b", "c"])
        self.assertEqual(ledger.with_tag("nope"), [])


class TagStorageTests(unittest.TestCase):
    def test_existing_v1_file_without_tags_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "transactions": [
                            {"id": "abc123", "date": "2026-08-04", "amount": "-1.00", "description": "x", "category": "food"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            rows = load_transactions(path)
            self.assertEqual(rows[0].tags, ())

    def test_saved_file_round_trips_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            save_transactions(path, [Transaction(date="2026-08-04", amount="-1", description="x", tags=("work",))])
            self.assertEqual(load_transactions(path)[0].tags, ("work",))


class TagCliTests(unittest.TestCase):
    def test_add_with_repeated_tag_and_list_by_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = str(Path(tmp) / "ledger.json")
            code, _, err = run_cli("--store", store, "add", "2026-08-04", "-1", "lunch", "--tag", "Work", "--tag", "food")
            self.assertEqual(code, 0, err)
            code, _, err = run_cli("--store", store, "add", "2026-08-05", "-2", "movie", "--tag", "home")
            self.assertEqual(code, 0, err)
            code, out, err = run_cli("--store", store, "list", "--tag", "work")
            self.assertEqual(code, 0, err)
            lines = out.strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn("lunch", lines[0])
            code, out, _ = run_cli("--store", store, "list")
            self.assertEqual(len(out.strip().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
