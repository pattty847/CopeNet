"""Multi-agent orchestration layer for CopeNet.

Routes a turn between provider "roles" — heavy lifting (Codex), thinking
(Claude), breadth (Gemini) — based on the model-declared turn route, and runs a
provider chain with fallback (e.g. Codex fails -> Claude succeeds).

This layer sits ABOVE the harness: it selects WHICH provider runs a turn and
falls back across providers, while ChatHarness.run_turn still owns HOW one turn
executes against a single provider. It is intentionally decoupled from the live
send_chat runtime via an injected `run_on_provider` callable, so it can be
unit-tested and wired in incrementally.

See docs/plans/MULTI_AGENT_ORCHESTRATOR.md.
"""

from __future__ import annotations

from .delegation import (
    SubAgentResult,
    SubAgentTask,
    build_subagent_prompt,
    delegate_subagent_task,
)
from .fallback_executor import (
    FallbackAttempt,
    FallbackOutcome,
    execute_with_fallback,
)
from .orchestrator_adapter import (
    MultiAgentOrchestrator,
    MultiAgentTurnResult,
)
from .provider_selector import (
    ProviderRole,
    ProviderRoleMap,
    ProviderSelection,
    select_provider_chain,
)

__all__ = [
    "FallbackAttempt",
    "FallbackOutcome",
    "execute_with_fallback",
    "MultiAgentOrchestrator",
    "MultiAgentTurnResult",
    "ProviderRole",
    "ProviderRoleMap",
    "ProviderSelection",
    "SubAgentResult",
    "SubAgentTask",
    "build_subagent_prompt",
    "delegate_subagent_task",
    "select_provider_chain",
]
