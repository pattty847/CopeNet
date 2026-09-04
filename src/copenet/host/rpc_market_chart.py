"""Authenticated chart RPC boundary shared with model drawing actions."""
from __future__ import annotations

import asyncio
from dataclasses import replace

from copenet.core.market.chart_workspace import get_chart_store
from copenet.core.market.chart_workspace.requests import (
    CaptureRequest, DocumentRequest, WorkspaceRequest, WorkspaceUpdate, ObservationReadRequest,
)
from .rpc_schema import ResponseFrame, make_response_frame


async def _reply(request_id, send_json, payload):
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


def _session(orchestrator, session_key, *, allow_archived=False):
    session = orchestrator._session_store.get(session_key)
    if session is None:
        raise ValueError("Select an existing session before capturing chart context")
    if session.archived and not allow_archived:
        raise ValueError("Restore the archived session before using chart context")


async def handle_chart_workspace_get(request_id, params, send_json, orchestrator, *, broadcast=None):
    request = WorkspaceRequest.model_validate(params or {})
    payload = await asyncio.to_thread(get_chart_store(orchestrator).workspace,
                                      request.workspaceId, request.instrument)
    await _reply(request_id, send_json, payload)


async def handle_chart_workspace_update(request_id, params, send_json, orchestrator, *, broadcast=None):
    request = WorkspaceUpdate.model_validate(params or {})
    if request.sessionKey:
        _session(orchestrator, request.sessionKey)
    payload = await asyncio.to_thread(get_chart_store(orchestrator).update_workspace, request.workspaceId, request.sessionKey)
    await _reply(request_id, send_json, payload)


async def handle_chart_capture(request_id, params, send_json, orchestrator, *, broadcast=None):
    request = CaptureRequest.model_validate(params or {})
    _session(orchestrator, request.sessionKey)
    payload = await asyncio.to_thread(get_chart_store(orchestrator).capture, request.sessionKey,
                                      request.captureId, request.capture)
    await _reply(request_id, send_json, payload)


async def handle_chart_read(request_id, params, send_json, orchestrator, *, broadcast=None):
    request = ObservationReadRequest.model_validate(params or {})
    store = get_chart_store(orchestrator)
    if request.documentId:
        observation = await asyncio.to_thread(store.document_evidence_observation, request.documentId, request.observationId, request.resourceKey)
        session_key = observation["sessionKey"]
    else:
        session_key = request.sessionKey
        _session(orchestrator, session_key, allow_archived=True)
        observation = await asyncio.to_thread(store.observation, request.observationId, session_key)
    context = store.resolve_context(session_key, "operator-read", {
        "observationId": request.observationId, "documentId": observation["documentId"],
        "viewId": observation["viewId"], "detail": request.detail, "access": "read",
    })
    if not request.includeAccountContext:
        allowed_keys = tuple(resource["key"] for resource in observation["resources"] if not resource["metadata"].get("accountContext"))
        context = replace(context, include_account_context=False, resource_keys=allowed_keys)
    payload = await asyncio.to_thread(store.read_resource, context, request.resourceKey, request.offset,
                                      request.limit, request.from_, request.to, None, request.fields, request.metadataPath)
    await _reply(request_id, send_json, payload)


async def handle_chart_document_get(request_id, params, send_json, orchestrator, *, broadcast=None):
    request = DocumentRequest.model_validate(params or {})
    payload = await asyncio.to_thread(get_chart_store(orchestrator).document, request.documentId)
    await _reply(request_id, send_json, payload)


async def _mutation(request_id, params, send_json, orchestrator, operation, broadcast=None):
    payload = await asyncio.to_thread(operation, params or {})
    await _reply(request_id, send_json, payload)
    await (broadcast or send_json)({"type": "event", "event": "market.chart.document", "payload": {
        "documentId": payload["documentId"], "revision": payload["revision"],
    }})


async def handle_chart_apply(request_id, params, send_json, orchestrator, *, broadcast=None):
    await _mutation(request_id, params, send_json, orchestrator, get_chart_store(orchestrator).apply, broadcast)


async def handle_chart_undo(request_id, params, send_json, orchestrator, *, broadcast=None):
    await _mutation(request_id, params, send_json, orchestrator, get_chart_store(orchestrator).undo, broadcast)


async def handle_chart_rendered(request_id, params, send_json, orchestrator, *, broadcast=None):
    payload = await asyncio.to_thread(get_chart_store(orchestrator).rendered, params or {})
    await _reply(request_id, send_json, payload)


MARKET_CHART_HANDLERS = {
    "market.chart.workspace.get": handle_chart_workspace_get,
    "market.chart.workspace.update": handle_chart_workspace_update,
    "market.chart.capture": handle_chart_capture,
    "market.chart.read": handle_chart_read,
    "market.chart.document.get": handle_chart_document_get,
    "market.chart.apply": handle_chart_apply,
    "market.chart.undo": handle_chart_undo,
    "market.chart.rendered": handle_chart_rendered,
}
