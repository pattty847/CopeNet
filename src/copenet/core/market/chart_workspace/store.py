"""Transactional local chart persistence; no market data is fetched here."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

from .codec import encode, new_id
from .admissions import AdmissionStore
from .documents import DocumentStore
from .models import InstrumentRef
from .observations import ObservationStore
from ..forecasts.schema import FORECAST_SCHEMA, used_bytes as forecast_used_bytes


class ChartStore(ObservationStore, DocumentStore, AdmissionStore):
    def __init__(self, path: Path, *, capacity_bytes: int = 512 * 1024 * 1024):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.capacity_bytes = capacity_bytes
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, session_key TEXT
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, instrument_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, body TEXT NOT NULL,
                    UNIQUE(workspace_id,instrument_id)
                );
                CREATE TABLE IF NOT EXISTS resources (
                    id TEXT PRIMARY KEY, body TEXT NOT NULL, bytes INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY, session_key TEXT NOT NULL, capture_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, document_id TEXT NOT NULL, body TEXT NOT NULL,
                    created_at REAL NOT NULL, bound INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(session_key,capture_id)
                );
                CREATE TABLE IF NOT EXISTS observation_resources (
                    observation_id TEXT NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
                    resource_key TEXT NOT NULL, resource_id TEXT NOT NULL REFERENCES resources(id),
                    PRIMARY KEY(observation_id,resource_key)
                );
                CREATE INDEX IF NOT EXISTS observation_document ON observations(document_id);
                CREATE INDEX IF NOT EXISTS observation_session ON observations(session_key);
                CREATE INDEX IF NOT EXISTS observation_retention ON observations(bound,created_at);
                CREATE INDEX IF NOT EXISTS resource_references ON observation_resources(resource_id);
                CREATE TABLE IF NOT EXISTS operations (
                    batch_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, operation_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, body TEXT NOT NULL, receipt TEXT NOT NULL,
                    UNIQUE(document_id,operation_id)
                );
                CREATE TABLE IF NOT EXISTS render_receipts (
                    document_id TEXT NOT NULL, view_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    body TEXT NOT NULL, PRIMARY KEY(document_id,view_id,revision)
                );
                CREATE TABLE IF NOT EXISTS admissions (
                    session_key TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, run_id TEXT NOT NULL, observation_id TEXT NOT NULL,
                    state TEXT NOT NULL, PRIMARY KEY(session_key,idempotency_key)
                );
            """)
            db.executescript(FORECAST_SCHEMA)
        self.cleanup_orphans()

    @staticmethod
    def _used_bytes(db):
        return db.execute("SELECT COALESCE((SELECT SUM(bytes) FROM resources),0) + "
                          "COALESCE((SELECT SUM(length(CAST(body AS BLOB))) FROM observations),0) + "
                          "COALESCE((SELECT SUM(length(CAST(body AS BLOB))) FROM documents),0) + "
                          "COALESCE((SELECT SUM(length(CAST(body AS BLOB))+length(CAST(receipt AS BLOB))) FROM operations),0) + "
                          "COALESCE((SELECT SUM(length(CAST(body AS BLOB))) FROM render_receipts),0) + "
                          "COALESCE((SELECT SUM(length(session_key)+length(idempotency_key)+length(fingerprint)+length(run_id)+length(observation_id)+length(state)) FROM admissions),0) + "
                          "COALESCE((SELECT SUM(length(id)+COALESCE(length(session_key),0)) FROM workspaces),0)").fetchone()[0] + forecast_used_bytes(db)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def workspace(self, workspace_id: str, instrument: dict) -> dict:
        instrument = InstrumentRef.model_validate(instrument).model_dump()
        if not isinstance(workspace_id, str) or not 0 < len(workspace_id) <= 160:
            raise ValueError("workspaceId is required")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO workspaces VALUES (?,NULL)", (workspace_id,))
            row = db.execute("SELECT body FROM documents WHERE workspace_id=? AND instrument_id=?",
                             (workspace_id, instrument["instrumentId"])).fetchone()
            if row is None:
                document = {"documentId": new_id("chart"), "workspaceId": workspace_id,
                            "instrument": instrument, "revision": 0, "objects": []}
                if self._used_bytes(db) + len(encode(document).encode()) > self.capacity_bytes:
                    raise ValueError("Chart store capacity reached; document was not created")
                db.execute("INSERT INTO documents VALUES (?,?,?,?,?)", (
                    document["documentId"], workspace_id, instrument["instrumentId"], 0, encode(document)))
            else:
                document = json.loads(row["body"])
                if document["instrument"] != instrument:
                    raise ValueError("Instrument identity differs from this document")
            workspace = db.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
            return {"workspace": {"workspaceId": workspace_id, "sessionKey": workspace["session_key"]},
                    "document": document}

    def update_workspace(self, workspace_id: str, session_key: str | None) -> dict:
        if not isinstance(workspace_id, str) or not 0 < len(workspace_id) <= 160:
            raise ValueError("workspaceId is required")
        if session_key is not None and (not isinstance(session_key, str) or not 0 < len(session_key) <= 160):
            raise ValueError("sessionKey must be a session identifier or null")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT length(id)+COALESCE(length(session_key),0) FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
            replaced_bytes = previous[0] if previous else 0
            if self._used_bytes(db) - replaced_bytes + len(workspace_id.encode()) + len((session_key or "").encode()) > self.capacity_bytes:
                raise ValueError("Chart store capacity reached; session link was not changed")
            db.execute("INSERT INTO workspaces VALUES (?,?) ON CONFLICT(id) DO UPDATE SET session_key=excluded.session_key",
                       (workspace_id, session_key))
        return {"workspace": {"workspaceId": workspace_id, "sessionKey": session_key}}

    def cleanup_orphans(self, *, now: float | None = None) -> int:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("DELETE FROM observations WHERE bound=0 AND created_at<? AND id NOT IN (SELECT observation_id FROM forecast_requests) AND id NOT IN (SELECT observation_id FROM forecast_lanes)",
                               ((now or time.time()) - 86400,)).rowcount
            db.execute("DELETE FROM resources WHERE id NOT IN (SELECT resource_id FROM observation_resources) AND id NOT IN (SELECT resource_id FROM forecast_resources)")
            return count
