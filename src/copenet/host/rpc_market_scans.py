"""Transport boundary for persisted scan controls."""
from __future__ import annotations
import asyncio
import logging

from copenet.core.market.scans.service import resolve_scan_service
from copenet.host.rpc_schema import ResponseFrame, make_response_frame


async def _reply(request_id, send_json, payload):
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


def _id(params):
    value = (params or {}).get("id")
    if not isinstance(value, str) or not value:
        raise ValueError("Scan id is required")
    return value


async def handle_market_scans_get(request_id, params, send_json, orchestrator):
    await _reply(request_id, send_json, resolve_scan_service(orchestrator).state())


async def handle_market_scans_run_get(request_id, params, send_json, orchestrator):
    await _reply(request_id, send_json, {"run": resolve_scan_service(orchestrator).store.run(_id(params))})


async def handle_market_scans_save(request_id, params, send_json, orchestrator):
    service = resolve_scan_service(orchestrator)
    service.store.save((params or {}).get("scan"))
    await _reply(request_id, send_json, service.state())


async def handle_market_scans_archive(request_id, params, send_json, orchestrator):
    service = resolve_scan_service(orchestrator)
    service.store.archive(_id(params))
    await _reply(request_id, send_json, service.state())


async def handle_market_scans_preview(request_id, params, send_json, orchestrator):
    service = resolve_scan_service(orchestrator)
    raw = params or {}
    scan = raw.get("scan") if "scan" in raw else service.store.get(_id(raw))
    await _reply(request_id, send_json, service.preview(scan))


async def handle_market_scans_run(request_id, params, send_json, orchestrator):
    service = resolve_scan_service(orchestrator)
    identifier = _id(params)
    token = (params or {}).get("scopeToken")
    if not isinstance(token, str) or len(token) != 64:
        raise ValueError("Preview this scan's scope before running")
    plan = service.preview(service.store.get(identifier))
    if plan["issues"]:
        raise ValueError("; ".join(plan["issues"]))
    if service.tasks:
        raise ValueError("A scan is already running; wait for it to finish")
    task = asyncio.create_task(service.run(identifier, expected_scope_token=token), name=f"market-scan-{identifier}")
    service.tasks.add(task)

    def completed(finished):
        service.tasks.discard(finished)
        if not finished.cancelled() and finished.exception():
            logging.warning("Market scan did not start: %s", finished.exception())

    task.add_done_callback(completed)
    # Let execution acquire its cross-process lock and persist the running record.
    await asyncio.sleep(0)
    if task.done() and not task.cancelled() and task.exception():
        raise task.exception()
    await _reply(request_id, send_json, service.state())
