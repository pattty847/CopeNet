"""Forecast tables share the chart store's resource lifetime and transaction boundary."""

FORECAST_SCHEMA = """
CREATE TABLE IF NOT EXISTS forecast_requests (
    id TEXT PRIMARY KEY, session_key TEXT NOT NULL, document_id TEXT NOT NULL REFERENCES documents(id),
    observation_id TEXT NOT NULL REFERENCES observations(id), fingerprint TEXT NOT NULL,
    status TEXT NOT NULL, body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS forecast_session ON forecast_requests(session_key);
CREATE TABLE IF NOT EXISTS forecast_lanes (
    request_id TEXT NOT NULL REFERENCES forecast_requests(id), lane TEXT NOT NULL,
    session_key TEXT NOT NULL, run_id TEXT, observation_id TEXT NOT NULL REFERENCES observations(id),
    body TEXT NOT NULL, PRIMARY KEY(request_id,lane)
);
CREATE INDEX IF NOT EXISTS forecast_lane_session ON forecast_lanes(session_key);
CREATE TABLE IF NOT EXISTS forecast_resources (
    request_id TEXT NOT NULL REFERENCES forecast_requests(id), resource_id TEXT NOT NULL REFERENCES resources(id),
    PRIMARY KEY(request_id,resource_id)
);
CREATE TABLE IF NOT EXISTS forecast_snapshots (
    id TEXT PRIMARY KEY, body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forecast_evaluations (
    request_id TEXT NOT NULL REFERENCES forecast_requests(id), snapshot_id TEXT NOT NULL REFERENCES forecast_snapshots(id),
    PRIMARY KEY(request_id,snapshot_id)
);
CREATE TABLE IF NOT EXISTS forecast_events (
    id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES forecast_requests(id),
    snapshot_id TEXT NOT NULL REFERENCES forecast_snapshots(id), body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forecast_amendments (
    id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES forecast_requests(id), body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forecast_render_receipts (
    request_id TEXT NOT NULL REFERENCES forecast_requests(id), view_id TEXT NOT NULL, revision INTEGER NOT NULL,
    body TEXT NOT NULL, PRIMARY KEY(request_id,view_id,revision)
);
"""


def used_bytes(db) -> int:
    tables = ('forecast_requests', 'forecast_lanes', 'forecast_snapshots', 'forecast_events',
              'forecast_amendments', 'forecast_render_receipts')
    return sum(db.execute(f'SELECT COALESCE(SUM(length(CAST(body AS BLOB))),0) FROM {table}').fetchone()[0]
               for table in tables) + sum(db.execute(f'SELECT COUNT(*) * 256 FROM {table}').fetchone()[0]
                                         for table in ('forecast_resources', 'forecast_evaluations'))
