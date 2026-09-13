"""Command-line interface: add, list, remove, balance, report, import-csv."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .importers import ImportError_, import_csv
from .ledger import Ledger
from .models import Transaction
from .reports import format_money, render_month, to_csv
from .storage import StoreError, load_transactions, save_transactions

DEFAULT_STORE = "ledger.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledgerly", description="Personal expense ledger")
    parser.add_argument("--store", default=DEFAULT_STORE, help="Path to the ledger JSON file")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="Record a transaction")
    add.add_argument("date")
    add.add_argument("amount")
    add.add_argument("description")
    add.add_argument("--category", default="other")

    listing = commands.add_parser("list", help="List transactions")
    listing.add_argument("--month", help="Only this YYYY-MM month")
    listing.add_argument("--csv", action="store_true", help="Emit CSV instead of a table")

    remove = commands.add_parser("remove", help="Remove a transaction by id")
    remove.add_argument("id")

    balance = commands.add_parser("balance", help="Print the running balance")
    balance.add_argument("--until", help="Only count transactions up to this date")

    report = commands.add_parser("report", help="Monthly report")
    report.add_argument("--month", required=True)

    importer = commands.add_parser("import-csv", help="Import transactions from a CSV file")
    importer.add_argument("path")
    importer.add_argument("--category", default="other")
    return parser


def cmd_add(args: argparse.Namespace) -> int:
    store = Path(args.store)
    try:
        ledger = Ledger(load_transactions(store))
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        tx = ledger.add(
            Transaction(date=args.date, amount=args.amount, description=args.description, category=args.category)
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    save_transactions(store, list(ledger.transactions()))
    print(f"added {tx.id} {tx.date.isoformat()} {format_money(tx.amount)} {tx.description}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = Path(args.store)
    if not store.exists():
        print(f"error: no ledger at {store}", file=sys.stderr)
        return 2
    try:
        ledger = Ledger(load_transactions(store))
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        rows = ledger.in_month(args.month) if args.month else list(ledger.transactions())
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.csv:
        sys.stdout.write(to_csv(rows))
        return 0
    if not rows:
        print("(no transactions)")
        return 0
    for tx in rows:
        print(f"{tx.id}  {tx.date.isoformat()}  {format_money(tx.amount):>12}  {tx.category:<10} {tx.description}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    store = Path(args.store)
    if not store.exists():
        print(f"error: no ledger at {store}", file=sys.stderr)
        return 2
    try:
        ledger = Ledger(load_transactions(store))
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not ledger.remove(args.id):
        print(f"error: no transaction with id {args.id}", file=sys.stderr)
        return 1
    save_transactions(store, list(ledger.transactions()))
    print(f"removed {args.id}")
    return 0


def cmd_balance(args: argparse.Namespace) -> int:
    store = Path(args.store)
    if not store.exists():
        print(f"error: no ledger at {store}", file=sys.stderr)
        return 2
    try:
        ledger = Ledger(load_transactions(store))
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        print(format_money(ledger.balance(until=args.until)))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store = Path(args.store)
    if not store.exists():
        print(f"error: no ledger at {store}", file=sys.stderr)
        return 2
    try:
        ledger = Ledger(load_transactions(store))
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        print(render_month(ledger, args.month))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_import_csv(args: argparse.Namespace) -> int:
    store = Path(args.store)
    try:
        ledger = Ledger(load_transactions(store))
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    source = Path(args.path)
    if not source.is_file():
        print(f"error: no CSV at {source}", file=sys.stderr)
        return 2
    try:
        result = import_csv(ledger, source.read_text(encoding="utf-8"), category=args.category)
    except ImportError_ as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    save_transactions(store, list(ledger.transactions()))
    print(f"imported {result.added_count} transaction(s), skipped {result.skipped_count} duplicate(s)")
    return 0


COMMANDS = {
    "add": cmd_add,
    "list": cmd_list,
    "remove": cmd_remove,
    "balance": cmd_balance,
    "report": cmd_report,
    "import-csv": cmd_import_csv,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
