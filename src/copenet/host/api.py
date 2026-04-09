"""FastAPI app for the CopeNet gateway."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from copenet.host.ws_server import CopeNetWsServer

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="CopeNet Gateway", version="0.1.0")
    ws_server = CopeNetWsServer()

    # TODO: Add deeper health probes for providers, orchestrator, etc.
    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.websocket("/ws")
    async def websocket_rpc(websocket: WebSocket) -> None:
        await ws_server.handle(websocket)

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(_STATIC_DIR / "index.html")

    return app
