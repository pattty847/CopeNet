from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from copenet.host.api import _FRONTEND_DIST_DIR, create_app


def test_agents_ping_endpoint_returns_ok_status() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/agents/ping")

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["service"] == "agents"
    datetime.fromisoformat(payload["timestamp"])


def test_frontend_public_images_are_served_when_present() -> None:
    wallpaper_path = _FRONTEND_DIST_DIR / "imgs" / "wallpaper.png"
    if not wallpaper_path.is_file():
        wallpaper_path.parent.mkdir(parents=True, exist_ok=True)
        wallpaper_path.write_bytes(b"test-image")

    with TestClient(create_app()) as client:
        response = client.get("/imgs/wallpaper.png")

    assert response.status_code == 200
    assert response.content == Path(wallpaper_path).read_bytes()
