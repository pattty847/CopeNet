"""Settings RPC handlers."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from copenet.core.settings.integrations import integration_statuses
from copenet.host.rpc_schema import ResponseFrame, make_response_frame

SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_settings_integrations_get(request_id: str, send_json: SendJson, orchestrator) -> None:
    # find_spec touches the import system; keep it off the event loop.
    statuses = await asyncio.to_thread(integration_statuses)
    payload = {"integrations": [status.to_public_dict() for status in statuses]}
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))
