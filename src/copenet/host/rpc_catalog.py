"""Compatibility re-exports for catalog-style RPC handlers."""

from __future__ import annotations

from .rpc_catalog_core import (
    handle_prompts_list,
    handle_prompts_optimize,
    handle_providers_list,
    handle_models_list,
    handle_tools_list,
)
from .rpc_briefing import (
    handle_briefing_get,
)
from .rpc_persona import (
    handle_persona_get,
    handle_persona_settings_get,
    handle_persona_settings_update,
    handle_persona_context_get,
    handle_persona_list,
    handle_persona_create,
    handle_persona_select,
    handle_persona_read_file,
    handle_persona_write_file,
    handle_persona_flavor_draft,
    handle_persona_flavor_save,
)
from .rpc_memory import (
    handle_memory_list,
    handle_memory_upsert,
    handle_memory_archive,
    handle_memory_approve,
    handle_memory_discard,
)
from .rpc_user_notes import (
    handle_user_notes_list,
    handle_user_notes_approve,
    handle_user_notes_discard,
)
from .rpc_runtime import (
    handle_runtime_context_get,
    handle_runtime_context_resolve,
    handle_runtime_workspace_browse,
    handle_runtime_workspace_set,
)
from .rpc_provider_auth import (
    handle_provider_auth_status,
    handle_provider_auth_begin_login,
    handle_provider_auth_complete_login,
    handle_provider_auth_logout,
)
from .rpc_messaging import (
    handle_messaging_config_get,
    handle_messaging_config_update,
    handle_messaging_test,
    handle_messaging_destinations_list,
    handle_messaging_destinations_upsert,
    handle_messaging_destinations_delete,
    handle_messaging_routes_list,
    handle_messaging_routes_upsert,
    handle_messaging_routes_delete,
    handle_messaging_routes_resolve,
)
from .rpc_market import (
    handle_market_dashboard_get,
    handle_market_interpret,
    handle_market_read_get,
    handle_market_refresh,
    handle_market_ticker_get,
    handle_market_universe_get,
)


__all__ = [
    "handle_prompts_list",
    "handle_prompts_optimize",
    "handle_providers_list",
    "handle_models_list",
    "handle_tools_list",
    "handle_briefing_get",
    "handle_persona_get",
    "handle_persona_settings_get",
    "handle_persona_settings_update",
    "handle_persona_context_get",
    "handle_persona_list",
    "handle_persona_create",
    "handle_persona_select",
    "handle_persona_read_file",
    "handle_persona_write_file",
    "handle_persona_flavor_draft",
    "handle_persona_flavor_save",
    "handle_memory_list",
    "handle_memory_upsert",
    "handle_memory_archive",
    "handle_memory_approve",
    "handle_memory_discard",
    "handle_user_notes_list",
    "handle_user_notes_approve",
    "handle_user_notes_discard",
    "handle_runtime_context_get",
    "handle_runtime_context_resolve",
    "handle_runtime_workspace_browse",
    "handle_runtime_workspace_set",
    "handle_provider_auth_status",
    "handle_provider_auth_begin_login",
    "handle_provider_auth_complete_login",
    "handle_provider_auth_logout",
    "handle_messaging_config_get",
    "handle_messaging_config_update",
    "handle_messaging_test",
    "handle_messaging_destinations_list",
    "handle_messaging_destinations_upsert",
    "handle_messaging_destinations_delete",
    "handle_messaging_routes_list",
    "handle_messaging_routes_upsert",
    "handle_messaging_routes_delete",
    "handle_messaging_routes_resolve",
    "handle_market_dashboard_get",
    "handle_market_ticker_get",
    "handle_market_universe_get",
    "handle_market_refresh",
    "handle_market_interpret",
    "handle_market_read_get",
]
