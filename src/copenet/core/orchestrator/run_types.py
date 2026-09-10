"""Typed results for admission, prepared input, and accumulated provider events."""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from copenet.core.harness.planning import HarnessTurnPlan
from copenet.core.market.chart_workspace.models import MarketTurnContext
from copenet.core.sessions import SessionIndexEntry, SessionStateRecord
from copenet.core.tools import ToolDescriptor
from copenet.core.tools.policy import ToolPolicy
from copenet.core.tracing import RunTraceWriter
from copenet.prompts import PromptContextPolicy
from .context_budget import ContextBudget
from .requests import ChatSendRequest


@dataclass
class RunAdmission:
    request: ChatSendRequest
    session_key: str
    message: str
    run_id: str
    provider_name: str
    entry: SessionIndexEntry
    session_workspace_root: Path
    abort_event: asyncio.Event
    trace: RunTraceWriter
    market_context: MarketTurnContext | None
    market_reference: dict | None
    market_metadata: dict
    dedupe_key: str | None
    run_started_at: str
    is_first_turn: bool
    attachment_refs: list[dict]
    current_image_parts: list[dict]


@dataclass
class RunInput:
    available_tools: list[ToolDescriptor]
    effective_tool_policy: ToolPolicy
    scoped_tool_ids: frozenset[str] | None
    requested_tool_ids: tuple[str, ...]
    active_requested_tool_ids: tuple[str, ...]
    rejected_requested_tool_ids: tuple[str, ...]
    session_state: SessionStateRecord
    effective_system_prompt: str | None
    resolved_system_prompt_id: str | None
    resolved_task_prompt_id: str | None
    prompt_policy: PromptContextPolicy
    context_budget: ContextBudget
    history_for_replay: list[dict]
    chat_messages: list[dict]
    chat_prompt: str
    message_count: int
    input_token_estimate: int
    preplan_input_token_estimate: int
    unbounded_token_estimate: int
    initial_input_budget: int
    loop_reserve_tokens: int
    agent_runtime_payload: dict
    identity_context_payload: dict


@dataclass
class RunEvents:
    seq: int = 0
    resolved_model: str | None = None
    assistant_parts: list[str] = field(default_factory=list)
    assistant_message_parts: list[dict] = field(default_factory=list)
    tool_execution_payload: dict | None = None
    latest_turn_state: dict = field(default_factory=dict)
    normalized_tool_results: list[dict] = field(default_factory=list)
    artifact_drafts: list[dict] = field(default_factory=list)
    tool_steps: list[dict] = field(default_factory=list)
    persisted_tool_artifact_ids: list[str] = field(default_factory=list)
    chart_manifest_id: str | None = None
    plan: HarnessTurnPlan | None = None
    transcript_persisted: bool = False
    terminal_persisted: bool = False
    created_artifact_ids: list[str] = field(default_factory=list)
