"""FastAPI app for the CopeNet gateway."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from copenet.core.market.sentinel import MarketSentinel, sentinel_enabled
from copenet.core.media import MediaIngestionService
from copenet.core.orchestrator import Orchestrator
from copenet.core.web_ingest import WebIngestionService
from copenet.host.agents_api import create_agents_router
from copenet.host.app_api import create_app_router
from copenet.host.ws_server import CopeNetWsServer

_FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"
_FRONTEND_SECTION_PATHS = {
    "agents",
    "market",
    "workflows",
    "data-tools",
    "observability",
    "experiments",
}


def create_app(
    orchestrator: Orchestrator | None = None,
    media_service: MediaIngestionService | None = None,
    web_ingestion_service: WebIngestionService | None = None,
) -> FastAPI:
    ws_server = CopeNetWsServer(orchestrator=orchestrator)
    sentinel = MarketSentinel(ws_server.orchestrator)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Overnight market sentinel: pre-market sweep + morning brief. Disabled via
        # COPNET_MARKET_SENTINEL=0. Its startup catch-up delay keeps short-lived test
        # apps from ever triggering a real sweep.
        if sentinel_enabled():
            sentinel.start()
        yield
        sentinel.stop()

    app = FastAPI(title="CopeNet Gateway", version="0.1.0", lifespan=lifespan)

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

    def frontend_index() -> FileResponse:
        path = _FRONTEND_DIST_DIR / "index.html"
        if not path.is_file():
            raise HTTPException(
                status_code=503,
                detail=(
                    "React frontend build not found. Run "
                    "`cd src/copenet/host/frontend && npm ci && npm run build`."
                ),
            )
        return FileResponse(path)

    @app.get("/")
    def index() -> FileResponse:
        return frontend_index()

    # PWA root assets: iOS/Android fetch these from the site root, not /assets.
    # Without explicit routes they'd 404 and "Add to Home Screen" would break.
    _PWA_ROOT_ASSETS = {
        "manifest.webmanifest",
        "apple-touch-icon.png",
        "icon.svg",
        "icon-192.png",
        "icon-512.png",
        "icon-maskable-512.png",
        "favicon.ico",
        "favicon-32.png",
        "favicon-16.png",
    }

    @app.get("/{asset_name}")
    def pwa_root_asset(asset_name: str) -> FileResponse:
        if asset_name in _FRONTEND_SECTION_PATHS:
            return frontend_index()
        if asset_name not in _PWA_ROOT_ASSETS:
            raise HTTPException(status_code=404, detail="Not found")
        path = _FRONTEND_DIST_DIR / asset_name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(path)

    @app.get("/{section}/{client_path:path}")
    def frontend_nested_route(section: str, client_path: str) -> FileResponse:
        if section not in _FRONTEND_SECTION_PATHS or not client_path:
            raise HTTPException(status_code=404, detail="Not found")
        return frontend_index()

    return app
