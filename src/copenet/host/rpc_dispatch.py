"""RPC dispatch table for the CopeNet websocket host."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import ResponseFrame, RpcError, make_response_frame

from .rpc_catalog import (
    handle_briefing_get,
    handle_identity_context_get,
    handle_memory_archive,
    handle_memory_list,
    handle_memory_upsert,
    handle_messaging_config_get,
    handle_messaging_config_update,
    handle_messaging_destinations_delete,
    handle_messaging_destinations_list,
    handle_messaging_destinations_upsert,
    handle_messaging_routes_delete,
    handle_messaging_routes_list,
    handle_messaging_routes_resolve,
    handle_messaging_routes_upsert,
    handle_messaging_test,
    handle_models_list,
    handle_persona_context_get,
    handle_persona_flavor_draft,
    handle_persona_flavor_save,
    handle_persona_create,
    handle_persona_get,
    handle_persona_list,
    handle_persona_read_file,
    handle_persona_select,
    handle_persona_settings_get,
    handle_persona_settings_update,
    handle_persona_write_file,
    handle_profile_changelog,
    handle_profile_get,
    handle_prompts_list,
    handle_prompts_optimize,
    handle_provider_auth_begin_login,
    handle_provider_auth_complete_login,
    handle_provider_auth_logout,
    handle_provider_auth_status,
    handle_providers_list,
    handle_runtime_context_get,
    handle_runtime_context_resolve,
    handle_runtime_workspace_browse,
    handle_runtime_workspace_set,
    handle_tools_list,
)
from .rpc_chat import handle_chat_abort, handle_chat_history, handle_chat_send
from .rpc_nasa import handle_nasa_apod, handle_nasa_apod_list
from .rpc_permissions import (
    handle_permissions_allowlist_add,
    handle_permissions_allowlist_list,
    handle_permissions_allowlist_remove,
)
from .rpc_sessions import (
    handle_approvals_list,
    handle_pulse_create_from_session,
    handle_pulse_dismiss,
    handle_pulse_list,
    handle_pulse_save,
    handle_sessions_archive,
    handle_sessions_artifacts,
    handle_sessions_create,
    handle_sessions_debug_copy,
    handle_sessions_export,
    handle_sessions_list,
    handle_sessions_merge_create,
    handle_sessions_merge_state,
    handle_chat_decide_approval,
    handle_sessions_rename,
    handle_sessions_revert_edit,
    handle_sessions_run,
    handle_sessions_runs,
    handle_sessions_resolve,
    handle_sessions_state,
)
from copenet.host.rpc_workspace import (
    handle_workspace_list_files,
    handle_workspace_read_file,
    handle_workspace_write_file,
)


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def dispatch_rpc(req, send_json: SendJson, orchestrator, tasks: set, broadcast: SendJson | None = None) -> None:
    """Route one already-authenticated RPC request.

    Wrapped in a generic exception boundary so a malformed param (e.g. int("lol"))
    inside a handler returns an INVALID_REQUEST response instead of bubbling out
    and killing the WebSocket. Per Codex peer review round 2.

    `broadcast` (when provided) fans an event payload out to every connected
    client; chat streaming uses it so a reconnected socket or second device
    receives live frames. Falls back to the per-connection `send_json`.
    """
    try:
        await _route_rpc(req, send_json, orchestrator, tasks, broadcast or send_json)
    except ValueError as exc:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=req.id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message=str(exc) or "invalid request"),
                )
            )
        )
    except Exception as exc:  # noqa: BLE001 — last-resort socket-saver
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=req.id,
                    ok=False,
                    error=RpcError(
                        code="INTERNAL_ERROR",
                        message=f"{exc.__class__.__name__}: {exc}",
                    ),
                )
            )
        )


async def _route_rpc(req, send_json: SendJson, orchestrator, tasks: set, broadcast: SendJson) -> None:
    """Inner dispatch — original method table. Errors bubble to dispatch_rpc."""
    if req.method == "chat.send":
        await handle_chat_send(req.id, req.params, send_json, tasks, orchestrator, broadcast=broadcast)
    elif req.method == "chat.abort":
        await handle_chat_abort(req.id, req.params, send_json, orchestrator)
    elif req.method == "chat.history":
        await handle_chat_history(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.list":
        await handle_sessions_list(req.id, req.params, send_json, orchestrator)
    elif req.method == "prompts.list":
        await handle_prompts_list(req.id, send_json)
    elif req.method == "prompts.optimize":
        await handle_prompts_optimize(req.id, req.params, send_json, orchestrator)
    elif req.method == "providers.list":
        await handle_providers_list(req.id, send_json, orchestrator)
    elif req.method == "models.list":
        await handle_models_list(req.id, req.params, send_json, orchestrator)
    elif req.method == "tools.list":
        await handle_tools_list(req.id, send_json, orchestrator)
    elif req.method == "profile.get":
        await handle_profile_get(req.id, send_json, orchestrator)
    elif req.method == "identity.context":
        await handle_identity_context_get(req.id, send_json, orchestrator)
    elif req.method == "persona.get":
        await handle_persona_get(req.id, req.params, send_json, orchestrator)
    elif req.method == "persona.settings.get":
        await handle_persona_settings_get(req.id, send_json, orchestrator)
    elif req.method == "persona.settings.update":
        await handle_persona_settings_update(req.id, req.params, send_json, orchestrator)
    elif req.method == "persona.context":
        await handle_persona_context_get(req.id, req.params, send_json, orchestrator)
    elif req.method == "persona.flavor.draft":
        await handle_persona_flavor_draft(req.id, req.params, send_json, orchestrator)
    elif req.method == "persona.flavor.save":
        await handle_persona_flavor_save(req.id, req.params, send_json, orchestrator)
    elif req.method == "persona.list":
        await handle_persona_list(req.id, req.params, send_json, orchestrator)
    elif req.method == "persona.create":
        await handle_persona_create(req.id, req.params, send_json, orchestrator)
    elif req.method == "persona.select":
        await handle_persona_select(req.id, req.params, send_json, orchestrator)
    elif req.method == "persona.readFile":
        await handle_persona_read_file(req.id, req.params, send_json, orchestrator)
    elif req.method == "persona.writeFile":
        await handle_persona_write_file(req.id, req.params, send_json, orchestrator)
    elif req.method == "profile.changelog":
        await handle_profile_changelog(req.id, req.params, send_json, orchestrator)
    elif req.method == "briefing.get":
        await handle_briefing_get(req.id, send_json, orchestrator)
    elif req.method == "memory.list":
        await handle_memory_list(req.id, req.params, send_json, orchestrator)
    elif req.method == "memory.upsert":
        await handle_memory_upsert(req.id, req.params, send_json, orchestrator)
    elif req.method == "memory.archive":
        await handle_memory_archive(req.id, req.params, send_json, orchestrator)
    elif req.method == "runtime.context":
        if req.params:
            await handle_runtime_context_resolve(req.id, req.params, send_json, orchestrator)
        else:
            await handle_runtime_context_get(req.id, send_json, orchestrator)
    elif req.method == "runtime.workspace.browse":
        await handle_runtime_workspace_browse(req.id, send_json, orchestrator)
    elif req.method == "runtime.workspace.set":
        await handle_runtime_workspace_set(req.id, req.params, send_json, orchestrator)
    elif req.method == "providerAuth.status":
        await handle_provider_auth_status(req.id, req.params, send_json, orchestrator)
    elif req.method == "providerAuth.beginLogin":
        await handle_provider_auth_begin_login(req.id, req.params, send_json, orchestrator)
    elif req.method == "providerAuth.completeLogin":
        await handle_provider_auth_complete_login(req.id, req.params, send_json, orchestrator)
    elif req.method == "providerAuth.logout":
        await handle_provider_auth_logout(req.id, req.params, send_json, orchestrator)
    elif req.method == "messaging.config.get":
        await handle_messaging_config_get(req.id, send_json, orchestrator)
    elif req.method == "messaging.config.update":
        await handle_messaging_config_update(req.id, req.params, send_json, orchestrator)
    elif req.method == "messaging.test":
        await handle_messaging_test(req.id, req.params, send_json, orchestrator)
    elif req.method == "messaging.destinations.list":
        await handle_messaging_destinations_list(req.id, send_json, orchestrator)
    elif req.method == "messaging.destinations.upsert":
        await handle_messaging_destinations_upsert(req.id, req.params, send_json, orchestrator)
    elif req.method == "messaging.destinations.delete":
        await handle_messaging_destinations_delete(req.id, req.params, send_json, orchestrator)
    elif req.method == "messaging.routes.list":
        await handle_messaging_routes_list(req.id, send_json, orchestrator)
    elif req.method == "messaging.routes.upsert":
        await handle_messaging_routes_upsert(req.id, req.params, send_json, orchestrator)
    elif req.method == "messaging.routes.delete":
        await handle_messaging_routes_delete(req.id, req.params, send_json, orchestrator)
    elif req.method == "messaging.routes.resolve":
        await handle_messaging_routes_resolve(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.create":
        await handle_sessions_create(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.merge.create":
        await handle_sessions_merge_create(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.merge.state":
        await handle_sessions_merge_state(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.rename":
        await handle_sessions_rename(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.archive":
        await handle_sessions_archive(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.artifacts":
        await handle_sessions_artifacts(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.revertEdit":
        await handle_sessions_revert_edit(req.id, req.params, send_json, orchestrator)
    elif req.method == "workspace.listFiles":
        await handle_workspace_list_files(req.id, req.params, send_json, orchestrator)
    elif req.method == "workspace.readFile":
        await handle_workspace_read_file(req.id, req.params, send_json, orchestrator)
    elif req.method == "workspace.writeFile":
        await handle_workspace_write_file(req.id, req.params, send_json, orchestrator)
    elif req.method == "chat.decideApproval":
        await handle_chat_decide_approval(req.id, req.params, send_json, orchestrator)
    elif req.method == "approvals.list":
        await handle_approvals_list(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.debugCopy":
        await handle_sessions_debug_copy(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.export":
        await handle_sessions_export(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.runs":
        await handle_sessions_runs(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.run":
        await handle_sessions_run(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.state":
        await handle_sessions_state(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.resolve":
        await handle_sessions_resolve(req.id, req.params, send_json, orchestrator)
    elif req.method == "pulse.list":
        await handle_pulse_list(req.id, req.params, send_json, orchestrator)
    elif req.method == "pulse.create_from_session":
        await handle_pulse_create_from_session(req.id, req.params, send_json, orchestrator)
    elif req.method == "pulse.save":
        await handle_pulse_save(req.id, req.params, send_json, orchestrator)
    elif req.method == "pulse.dismiss":
        await handle_pulse_dismiss(req.id, req.params, send_json, orchestrator)
    elif req.method == "nasa.apod":
        await handle_nasa_apod(req.id, req.params, send_json, orchestrator)
    elif req.method == "nasa.apod.list":
        await handle_nasa_apod_list(req.id, req.params, send_json, orchestrator)
    elif req.method == "permissions.allowlist.list":
        await handle_permissions_allowlist_list(req.id, send_json, orchestrator)
    elif req.method == "permissions.allowlist.add":
        await handle_permissions_allowlist_add(req.id, req.params, send_json, orchestrator)
    elif req.method == "permissions.allowlist.remove":
        await handle_permissions_allowlist_remove(req.id, req.params, send_json, orchestrator)
    else:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=req.id,
                    ok=False,
                    error=RpcError(code="METHOD_NOT_FOUND", message=f"unknown method: {req.method}"),
                )
            )
        )
