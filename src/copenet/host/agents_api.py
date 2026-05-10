"""Agent orchestration utility routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter


def create_agents_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

    @router.get("/ping")
    def agents_ping() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "agents",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return router
