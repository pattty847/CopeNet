# ledgerly

A small personal expense ledger. Standard library only; Python 3.11+.

## Usage

```bash
python -m ledgerly.cli --store ledger.json add 2026-08-04 -47.30 "Groceries" --category food
python -m ledgerly.cli --store ledger.json list --month 2026-08
python -m ledgerly.cli --store ledger.json balance
python -m ledgerly.cli --store ledger.json report --month 2026-08
python -m ledgerly.cli --store ledger.json import-csv sample/bank_export.csv --category food
```

Programmatic use:

```python
from ledgerly import Ledger, Transaction

ledger = Ledger()
ledger.add(Transaction(date="2026-08-01", amount="2400.00", description="Paycheck", category="income"))
ledger.add(Transaction(date="2026-08-04", amount="-47.30", description="Groceries", category="food"))
print(ledger.summary("2026-08"))   # {'month': '2026-08', 'income': ..., 'expenses': ..., 'net': ..., 'count': 2}
```

## Layout

| Module | Role |
|---|---|
| `ledgerly/models.py` | `Transaction`, amount/date parsing, description normalization |
| `ledgerly/storage.py` | JSON load/save with schema version and atomic writes |
| `ledgerly/ledger.py` | `Ledger`: add/remove, balance, date-range and month queries, `summary` |
| `ledgerly/reports.py` | Category totals, monthly table, CSV export |
| `ledgerly/importers.py` | CSV import with column aliases and duplicate detection |
| `ledgerly/cli.py` | argparse front end |

## Development

```bash
python -m unittest discover -s tests -t .
python scripts/check.py     # unused imports, stray prints, then the tests
```
