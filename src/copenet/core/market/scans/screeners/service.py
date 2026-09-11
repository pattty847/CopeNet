"""Scope admission, immutable observations and explicit watchlist handoff."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from copenet.core._json_store import read_json, write_json_atomic
from copenet.core.market.scans.store import file_lock
from copenet.core.market.scans.service import finish_inflight
from .evaluate import evaluate
from .models import MAX_ROWS, PRESETS, VERSION, ScreenerConfig
from .source import fetch_snapshot


def now():
    return datetime.now(timezone.utc).isoformat()


class ScreenerService:
    def __init__(self, root: Path, watchlists, fetch=fetch_snapshot):
        self.root = root / "scans" / "screeners"
        self.watchlists = watchlists
        self.fetch = fetch
        self.task = None
        self.previews = {}

    def state(self):
        paths = sorted((self.root / "summaries").glob("*.json"), reverse=True)[:30]
        runs = [read_json(path, {}) for path in paths]
        latest_id = read_json(self.root / "latest.json", None)
        latest = self.get_run(latest_id) if latest_id else None
        if latest is not None:
            latest = {key: value for key, value in latest.items() if key != "observations"}
        return {"presets": PRESETS, "config": read_json(self.root / "config.json", ScreenerConfig().model_dump()),
                "latest": latest, "running": self.task is not None and not self.task.done(),
                "history": [{k: run[k] for k in ("id", "startedAt", "finishedAt", "status", "error")} for run in runs]}

    def preview(self, config: ScreenerConfig):
        self.previews = {key: value for key, value in self.previews.items() if value[0] > time.monotonic()}
        if len(self.previews) >= 100:
            self.previews.pop(next(iter(self.previews)))
        token = uuid4().hex
        self.previews[token] = (time.monotonic() + 600, config)
        return {"scopeToken": token, "config": config.model_dump(), "maxRows": MAX_ROWS,
                "scope": "US-listed common shares on NASDAQ, NYSE and AMEX; one TradingView request for all five screens.",
                "notes": ["Dollar volume is current price × 30-day average share volume, an approximation.",
                          "Quotes may be delayed; daily metrics may include an unfinished session.",
                          "No candles, filings or model calls are fetched. No automatic schedule is created."]}

    def start(self, config: ScreenerConfig, token: str):
        admitted = self.previews.get(token)
        if admitted is None or admitted[0] < time.monotonic() or admitted[1] != config:
            raise ValueError("Preview the current universe before running; previews expire after 10 minutes")
        if self.task is not None and not self.task.done():
            raise ValueError("A screener run is already active")
        lease = file_lock(self.root / "execution.lock", blocking=False)
        lease.__enter__()
        self.previews.pop(token)
        self.task = asyncio.create_task(self._run(config, lease))
        return {"running": True}

    async def _run(self, config, lease):
        run = {"id": uuid4().hex, "version": VERSION, "startedAt": now(), "finishedAt": None,
               "status": "running", "error": None, "config": config.model_dump(), "presets": PRESETS,
               "source": "TradingView via tvscreener 0.4.1", "sourceTimestamp": None,
               "priceBasis": "TradingView screener snapshot; not canonical CopeNet candles",
               "accountScope": "excluded"}
        try:
            source = await finish_inflight(asyncio.to_thread(self.fetch, config))
            run.update(evaluate(source, config))
            run.update({"status": "complete", "received": source["received"], "truncated": source["truncated"],
                        "observations": source["rows"]})
        except asyncio.CancelledError:
            run.update(status="error", error="The host stopped during screening; run again")
            raise
        except Exception as exc:
            run.update(status="error", error=str(exc) if isinstance(exc, ValueError) else "Screening failed; the previous snapshot is retained")
        finally:
            run["finishedAt"] = now()
            try:
                filename = f"{run['startedAt'].replace(':', '')}-{run['id']}.json"
                write_json_atomic(self.root / "runs" / filename, run)
                write_json_atomic(self.root / "summaries" / filename, {key: run[key] for key in ("id", "startedAt", "finishedAt", "status", "error")})
                if run["status"] == "complete":
                    write_json_atomic(self.root / "latest.json", run["id"])
                    write_json_atomic(self.root / "config.json", config.model_dump())
            finally:
                lease.__exit__(None, None, None)

    def get_run(self, identifier: str):
        paths = list((self.root / "runs").glob(f"*-{identifier}.json"))
        if not paths:
            raise ValueError("Screener run not found")
        return read_json(paths[0], None)

    def handoff(self, identifier: str, symbols: list[str], name: str):
        run = self.get_run(identifier)
        if run["status"] != "complete":
            raise ValueError("Only completed screener results can become a watchlist")
        available = {row["symbol"]: row for screen in run["screens"] for row in screen["rows"]}
        if not set(symbols).issubset(available):
            raise ValueError("Select symbols from this saved screener run")
        # Create-only: existing lists, including broker imports, cannot be overwritten.
        entries = [{"symbol": symbol, "name": available[symbol]["name"] or symbol} for symbol in dict.fromkeys(symbols)]
        self.watchlists.create_list(name, role="context", entries=entries, select=False)
        receipt = {"id": uuid4().hex, "runId": identifier, "symbols": list(dict.fromkeys(symbols)),
                   "watchlist": name, "createdAt": now(), "role": "context"}
        write_json_atomic(self.root / "handoffs" / f"{receipt['id']}.json", receipt)
        return receipt
