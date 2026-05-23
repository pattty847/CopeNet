"""Provider selection: turn route + roles -> an ordered provider chain.

Pure decision logic. Given the model-declared `route` (from the HarnessDecision
record) and the set of currently-available provider ids, produce an ordered
chain of providers to attempt (primary first, then fallbacks). No I/O, no
side effects beyond an optional trace callback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


TraceRecorder = Callable[[str, dict[str, Any] | None], None]

# Abstract orchestration roles, mapped to concrete provider ids by ProviderRoleMap.
ProviderRole = Literal["heavy_lifting", "thinking", "breadth"]

# The routes are the HarnessDecision `route` enum (core/harness/decision.py).
# Each maps to an ordered preference of roles. Unknown routes use _DEFAULT_ROLES.
_ROUTE_ROLE_PREFERENCE: dict[str, tuple[ProviderRole, ...]] = {
    # Fast turnarounds: breadth first (Gemini), then accuracy (Claude), then Codex.
    "direct_response": ("breadth", "thinking", "heavy_lifting"),
    # Clarifying questions: Claude is strong here; breadth as backup.
    "ask_clarifying_question": ("thinking", "breadth"),
    # Native tool calls: Codex first (best native tool calling), Claude fallback.
    "call_tool": ("heavy_lifting", "thinking"),
    # Multi-step agent work: chain Codex -> Claude (review) -> Gemini (alternatives).
    "multi_step_agent_loop": ("heavy_lifting", "thinking", "breadth"),
    # Artifact creation: Codex first, Claude fallback.
    "create_or_update_artifact": ("heavy_lifting", "thinking"),
    # Refusals/redirects: Claude.
    "refuse_or_redirect": ("thinking",),
}
_DEFAULT_ROLES: tuple[ProviderRole, ...] = ("heavy_lifting", "thinking", "breadth")


@dataclass(frozen=True)
class ProviderRoleMap:
    """Maps abstract orchestration roles to concrete CopeNet provider ids.

    Defaults reflect the spec: Codex for heavy lifting, Claude for thinking,
    Gemini for breadth. `breadth` defaults to "gemini", which is not in the
    default registry yet — selection filters it out gracefully when absent.
    """

    heavy_lifting: str = "openai-codex"
    thinking: str = "claude-cli"
    breadth: str = "gemini"

    def provider_for(self, role: ProviderRole) -> str:
        return getattr(self, role)

    def ordered_provider_ids(self, roles: tuple[ProviderRole, ...]) -> list[str]:
        """Resolve a role preference into provider ids, de-duplicated in order."""
        seen: set[str] = set()
        out: list[str] = []
        for role in roles:
            provider_id = self.provider_for(role)
            if provider_id and provider_id not in seen:
                seen.add(provider_id)
                out.append(provider_id)
        return out


@dataclass(frozen=True)
class ProviderSelection:
    """Result of selecting a provider chain for one turn."""

    route: str
    primary: str | None
    chain: tuple[str, ...]
    rationale: str
    requested_chain: tuple[str, ...] = field(default_factory=tuple)
    unavailable: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.primary is not None


def select_provider_chain(
    *,
    route: str | None,
    available_provider_ids: list[str] | set[str],
    role_map: ProviderRoleMap | None = None,
    capability_profile: Any | None = None,
    trace: TraceRecorder | None = None,
) -> ProviderSelection:
    """Pick an ordered provider chain (primary + fallbacks) for one turn.

    `route` is the HarnessDecision route. `available_provider_ids` is the set of
    providers that initialized successfully (e.g. orchestrator._providers keys).
    `capability_profile` is accepted for trace/rationale only — selection is
    route-driven; per-provider capabilities are enforced later by the harness.
    """
    role_map = role_map or ProviderRoleMap()
    available = set(available_provider_ids)
    normalized_route = (route or "").strip() or "unknown"
    roles = _ROUTE_ROLE_PREFERENCE.get(normalized_route, _DEFAULT_ROLES)
    requested = role_map.ordered_provider_ids(roles)
    chain = [pid for pid in requested if pid in available]
    unavailable = [pid for pid in requested if pid not in available]
    primary = chain[0] if chain else None

    rationale = _build_rationale(
        route=normalized_route,
        roles=roles,
        chain=chain,
        unavailable=unavailable,
    )
    selection = ProviderSelection(
        route=normalized_route,
        primary=primary,
        chain=tuple(chain),
        rationale=rationale,
        requested_chain=tuple(requested),
        unavailable=tuple(unavailable),
    )
    if trace is not None:
        trace(
            "multiagent_selection",
            {
                "route": normalized_route,
                "primary": primary,
                "chain": list(chain),
                "requestedChain": list(requested),
                "unavailable": list(unavailable),
                "rationale": rationale,
                "capabilityProvider": getattr(capability_profile, "provider", None),
            },
        )
    return selection


def _build_rationale(
    *,
    route: str,
    roles: tuple[ProviderRole, ...],
    chain: list[str],
    unavailable: list[str],
) -> str:
    if not chain:
        return (
            f"No available provider for route '{route}'. "
            f"Preferred roles {list(roles)} resolved to unavailable providers {unavailable}."
        )
    parts = [f"route '{route}' -> roles {list(roles)}; chain {chain}"]
    if unavailable:
        parts.append(f"(skipped unavailable: {unavailable})")
    return " ".join(parts)
