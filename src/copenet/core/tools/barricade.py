"""The CopeNet Barricade — taint-tracking + egress hardening for tool use.

Toggle with the ``COPENET_BARRICADE=1`` environment variable.

The threat this defends (see docs/THREAT_MODEL.md): an autonomous agent ingests
content an attacker controls (a fetched web page, a poisoned file) and that
content steers the next tool call into a harmful side effect — write a payload,
run a command, leak a secret. The dangerous shape is always:

    untrusted-content-in  ->  privileged-action-out   (same run)

The Barricade is the HARD layer. It does not ask the model to be careful; it
assumes the model has already been fooled and contracts privilege deterministically:

1. **Taint tracking** — when untrusted content enters a run (``web.search`` /
   ``web.fetch``), the run is marked tainted. While tainted, side-effectful tools
   (``files.write`` / ``files.edit`` / ``shell.exec`` / ``artifact.create``)
   return ``approval_required`` instead of executing — even in full-access mode.
2. **Egress guard** — ``web.fetch`` refuses private/loopback/metadata hosts and
   URLs whose query string carries secret-like data, so a "read-only" fetch can't
   become an exfiltration channel.

Every decision is recorded on the run's :class:`RunSecurityState` so the operator
(and a lecture demo) can render a clean security timeline of what happened.
"""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .contracts import ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

_SECURITY_KEY = "security"

# Tools whose output is attacker-influenceable content. Reading their result
# taints the run. web.* is the clean, demonstrable case; this set is the single
# place to extend taint sources (untrusted file reads, inbound messages, …).
UNTRUSTED_SOURCE_TOOLS = {"web.search", "web.fetch"}

# Tools that change the world. While a run is tainted these require approval.
SIDE_EFFECT_TOOLS = {"files.write", "files.edit", "shell.exec", "artifact.create"}

# Query-parameter names that suggest secret material is being smuggled in a URL.
_SECRET_HINTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "session",
    "cookie",
)

# Paths whose contents are treated as sensitive — values read from them become
# canaries the egress guard watches for in outbound URLs.
_SENSITIVE_PATH_RE = re.compile(r"(\.env|secret|credential|password|token|\.pem|id_rsa)", re.IGNORECASE)
_SENSITIVE_VALUE_RE = re.compile(r"[A-Za-z0-9_\-]{6,}")


def barricade_enabled() -> bool:
    """Return True when the Barricade hardening is switched on."""
    return os.environ.get("COPENET_BARRICADE", "").strip().lower() in {"1", "true", "yes", "on"}


def _fetch_host_allowlist() -> set[str]:
    """Operator-trusted hosts the egress guard may fetch despite being private.

    Real operators sometimes need the agent to reach a specific internal host
    (a docs server, an intranet wiki). `COPENET_BARRICADE_FETCH_ALLOWLIST` is a
    comma-separated host allowlist that exempts ONLY the private-address check —
    the secret-parameter and canary-value checks still apply, so an allowlisted
    host still can't be used to smuggle a freshly-read secret.
    """
    raw = os.environ.get("COPENET_BARRICADE_FETCH_ALLOWLIST", "")
    return {host.strip().lower() for host in raw.split(",") if host.strip()}


@dataclass
class SecurityEvent:
    """One entry in the run's security timeline."""

    kind: str            # taint | side_effect_gated | egress_blocked | side_effect_allowed
    tool_id: str
    detail: str
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "toolId": self.tool_id, "detail": self.detail, "source": self.source}


@dataclass
class RunSecurityState:
    """Per-run security posture accumulated as tools execute."""

    untrusted_context: bool = False
    untrusted_sources: list[str] = field(default_factory=list)
    sensitive_values: list[str] = field(default_factory=list)
    events: list[SecurityEvent] = field(default_factory=list)

    def record(self, event: SecurityEvent) -> None:
        self.events.append(event)

    def timeline(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.events]


def get_security_state(context: ToolExecutionContext) -> RunSecurityState:
    """Return (creating if needed) the run's security state from ephemeral context."""
    state = context.ephemeral.get(_SECURITY_KEY)
    if not isinstance(state, RunSecurityState):
        state = RunSecurityState()
        context.ephemeral[_SECURITY_KEY] = state
    return state


def _target_key(request: ToolExecutionRequest) -> str:
    args = request.arguments or {}
    for key in ("command", "path", "url", "target", "title"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return request.tool_id


# ---------------------------------------------------------------------------
# Pre-dispatch gates (run BEFORE a tool's side effect happens)
# ---------------------------------------------------------------------------


def pre_dispatch_gate(
    request: ToolExecutionRequest,
    context: ToolExecutionContext,
) -> ToolExecutionResult | None:
    """Return a blocking result if the Barricade should stop this call, else None.

    Two independent checks, both only active when the Barricade is enabled:
    - egress guard on ``web.fetch`` (always, regardless of taint)
    - side-effect gate while the run is tainted
    """
    if not barricade_enabled():
        return None

    if request.tool_id == "web.fetch":
        blocked = _egress_guard(request, context)
        if blocked is not None:
            return blocked

    if request.tool_id in SIDE_EFFECT_TOOLS:
        gated = _side_effect_gate(request, context)
        if gated is not None:
            return gated

    return None


def _side_effect_gate(
    request: ToolExecutionRequest,
    context: ToolExecutionContext,
) -> ToolExecutionResult | None:
    state = get_security_state(context)
    if not state.untrusted_context:
        return None

    target = _target_key(request)
    # Operator already approved this exact action earlier in the run.
    approved = context.ephemeral.get("barricade_approved")
    if isinstance(approved, set) and target in approved:
        state.record(SecurityEvent("side_effect_allowed", request.tool_id, f"operator-approved: {target}"))
        return None

    sources = ", ".join(dict.fromkeys(state.untrusted_sources)) or "untrusted content"
    summary = (
        f"Barricade: this run observed untrusted content ({sources}); "
        f"{request.tool_id} requires operator approval before it can act."
    )
    state.record(SecurityEvent("side_effect_gated", request.tool_id, target, source=sources))
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=False,
        summary=f"Approval required: {request.tool_id} after untrusted content",
        error="barricade_tainted_side_effect",
        output={
            "command": target if request.tool_id == "shell.exec" else None,
            "target": target,
            "policyDecision": "approval_required",
            "policySummary": summary,
            "barricade": {"reason": "untrusted_context", "sources": list(dict.fromkeys(state.untrusted_sources))},
        },
    )


def _egress_guard(
    request: ToolExecutionRequest,
    context: ToolExecutionContext,
) -> ToolExecutionResult | None:
    raw_url = str((request.arguments or {}).get("url") or "").strip()
    if not raw_url:
        return None
    candidate = raw_url if "://" in raw_url else f"https://{raw_url}"
    parsed = urlparse(candidate)
    state = get_security_state(context)

    allowlisted = (parsed.hostname or "").lower() in _fetch_host_allowlist()
    reason: str | None = None
    if parsed.scheme not in {"http", "https"}:
        reason = f"non-web scheme '{parsed.scheme or '?'}' is blocked"
    elif _is_private_host(parsed.hostname) and not allowlisted:
        reason = f"refusing fetch to private/loopback/metadata host '{parsed.hostname}'"
    else:
        leaked = _leaked_secret(candidate, state)
        if leaked:
            reason = f"URL appears to carry a previously-read secret value ('{leaked[:8]}…')"
        else:
            hint = _secret_hint_in_query(parsed.query)
            if hint:
                reason = f"URL query carries secret-like parameter '{hint}=' — possible exfiltration"

    if reason is None:
        return None

    state.record(SecurityEvent("egress_blocked", "web.fetch", reason))
    return ToolExecutionResult(
        tool_id="web.fetch",
        ok=False,
        summary=f"Egress blocked: {reason}",
        error="barricade_egress_blocked",
        output={
            "target": raw_url,
            "policyDecision": "approval_required",
            "policySummary": f"Barricade egress guard: {reason}.",
            "barricade": {"reason": "egress", "detail": reason},
        },
    )


def _is_private_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = hostname.lower().strip("[]")
    if host in {"localhost", "metadata", "metadata.google.internal"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def _secret_hint_in_query(query: str) -> str | None:
    lowered = (query or "").lower()
    for hint in _SECRET_HINTS:
        if f"{hint}=" in lowered:
            return hint
    return None


def _leaked_secret(url: str, state: RunSecurityState) -> str | None:
    for value in state.sensitive_values:
        if value and len(value) >= 6 and value in url:
            return value
    return None


# ---------------------------------------------------------------------------
# Post-dispatch accounting (run AFTER a tool returns)
# ---------------------------------------------------------------------------


def post_dispatch_record(
    request: ToolExecutionRequest,
    context: ToolExecutionContext,
    result: ToolExecutionResult,
) -> None:
    """Update taint + sensitive-value tracking from a completed tool result."""
    if not barricade_enabled() or not result.ok:
        return
    state = get_security_state(context)

    if request.tool_id in UNTRUSTED_SOURCE_TOOLS:
        if not state.untrusted_context:
            state.untrusted_context = True
        if request.tool_id not in state.untrusted_sources:
            state.untrusted_sources.append(request.tool_id)
        state.record(SecurityEvent("taint", request.tool_id, "run marked untrusted", source=request.tool_id))

    if request.tool_id == "files.read":
        _record_sensitive_read(request, result, state)


def _record_sensitive_read(
    request: ToolExecutionRequest,
    result: ToolExecutionResult,
    state: RunSecurityState,
) -> None:
    path = str((request.arguments or {}).get("path") or "")
    if not _SENSITIVE_PATH_RE.search(path):
        return
    body = result.body if result.body is not None else result.output
    content = body.get("content") if isinstance(body, dict) else None
    if not isinstance(content, str):
        return
    for match in _SENSITIVE_VALUE_RE.findall(content):
        # Skip common words; keep token-looking values as canaries to watch for.
        if any(ch.isdigit() for ch in match) or match.isupper() or "_" in match:
            if match not in state.sensitive_values:
                state.sensitive_values.append(match)
