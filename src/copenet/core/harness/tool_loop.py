"""Compatibility facade for CopeNet harness tool loops."""

from __future__ import annotations

from .tool_loop_common import (
    DEFAULT_RESPONSES_REASONING,
    MAX_TOOL_STEPS,
    ToolExecutor,
    TraceRecorder,
    _coerce_native_message_content,
    _coerce_prompted_tool_request,
    _compose_prompted_tool_followup,
    _extract_native_choice,
    _extract_native_tool_calls,
    _force_call_id,
    _max_step_explanation,
    _native_tool_message_content,
    _new_call_id,
    _parse_native_tool_arguments,
    _tool_call_event_payload,
    _tool_result_event_payload,
    collect_provider_turn,
    compose_native_tool_system_prompt,
    compose_prompted_tool_correction,
    compose_prompted_tool_system_prompt,
    compose_provider_prompt,
    compose_responses_tool_instructions,
    compose_system_prompt,
    parse_prompted_tool_turn,
    provider_system_prompt,
)
from .tool_loop_native import NativeToolProvider, run_with_native_tools
from .tool_loop_prompted import run_with_prompted_tools
from .tool_loop_responses import ResponsesProvider, run_with_responses_tools
from .tool_result_materialization import (
    LARGE_TOOL_RESULT_CHAR_LIMIT,
    _materialize_tool_result_artifact,
    model_facing_result_char_limit,
)


__all__ = [
    "DEFAULT_RESPONSES_REASONING",
    "LARGE_TOOL_RESULT_CHAR_LIMIT",
    "MAX_TOOL_STEPS",
    "NativeToolProvider",
    "ResponsesProvider",
    "ToolExecutor",
    "TraceRecorder",
    "_coerce_native_message_content",
    "_coerce_prompted_tool_request",
    "_compose_prompted_tool_followup",
    "_extract_native_choice",
    "_extract_native_tool_calls",
    "_force_call_id",
    "_materialize_tool_result_artifact",
    "_max_step_explanation",
    "_native_tool_message_content",
    "_new_call_id",
    "_parse_native_tool_arguments",
    "_tool_call_event_payload",
    "_tool_result_event_payload",
    "collect_provider_turn",
    "compose_native_tool_system_prompt",
    "compose_prompted_tool_correction",
    "compose_prompted_tool_system_prompt",
    "compose_provider_prompt",
    "compose_responses_tool_instructions",
    "compose_system_prompt",
    "model_facing_result_char_limit",
    "parse_prompted_tool_turn",
    "provider_system_prompt",
    "run_with_native_tools",
    "run_with_prompted_tools",
    "run_with_responses_tools",
]
