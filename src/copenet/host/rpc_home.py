"""Home RPC handlers: the desk snapshot and the operator's focus list."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import ResponseFrame, RpcError, make_response_frame

SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def _respond(request_id: str, send_json: SendJson, payload: dict) -> None:
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


async def handle_home_snapshot(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    limit = max(1, min(int(raw.get("activityLimit") or 8), 40))
    await _respond(request_id, send_json, {"snapshot": orchestrator.desk_snapshot(activity_limit=limit)})


async def handle_focus_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    await _respond(request_id, send_json, {"focus": orchestrator.get_focus()})


async def handle_focus_update(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """One method for every mutation, keyed by `op`.

    The focus list is a single small document, and every operation rewrites it and returns
    the whole thing — so seven RPC names would be seven ways to say "here is the new
    document". The op is validated exhaustively; an unknown one is an error, not a no-op.
    """
    raw = params or {}
    op = str(raw.get("op") or "").strip()
    item_id = str(raw.get("itemId") or "").strip()

    try:
        if op == "add":
            focus = orchestrator.add_focus_item(str(raw.get("text") or ""))
        elif op == "toggle":
            focus = orchestrator.set_focus_item(item_id, done=bool(raw.get("done")))
        elif op == "rename":
            focus = orchestrator.set_focus_item(item_id, text=str(raw.get("text") or ""))
        elif op == "remove":
            focus = orchestrator.remove_focus_item(item_id)
        elif op == "clearDone":
            focus = orchestrator.clear_done_focus_items()
        elif op == "notes":
            focus = orchestrator.set_focus_notes(str(raw.get("notes") or ""))
        elif op == "quickLaunch":
            tiles = raw.get("tiles")
            focus = orchestrator.set_quick_launch([str(tile) for tile in tiles] if isinstance(tiles, list) else [])
        else:
            raise RpcError(f"unknown focus op: {op or '(missing)'}")
    except KeyError:
        raise RpcError(f"no focus item with id {item_id!r}") from None
    except ValueError as cause:
        raise RpcError(str(cause)) from None

    await _respond(request_id, send_json, {"focus": focus})
