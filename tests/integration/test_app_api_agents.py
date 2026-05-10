from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from copenet.host.api import create_app


def test_agents_ping_endpoint_returns_ok_status() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/agents/ping")

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["service"] == "agents"
    datetime.fromisoformat(payload["timestamp"])
