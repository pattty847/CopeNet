"""Run a conservative, read-only yfinance intraday capability probe."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from copenet.core._json_store import write_json_atomic
from copenet.core.market.data_probe import (
    DEFAULT_INTRADAY_PROBE_SPECS,
    IntradayProbeSpec,
    probe_report_has_errors,
    run_yfinance_intraday_probe,
    safe_probe_filename_part,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure actual yfinance intraday/session/volume capabilities without changing production state."
    )
    parser.add_argument("symbols", nargs="*", default=["AAPL"], help="Symbols to probe; defaults to AAPL.")
    parser.add_argument(
        "--spec",
        action="append",
        default=[],
        metavar="INTERVAL:PERIOD",
        help="Repeatable request specification, e.g. --spec 5m:1mo.",
    )
    parser.add_argument(
        "--timezone",
        default="America/New_York",
        help="Session-label timezone; the current US-equity profile requires America/New_York.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=1.0,
        help="Sequential delay between symbol requests; defaults to 1 second.",
    )
    parser.add_argument("--output", type=Path, help="Optional summary JSON path.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    return parser


def _parse_specs(values: list[str]) -> tuple[IntradayProbeSpec, ...]:
    if not values:
        return DEFAULT_INTRADAY_PROBE_SPECS
    specs: list[IntradayProbeSpec] = []
    for raw in values:
        interval, separator, period = raw.partition(":")
        if not separator or not interval.strip() or not period.strip():
            raise ValueError(f"invalid --spec {raw!r}; expected INTERVAL:PERIOD")
        specs.append(IntradayProbeSpec(interval=interval.strip(), period=period.strip()))
    return tuple(specs)


def _default_output_path(report: dict) -> Path:
    data_root = Path(os.environ.get("COPNET_DATA_DIR", Path.home() / ".copenet"))
    stamp = datetime.fromisoformat(report["generated_at"]).strftime("%Y%m%dT%H%M%SZ")
    symbols = "-".join(safe_probe_filename_part(item["symbol"]) for item in report["symbols"])
    return data_root / "market" / "probes" / f"{stamp}-{symbols}.json"


def _print_summary(report: dict, output_path: Path) -> None:
    print(f"yfinance {report['vendor_version']} · {report['request_count']} sequential request(s)")
    for item in report["symbols"]:
        capabilities = item["capabilities"]
        intervals = ", ".join(capabilities["supported_intervals"]) or "none"
        assumed_extended = ", ".join(capabilities["assumed_extended_price_intervals"]) or "none"
        print(
            f"{item['symbol']}: intervals={intervals} · "
            f"assumed extended-price intervals={assumed_extended}"
        )
        for result in item["results"]:
            warnings = "; ".join(result["warnings"])
            suffix = f" · warning: {warnings}" if warnings else ""
            print(
                f"  {result['interval']}/{result['period']}: {result['status']} · "
                f"{result['row_count']} rows · last={result['last_timestamp']}{suffix}"
            )
    print(f"Summary saved to {output_path}")


def main() -> int:
    args = _build_parser().parse_args()
    try:
        specs = _parse_specs(args.spec)
        report = run_yfinance_intraday_probe(
            args.symbols,
            specs=specs,
            timezone_name=args.timezone,
            pause_seconds=max(args.pause_seconds, 0),
        )
    except (OSError, ValueError) as exc:
        print(f"market data probe failed: {exc}", file=sys.stderr)
        return 2

    output_path = args.output or _default_output_path(report)
    write_json_atomic(output_path, report)
    _print_summary(report, output_path)
    if args.json:
        print(json.dumps(report, indent=2))
    return _probe_exit_code(report)


def _probe_exit_code(report: dict) -> int:
    return 1 if probe_report_has_errors(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
