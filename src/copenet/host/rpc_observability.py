"""Observability settings and run-inspection RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.core.orchestrator.facade_observability import DEFAULT_USAGE_DAYS
from copenet.host.rpc_schema import ResponseFrame, RpcError, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_observability_settings_get(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(id=request_id, ok=True, payload={"settings": orchestrator.get_observability_settings()})
        )
    )


async def handle_observability_settings_update(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    debug_capture = raw.get("debugCapture")
    if not isinstance(debug_capture, bool):
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="debugCapture must be a boolean"),
                )
            )
        )
        return
    settings = orchestrator.update_observability_settings(debug_capture=debug_capture)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"settings": settings})))


async def handle_observability_traces_purge(request_id: str, send_json: SendJson, orchestrator) -> None:
    """Delete every stored run trace. Run records and transcripts are untouched."""
    await send_json(
        make_response_frame(
            ResponseFrame(id=request_id, ok=True, payload={"settings": orchestrator.purge_observability_traces()})
        )
    )


async def handle_observability_usage_get(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    """Return the token/tool usage rollup over the requested window of days."""
    raw = params or {}
    days = raw.get("days")
    include_bench = raw.get("includeBench")
    if days is not None and not isinstance(days, int):
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="days must be an integer"),
                )
            )
        )
        return
    rollup = orchestrator.get_usage_rollup(
        days=days if days is not None else DEFAULT_USAGE_DAYS,
        include_bench=bool(include_bench),
    )
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"usage": rollup})))


async def handle_observability_run_get(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    session_key = str(raw.get("sessionKey") or "").strip()
    run_id = str(raw.get("runId") or "").strip()
    if not session_key or not run_id:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="sessionKey and runId are required"),
                )
            )
        )
        return
    detail = orchestrator.resolve_observability_run(session_key, run_id)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"detail": detail})))
