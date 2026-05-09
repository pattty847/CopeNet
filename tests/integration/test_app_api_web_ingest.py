from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.host.api import create_app


class FakeWebIngestionService:
    async def extract_url(self, *, url: str, max_chars: int = 20000):
        class _Result:
            def to_public_dict(self):
                return {
                    "url": url,
                    "title": "Example Article",
                    "text": "Hello from a clean extract.",
                    "markdown": "# Example Article\n\nSource: https://example.com\n\nHello from a clean extract.\n",
                    "excerpt": "Hello from a clean extract.",
                    "wordCount": 5,
                }

        assert max_chars == 1200
        return _Result()


@pytest.fixture
def web_app_client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    monkeypatch.setenv("COPNET_TOKEN", "dev-token")
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={},
    )
    _, token = orchestrator.register_app(app_id="subtext", display_name="Subtext")
    app = create_app(orchestrator, web_ingestion_service=FakeWebIngestionService())
    with TestClient(app) as client:
        yield client, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_web_extract_requires_auth(web_app_client) -> None:
    client, _ = web_app_client
    response = client.post("/api/v1/web/extract", json={"url": "https://example.com"})
    assert response.status_code == 401


def test_web_extract_returns_readable_document(web_app_client) -> None:
    client, token = web_app_client
    response = client.post(
        "/api/v1/web/extract",
        headers=_auth(token),
        json={"url": "https://example.com", "maxChars": 1200},
    )
    assert response.status_code == 200
    payload = response.json()["document"]
    assert payload["title"] == "Example Article"
    assert payload["wordCount"] == 5
    assert "Hello from a clean extract." in payload["markdown"]
