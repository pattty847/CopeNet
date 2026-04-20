from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from copenet.core.media import MediaDependencyError
from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.host.api import create_app


class FakeMediaAsset:
    def __init__(self, asset_id: str, title: str, transcript_excerpt: str) -> None:
        self.asset_id = asset_id
        self.title = title
        self.transcript_excerpt = transcript_excerpt

    def to_public_dict(self) -> dict[str, object]:
        return {
            "assetId": self.asset_id,
            "appId": "subtext",
            "sourceType": "url",
            "sourceUrl": "https://example.com/video",
            "sourcePath": None,
            "title": self.title,
            "mediaPath": "/tmp/example.mp4",
            "transcriptPath": "/tmp/example.md",
            "transcriptSource": "youtube-captions",
            "transcriptExcerpt": self.transcript_excerpt,
            "metadata": {"source": "youtube-captions"},
            "durationSeconds": 12.5,
            "latencyMs": 420,
            "createdAt": "2026-04-15T00:00:00+00:00",
            "updatedAt": "2026-04-15T00:00:00+00:00",
        }

    def to_detail_dict(self) -> dict[str, object]:
        payload = self.to_public_dict()
        payload["transcriptContent"] = f"Full transcript for {self.title}."
        return payload


class FakeMediaService:
    def __init__(self, tmp_path: Path) -> None:
        self.assets = [
            FakeMediaAsset("media-1", "Clip One", "First imported transcript excerpt."),
        ]
        self.last_import: dict[str, object] | None = None
        self.last_download: dict[str, object] | None = None
        self.download_path = tmp_path / "downloads" / "funny-clip.mp4"
        self.download_path.parent.mkdir(parents=True, exist_ok=True)
        self.download_path.write_bytes(b"fake-video")

    async def import_url(
        self,
        *,
        app_id: str,
        url: str,
        include_timestamps: bool = True,
        prefer_captions: bool = True,
        whisper_model: str = "base",
    ) -> FakeMediaAsset:
        self.last_import = {
            "app_id": app_id,
            "url": url,
            "include_timestamps": include_timestamps,
            "prefer_captions": prefer_captions,
            "whisper_model": whisper_model,
        }
        asset = FakeMediaAsset("media-2", "Imported Clip", "Transcript imported through fake media service.")
        self.assets.insert(0, asset)
        return asset

    async def stream_import_url(
        self,
        *,
        app_id: str,
        url: str,
        include_timestamps: bool = True,
        prefer_captions: bool = True,
        whisper_model: str = "base",
    ):
        yield {"type": "progress", "stage": "download", "percent": 10.0, "message": f"Downloading {url} for {app_id}."}
        yield {"type": "chunk", "text": "first chunk"}
        yield {"type": "done", "asset": self.assets[0].to_public_dict()}

    async def download_url(
        self,
        *,
        url: str,
    ) -> tuple[Path, dict[str, object]]:
        self.last_download = {
            "url": url,
        }
        return self.download_path, {
            "title": "Funny Clip",
            "filename": self.download_path.name,
            "source": "yt-dlp",
        }

    def list_assets(self, *, app_id: str, limit: int = 50) -> list[dict[str, object]]:
        return [asset.to_public_dict() for asset in self.assets[:limit]]

    def get_asset_detail(self, *, app_id: str, asset_id: str) -> dict[str, object] | None:
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset.to_detail_dict()
        return None


class BrokenMediaService(FakeMediaService):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path)

    async def import_url(self, **kwargs):  # type: ignore[override]
        raise MediaDependencyError("yt-dlp is not installed.")


@pytest.fixture
def media_app_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    monkeypatch.setenv("COPNET_TOKEN", "dev-token")
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={},
    )
    _, token = orchestrator.register_app(app_id="subtext", display_name="Subtext")
    media_service = FakeMediaService(tmp_path)
    app = create_app(orchestrator, media_service=media_service)
    with TestClient(app) as client:
        yield client, token, media_service


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_media_assets_require_auth_and_list_records(media_app_client) -> None:
    client, token, _ = media_app_client

    unauthorized = client.get("/api/v1/media/assets")
    assert unauthorized.status_code == 401

    response = client.get("/api/v1/media/assets", headers=_auth(token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["assets"][0]["assetId"] == "media-1"
    assert payload["assets"][0]["title"] == "Clip One"


def test_media_import_returns_asset_and_uses_request_fields(media_app_client) -> None:
    client, token, media_service = media_app_client

    response = client.post(
        "/api/v1/media/import",
        headers=_auth(token),
        json={
            "url": "https://youtu.be/example",
            "includeTimestamps": False,
            "preferCaptions": True,
            "whisperModel": "tiny",
        },
    )
    assert response.status_code == 200
    asset = response.json()["asset"]
    assert asset["assetId"] == "media-2"
    assert asset["title"] == "Imported Clip"
    assert media_service.last_import == {
        "app_id": "subtext",
        "url": "https://youtu.be/example",
        "include_timestamps": False,
        "prefer_captions": True,
        "whisper_model": "tiny",
    }


def test_media_asset_detail_returns_transcript_content(media_app_client) -> None:
    client, token, _ = media_app_client

    response = client.get("/api/v1/media/assets/media-1", headers=_auth(token))
    assert response.status_code == 200
    asset = response.json()["asset"]
    assert asset["assetId"] == "media-1"
    assert asset["transcriptContent"] == "Full transcript for Clip One."


def test_media_import_stream_exposes_sse_events(media_app_client) -> None:
    client, token, _ = media_app_client

    with client.stream(
        "GET",
        "/api/v1/media/import/stream",
        headers=_auth(token),
        params={"url": "https://example.com/video"},
    ) as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())

    assert "event: progress" in text
    assert "event: chunk" in text
    assert "event: done" in text
    assert '"Downloading https://example.com/video for subtext."' in text


def test_media_import_dependency_error_maps_to_service_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    monkeypatch.setenv("COPNET_TOKEN", "dev-token")
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={},
    )
    _, token = orchestrator.register_app(app_id="subtext", display_name="Subtext")
    app = create_app(orchestrator, media_service=BrokenMediaService(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/media/import",
            headers=_auth(token),
            json={"url": "https://example.com/video"},
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "yt-dlp is not installed."


def test_media_routes_accept_gateway_token(media_app_client) -> None:
    client, _, media_service = media_app_client

    response = client.post(
        "/api/v1/media/import",
        headers=_auth("dev-token"),
        json={"url": "https://example.com/clip"},
    )
    assert response.status_code == 200
    assert response.json()["asset"]["assetId"] == "media-2"
    assert media_service.last_import is not None
    assert media_service.last_import["app_id"] == "copenet-web"


def test_media_download_returns_attachment_without_persisting_asset(media_app_client) -> None:
    client, token, media_service = media_app_client

    response = client.post(
        "/api/v1/media/download",
        headers=_auth(token),
        json={"url": "https://example.com/funny-video"},
    )

    assert response.status_code == 200
    assert response.content == b"fake-video"
    assert response.headers["content-type"] == "video/mp4"
    assert 'attachment; filename="funny-clip.mp4"' in response.headers["content-disposition"]
    assert media_service.last_download == {"url": "https://example.com/funny-video"}
    assert [asset.asset_id for asset in media_service.assets] == ["media-1"]


def test_media_download_accepts_gateway_token(media_app_client) -> None:
    client, _, media_service = media_app_client

    response = client.post(
        "/api/v1/media/download",
        headers=_auth("dev-token"),
        json={"url": "https://example.com/clip"},
    )

    assert response.status_code == 200
    assert response.content == b"fake-video"
    assert media_service.last_download == {"url": "https://example.com/clip"}
