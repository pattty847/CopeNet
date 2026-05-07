"""RPC dispatch table for the CopeNet websocket host."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import ResponseFrame, RpcError, make_response_frame

from .rpc_catalog import (
    handle_briefing_get,
    handle_messaging_config_get,
    handle_messaging_config_update,
    handle_messaging_test,
    handle_models_list,
    handle_profile_changelog,
    handle_profile_get,
    handle_prompts_list,
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
from .rpc_sessions import (
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
    handle_sessions_rename,
    handle_sessions_run,
    handle_sessions_runs,
    handle_sessions_resolve,
    handle_sessions_state,
)


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def dispatch_rpc(req, send_json: SendJson, orchestrator, tasks: set) -> None:
    """Route one already-authenticated RPC request."""
    if req.method == "chat.send":
        await handle_chat_send(req.id, req.params, send_json, tasks, orchestrator)
    elif req.method == "chat.abort":
        await handle_chat_abort(req.id, req.params, send_json, orchestrator)
    elif req.method == "chat.history":
        await handle_chat_history(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.list":
        await handle_sessions_list(req.id, req.params, send_json, orchestrator)
    elif req.method == "prompts.list":
        await handle_prompts_list(req.id, send_json)
    elif req.method == "providers.list":
        await handle_providers_list(req.id, send_json, orchestrator)
    elif req.method == "models.list":
        await handle_models_list(req.id, req.params, send_json, orchestrator)
    elif req.method == "tools.list":
        await handle_tools_list(req.id, send_json, orchestrator)
    elif req.method == "profile.get":
        await handle_profile_get(req.id, send_json, orchestrator)
    elif req.method == "profile.changelog":
        await handle_profile_changelog(req.id, req.params, send_json, orchestrator)
    elif req.method == "briefing.get":
        await handle_briefing_get(req.id, send_json, orchestrator)
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
