"""SQLite-backed Market delivery records, with a process-wide sender lease."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import sqlite3
from typing import Iterator


class MarketOutbox:
    def __init__(self, root: Path) -> None:
        self.directory = root / "notifications"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "deliveries.sqlite3"
        with self.connection() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS deliveries (id TEXT PRIMARY KEY, body TEXT NOT NULL)")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def sender_lock(self, *, blocking: bool = True) -> Iterator[bool]:
        with (self.directory / "sender.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def rows(self) -> list[dict]:
        with self.connection() as connection:
            return [json.loads(row[0]) for row in connection.execute("SELECT body FROM deliveries ORDER BY rowid DESC")]

    def insert(self, row: dict) -> dict:
        with self.connection() as connection:
            connection.execute("INSERT OR IGNORE INTO deliveries VALUES (?, ?)", (row["id"], json.dumps(row)))
            return json.loads(connection.execute("SELECT body FROM deliveries WHERE id=?", (row["id"],)).fetchone()[0])

    def save(self, row: dict) -> None:
        with self.connection() as connection:
            connection.execute("UPDATE deliveries SET body=? WHERE id=?", (json.dumps(row), row["id"]))
