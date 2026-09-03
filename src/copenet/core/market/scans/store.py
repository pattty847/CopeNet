"""Atomic definitions and immutable completed runs, protected across host processes."""
from __future__ import annotations

import fcntl
import asyncio
import re
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path
from uuid import uuid4

from copenet.core._json_store import read_json, write_json_atomic
from .definitions import default_scan, validate_scan


@contextmanager
def file_lock(path: Path, *, blocking: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise ValueError("Another market scan is running; wait for it to finish") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@asynccontextmanager
async def execution_lease(path: Path, *, wait: bool):
    """Admitted scheduled work waits politely; manual callers get immediate feedback."""
    while True:
        lease = file_lock(path, blocking=False)
        try:
            lease.__enter__()
            break
        except ValueError:
            if not wait:
                raise
            await asyncio.sleep(0.25)
    try:
        yield
    finally:
        lease.__exit__(None, None, None)


class ScanStore:
    def __init__(self, root: Path, watchlists):
        self.root = root / "scans"
        self.path = self.root / "definitions.json"
        with file_lock(self.root / "definitions.lock"):
            if not self.path.exists():
                write_json_atomic(self.path, {"version": 1, "scans": [default_scan(watchlists.scan_lists())]})

    def definitions(self) -> list[dict]:
        payload = read_json(self.path, None)
        if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("scans"), list):
            raise ValueError("Scan definitions are invalid; preserved on disk for recovery")
        return [validate_scan(scan) for scan in payload["scans"]]

    def get(self, identifier: str) -> dict:
        for scan in self.definitions():
            if scan["id"] == identifier:
                return scan
        raise ValueError("Scan not found; refresh the list")

    def save(self, raw: dict) -> dict:
        scan = validate_scan(raw)
        with file_lock(self.root / "definitions.lock"):
            scans = self.definitions()
            existing = next((item for item in scans if item["id"] == scan["id"]), None)
            if existing and existing["revision"] != scan["revision"]:
                raise ValueError("This scan changed in another window; reload before saving")
            if scan["id"] and not existing:
                raise ValueError("Scan no longer exists; reload before saving")
            if not existing and len(scans) >= 100:
                raise ValueError("Scan limit reached (100)")
            scan["id"] = scan["id"] or uuid4().hex
            scan["revision"] += 1
            scans = [scan if item["id"] == scan["id"] else item for item in scans]
            if not existing:
                scans.append(scan)
            write_json_atomic(self.path, {"version": 1, "scans": scans})
        return scan

    def archive(self, identifier: str) -> None:
        with file_lock(self.root / "definitions.lock"):
            scan = self.get(identifier)
            write_json_atomic(self.root / "archived" / f"{identifier}-{scan['revision']}.json", scan)
            write_json_atomic(self.path, {"version": 1, "scans": [s for s in self.definitions() if s["id"] != identifier]})

    def runs(self, limit: int = 100) -> list[dict]:
        return [read_json(path, {}) for path in sorted((self.root / "runs").glob("*.json"), reverse=True)[:limit]]

    def run(self, identifier: str) -> dict:
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", identifier):
            raise ValueError("Invalid run id")
        matches = list((self.root / "runs").glob(f"*-{identifier}.json"))
        if not matches:
            raise ValueError("Scan run not found")
        return read_json(matches[0], {})

    def run_summaries(self, limit: int = 100) -> list[dict]:
        # Indexes are generated alongside durable progress updates. Readers never
        # race another process writing an index; a missing/stale index is projected.
        summaries = []
        for path in sorted((self.root / "runs").glob("*.json"), reverse=True)[:limit]:
            summary_path = self.root / "summaries" / path.name
            summary = read_json(summary_path, None)
            if summary is None or summary_path.stat().st_mtime_ns < path.stat().st_mtime_ns:
                summary = compact_run(read_json(path, {}))
            summaries.append(summary)
        return summaries

    def save_run(self, run: dict) -> None:
        name = f"{run['startedAt'].replace(':', '')}-{run['id']}.json"
        write_json_atomic(self.root / "runs" / name, run)
        write_json_atomic(self.root / "summaries" / name, compact_run(run))


def compact_run(run: dict) -> dict:
    fields = ("id", "scanId", "name", "status", "startedAt", "finishedAt", "revision", "reason", "scheduledAt",
              "sources", "resolvedSymbols", "contextSymbols", "cacheHits", "fetched", "errors")
    return {field: run[field] for field in fields if field in run}
