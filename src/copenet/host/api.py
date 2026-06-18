"""FastAPI app for the CopeNet gateway."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from copenet.core.media import MediaIngestionService
from copenet.core.orchestrator import Orchestrator
from copenet.core.web_ingest import WebIngestionService
from copenet.host.agents_api import create_agents_router
from copenet.host.app_api import create_app_router
from copenet.host.ws_server import CopeNetWsServer

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"


def _root_index_path() -> Path:
    dist_index = _FRONTEND_DIST_DIR / "index.html"
    return dist_index if dist_index.is_file() else (_STATIC_DIR / "index.html")

def create_app(
    orchestrator: Orchestrator | None = None,
    media_service: MediaIngestionService | None = None,
    web_ingestion_service: WebIngestionService | None = None,
) -> FastAPI:
    app = FastAPI(title="CopeNet Gateway", version="0.1.0")
    ws_server = CopeNetWsServer(orchestrator=orchestrator)

    # TODO: Add deeper health probes for providers, orchestrator, etc.
    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.websocket("/ws")
    async def websocket_rpc(websocket: WebSocket) -> None:
        await ws_server.handle(websocket)

    app.include_router(
        create_app_router(
            ws_server.orchestrator,
            media_service=media_service,
            web_ingestion_service=web_ingestion_service,
        )
    )
    app.include_router(create_agents_router())

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    if (_FRONTEND_DIST_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST_DIR / "assets"), name="assets")
    if (_FRONTEND_DIST_DIR / "imgs").is_dir():
        app.mount("/imgs", StaticFiles(directory=_FRONTEND_DIST_DIR / "imgs"), name="imgs")

    @app.get("/nasa/apod/image/{date}")
    def nasa_apod_image(date: str) -> FileResponse:
        # Serve the locally cached APOD image (lazily caching on first request) so the
        # Home card doesn't break when apod.nasa.gov is flaky.
        path = ws_server.orchestrator.nasa_image_path(date)
        if path is None:
            raise HTTPException(status_code=404, detail="APOD image not available")
        return FileResponse(path)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_root_index_path())

    return app
