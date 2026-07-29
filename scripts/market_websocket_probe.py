"""Capture a bounded Yahoo Finance WebSocket session for capability analysis."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from copenet.core.market.stream_probe import StreamProbeConfig, capture_yahoo_stream


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture Yahoo stream messages and connection failures until a hard stop."
    )
    parser.add_argument("symbols", nargs="+", help="Symbols to subscribe to.")
    parser.add_argument("--start-at", required=True, help="Timezone-aware ISO start timestamp.")
    parser.add_argument("--end-at", required=True, help="Timezone-aware ISO hard-stop timestamp.")
    parser.add_argument(
        "--expected-date",
        help="Optional local YYYY-MM-DD guard that makes a scheduled run one-shot.",
    )
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--heartbeat-seconds", type=float, default=15)
    parser.add_argument("--max-reconnects", type=int, default=5)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    data_root = Path(os.environ.get("COPNET_DATA_DIR", Path.home() / ".copenet"))
    output_directory = args.output_directory or data_root / "market" / "probes" / "websocket"
    try:
        config = StreamProbeConfig(
            symbols=tuple(dict.fromkeys(symbol.strip().upper() for symbol in args.symbols)),
            start_at=datetime.fromisoformat(args.start_at),
            end_at=datetime.fromisoformat(args.end_at),
            expected_date=args.expected_date,
            heartbeat_seconds=args.heartbeat_seconds,
            max_reconnects=args.max_reconnects,
        )
        summary = asyncio.run(
            capture_yahoo_stream(config, output_directory=output_directory)
        )
    except (OSError, ValueError) as exc:
        print(f"market WebSocket probe failed: {exc}", file=sys.stderr)
        return 2

    print(
        f"Yahoo stream probe {summary['status']}: "
        f"{summary['message_count']} messages, "
        f"{summary['disconnect_count']} disconnects, "
        f"{summary['reconnect_count']} reconnects"
    )
    if summary.get("summary_path"):
        print(f"Summary saved to {summary['summary_path']}")
    return 0 if summary["status"] in {"completed", "skipped_wrong_date"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
