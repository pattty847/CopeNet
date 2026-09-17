"""The served frontend must never be heuristically cached into a stale deploy.

`index.html` used to ship `etag` and `last-modified` with no `Cache-Control`, which lets a
browser invent its own freshness lifetime. The shell HTML is the only file that names the
current hashed bundles, so holding it for hours makes a rebuilt frontend look like it never
deployed — and an iOS home-screen install has no reload control to break out with.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from copenet.core.orchestrator import Orchestrator
from copenet.host.api import _FRONTEND_DIST_DIR, create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app(Orchestrator(recover_interrupted_runs=False)))


def _requires_build() -> None:
    if not (_FRONTEND_DIST_DIR / "index.html").is_file():
        pytest.skip("frontend build not present")


def test_shell_html_revalidates_on_every_load(client: TestClient) -> None:
    _requires_build()
    response = client.get("/")
    assert response.status_code == 200
    cache_control = response.headers.get("cache-control", "")
    assert "no-cache" in cache_control
    # Revalidation, not refetching: the ETag is what keeps the usual case a bodiless 304.
    assert response.headers.get("etag")


def test_client_routed_sections_revalidate_too(client: TestClient) -> None:
    _requires_build()
    for path in ("/agents", "/market", "/market/AAPL"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "no-cache" in response.headers.get("cache-control", ""), path


def test_hashed_bundles_are_immutable(client: TestClient) -> None:
    assets = _FRONTEND_DIST_DIR / "assets"
    if not assets.is_dir():
        pytest.skip("frontend build not present")
    bundle = next((path for path in assets.iterdir() if path.suffix in {".js", ".css"}), None)
    if bundle is None:
        pytest.skip("no hashed bundle in build")
    response = client.get(f"/assets/{bundle.name}")
    assert response.status_code == 200
    cache_control = response.headers.get("cache-control", "")
    assert "immutable" in cache_control
    assert "max-age=31536000" in cache_control


def test_pwa_root_assets_revalidate(client: TestClient) -> None:
    if not (_FRONTEND_DIST_DIR / "manifest.webmanifest").is_file():
        pytest.skip("frontend build not present")
    # These keep their filenames across builds, so a long cache would pin a stale app
    # identity onto a home-screen install.
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    assert "no-cache" in response.headers.get("cache-control", "")
