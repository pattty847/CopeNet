"""Resolve the current turn's registered tools and effective Access policy."""

from .run_types import RunAdmission, ToolSelection
from copenet.core.market.chart_workspace.authorization import chart_tool_ids
from .market_context import chart_policy
from .tool_requests import normalize_requested_tool_ids
from copenet.core.tools import policy_for_task_mode, disclose_policy_in_descriptions


def select_run_tools(orchestrator, admission: RunAdmission) -> ToolSelection:
    registered_tools = orchestrator._tool_registry.list_tools()
    requested_tool_ids = normalize_requested_tool_ids(
        admission.request.requested_tool_ids, registered_tool_ids=(tool.id for tool in registered_tools)
    )
    effective_tool_policy = policy_for_task_mode(
        admission.entry.task_prompt_id or admission.request.task_prompt_id, provider=admission.provider_name
    )
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
    )
