"""Resolve the current turn's registered tools and effective Access policy."""

from .run_types import RunAdmission, ToolSelection
from copenet.core.market.chart_workspace.authorization import chart_tool_ids
from .market_context import chart_policy
from .tool_requests import normalize_requested_tool_ids
from copenet.core.tools import policy_for_task_mode, disclose_policy_in_descriptions
from copenet.core.tools.disclosure import split_by_disclosure


def select_run_tools(orchestrator, admission: RunAdmission, *, session_loaded_tool_ids: tuple[str, ...] = ()) -> ToolSelection:
    registered_tools = orchestrator._tool_registry.list_tools()
    requested_tool_ids = normalize_requested_tool_ids(
        admission.request.requested_tool_ids, registered_tool_ids=(tool.id for tool in registered_tools)
    )
    effective_tool_policy = policy_for_task_mode(admission.entry.task_prompt_id or admission.request.task_prompt_id)
    effective_tool_policy = chart_policy(effective_tool_policy, admission.market_context)
    scoped_tool_ids = (
        chart_tool_ids(admission.market_context) if admission.market_context is not None else None
    )
    available_tools = (
        disclose_policy_in_descriptions(
            [
                tool
                for tool in registered_tools
                if tool.category in effective_tool_policy.allowed_categories
                and (
                    tool.id in scoped_tool_ids
                    if scoped_tool_ids is not None
                    else not tool.id.startswith(("market.chart.", "market.forecast."))
                )
            ],
            effective_tool_policy,
        )
        if admission.request.allow_tools
        else []
    )
    # Deferred disclosure for ordinary sessions: the core set, anything the operator
    # attached, and anything this session already loaded are offered outright; the
    # rest waits behind the catalog. The chart lane keeps its own scoped set.
    deferred_tools: list = []
    if scoped_tool_ids is None and available_tools:
        available_tools, deferred_tools = split_by_disclosure(
            available_tools, loaded_tool_ids=(*requested_tool_ids, *session_loaded_tool_ids)
        )
    available_tool_ids = {tool.id for tool in available_tools}
    active_requested_tool_ids = tuple(
        (tool_id for tool_id in requested_tool_ids if tool_id in available_tool_ids)
    )
    rejected_requested_tool_ids = tuple(
        (tool_id for tool_id in requested_tool_ids if tool_id not in available_tool_ids)
    )
    return ToolSelection(
        available_tools=available_tools,
        effective_tool_policy=effective_tool_policy,
        scoped_tool_ids=scoped_tool_ids,
        requested_tool_ids=requested_tool_ids,
        active_requested_tool_ids=active_requested_tool_ids,
        rejected_requested_tool_ids=rejected_requested_tool_ids,
        deferred_tools=deferred_tools,
    )
