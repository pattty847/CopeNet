from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from copenet.host import api as host_api
from copenet.host.api import create_app


def test_agents_ping_endpoint_returns_ok_status() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/agents/ping")

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["service"] == "agents"
    datetime.fromisoformat(payload["timestamp"])


def test_frontend_public_images_are_served_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frontend_dist = tmp_path / "dist"
    wallpaper_path = frontend_dist / "imgs" / "wallpaper.png"
    wallpaper_path.parent.mkdir(parents=True)
    wallpaper_path.write_bytes(b"test-image")
    monkeypatch.setattr(host_api, "_FRONTEND_DIST_DIR", frontend_dist)

    with TestClient(create_app()) as client:
        response = client.get("/imgs/wallpaper.png")

    assert response.status_code == 200
    assert response.content == wallpaper_path.read_bytes()


@pytest.mark.parametrize(
    "path",
    ["/agents", "/market", "/workflows", "/data-tools", "/observability", "/experiments"],
)
def test_frontend_section_paths_serve_the_spa(path: str) -> None:
    with TestClient(create_app()) as client:
        response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_unknown_frontend_root_path_still_returns_not_found() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/not-a-copenet-section")

    assert response.status_code == 404
