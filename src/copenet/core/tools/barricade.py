"""The CopeNet Barricade — taint-tracking + egress hardening for tool use.

Always on. ``COPENET_BARRICADE=0`` (or false/no/off) is a deliberate, loud escape
hatch for local debugging of the guard itself — it is not a supported deployment
mode, and every disabled check logs a warning so it's never silently off.

The threat this defends (see docs/THREAT_MODEL.md): an autonomous agent ingests
content an attacker controls (a fetched web page, a poisoned file) and that
content steers the next tool call into a harmful side effect — write a payload,
run a command, leak a secret. The dangerous shape is always:

    untrusted-content-in  ->  privileged-action-out   (same run)

The Barricade is the HARD layer. It does not ask the model to be careful; it
assumes the model has already been fooled and contracts privilege deterministically:

1. **Taint tracking** — when untrusted content enters a run (``web.search`` /
   ``web.fetch``), the session is marked tainted. While tainted, state-changing
   tools (classified from the descriptor, so new MCP/browser/message tools are
   covered automatically) return ``approval_required`` instead of executing —
   even in full-access mode. Taint PERSISTS across turns in a session, because a
   poisoned tool output from turn N is replayed into turn N+1's model context.
2. **Egress guard** — ``web.fetch`` AND ``web.search`` are outbound channels:
   both refuse private/loopback/metadata hosts, secret-like query data, and any
   value previously read from a sensitive file. Egress to an attacker target is a
   HARD block (not operator-approvable through the tainted flow).

Every decision is recorded on the run's :class:`RunSecurityState` so the operator
(and a lecture demo) can render a clean security timeline of what happened.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .contracts import ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

_LOG = logging.getLogger(__name__)

_SECURITY_KEY = "security"

# Tools whose output is attacker-influenceable content. Reading their result
# taints the run. web.* is the clean, demonstrable case; this set is the single
# place to extend taint sources (untrusted file reads, inbound messages, …).
UNTRUSTED_SOURCE_TOOLS = {"web.search", "web.fetch"}

# Fallback list of state-changing tools (used only when a descriptor is missing).
# The live classification is descriptor-derived — see is_gated_side_effect — so a
# new MCP/browser/message tool is gated automatically without editing this set.
SIDE_EFFECT_TOOLS = {"files.write", "files.edit", "shell.exec", "artifact.create"}

# Categories whose tools mutate local state and must be gated while tainted.
_MUTATING_CATEGORIES = {"repo-write", "shell-read", "shell-write", "artifact"}
# Read-only external categories that are taint SOURCES, never gated as effects.
_READONLY_EXTERNAL_CATEGORIES = {"web"}

# Session-scoped taint that PERSISTS across turns (Codex P1). RunSecurityState
# lives in per-run ephemeral context, but a poisoned tool output from turn N is
# replayed into turn N+1's model context — so taint must outlive the run or a
# second turn acts with clean privileges. This in-process registry carries taint
# + recorded secret canaries forward, keyed by session. (Durable-across-restart
# provenance is the Tier-B follow-up; replayed untrusted content survives a
# restart, so this is the cheap-but-correct first layer.)
_SESSION_SECURITY: dict[str, dict[str, Any]] = {}

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
# canaries the egress guard watches for in outbound URLs. Filename-pattern match
# (".env", "token", ...) catches the common naming case; directory-pattern match
# catches durable credential stores whose filenames don't look secret-shaped —
# e.g. provider OAuth tokens live at .copenet/providers/auth/<provider>.json.
_SENSITIVE_PATH_RE = re.compile(r"(\.env|secret|credential|password|token|\.pem|id_rsa)", re.IGNORECASE)
_SENSITIVE_PATH_DIR_RE = re.compile(r"providers[\\/]+auth", re.IGNORECASE)
_SENSITIVE_VALUE_RE = re.compile(r"[A-Za-z0-9_\-]{6,}")

_BARRICADE_DISABLE_VALUES = {"0", "false", "no", "off"}
_disabled_warning_logged = False

# Destinations web.fetch/web.search may reach WITHOUT an operator approval prompt.
# Curated from what CopeNet's own subsystems already talk to (its configured
# search backends) plus common, low-risk reference sources. Anything else public
# still works — it just pauses for a one-time operator approval instead of being
# silently allowed, per the "read broadly, but ask about places you haven't
# vetted" model. Extend via COPNET_WEB_FETCH_ALLOWLIST (comma-separated apex
# domains, additive) rather than editing this constant.
DEFAULT_ALLOWED_FETCH_DOMAINS: frozenset[str] = frozenset(
    {
        # search backends CopeNet is already configured to call
        "api.exa.ai",
        "api.search.brave.com",
        "html.duckduckgo.com",
        # general reference / docs
        "en.wikipedia.org",
        "wikipedia.org",
        "github.com",
        "raw.githubusercontent.com",
        "developer.mozilla.org",
        # finance/market reference (aligned with Market Monitor's own data sources)
        "www.sec.gov",
        "data.sec.gov",
        "home.treasury.gov",
        "finance.yahoo.com",
    }
)

_FETCH_ALLOWLIST_ENV = "COPNET_WEB_FETCH_ALLOWLIST"
_LEGACY_PRIVATE_ALLOWLIST_ENV = "COPENET_BARRICADE_FETCH_ALLOWLIST"


def barricade_enabled() -> bool:
    """Return True when the Barricade hardening is switched on (the default).

    Logs a warning (once per process) when it's off, so a disabled guard never
    goes unnoticed.
    """
    global _disabled_warning_logged
    raw = os.environ.get("COPENET_BARRICADE", "").strip().lower()
    enabled = raw not in _BARRICADE_DISABLE_VALUES
    if not enabled and not _disabled_warning_logged:
        _disabled_warning_logged = True
        _LOG.warning(
            "CopeNet Barricade is DISABLED (COPENET_BARRICADE=%r) — taint tracking, the "
            "egress guard, and secret-exfiltration checks are NOT active for this process.",
            raw,
        )
    return enabled


def fetch_allowlist() -> set[str]:
    """Destinations web.fetch/web.search may reach without an approval prompt.

    Built-in defaults, unioned with operator-configured entries from
    COPNET_WEB_FETCH_ALLOWLIST (and the legacy COPENET_BARRICADE_FETCH_ALLOWLIST
    name, merged in for back-compat). Additive: operators extend the safe
    defaults, they don't need to restate them.
    """
    operator_raw = os.environ.get(_FETCH_ALLOWLIST_ENV, "")
    legacy_raw = os.environ.get(_LEGACY_PRIVATE_ALLOWLIST_ENV, "")
    operator_entries = {
        host.strip().lower() for host in f"{operator_raw},{legacy_raw}".split(",") if host.strip()
    }
    return DEFAULT_ALLOWED_FETCH_DOMAINS | operator_entries


def host_matches_allowlist(hostname: str | None, allowlist: set[str]) -> bool:
    """True when `hostname` equals or is a subdomain of an entry in `allowlist`."""
    host = (hostname or "").lower().strip(".")
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in allowlist)


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
    """Return (creating if needed) the run's security state from ephemeral context.

    On first creation the state is seeded from any persisted session taint so a
    poisoned page from a prior turn keeps the run tainted (Codex P1).
    """
    state = context.ephemeral.get(_SECURITY_KEY)
    if not isinstance(state, RunSecurityState):
        state = RunSecurityState()
        _seed_state_from_session(context, state)
        context.ephemeral[_SECURITY_KEY] = state
    return state


def _session_key(context: ToolExecutionContext) -> str:
    return (context.session_key or "").strip()


def _seed_state_from_session(context: ToolExecutionContext, state: RunSecurityState) -> None:
    prior = _SESSION_SECURITY.get(_session_key(context))
    if not prior:
        return
    if prior.get("untrusted_context"):
        state.untrusted_context = True
        state.record(SecurityEvent("taint", "session", "untrusted context carried from a prior turn"))
    for src in prior.get("untrusted_sources", []):
        if src not in state.untrusted_sources:
            state.untrusted_sources.append(src)
    for val in prior.get("sensitive_values", []):
        if val not in state.sensitive_values:
            state.sensitive_values.append(val)


def _persist_state_to_session(context: ToolExecutionContext, state: RunSecurityState) -> None:
    key = _session_key(context)
    if not key:
        return
    _SESSION_SECURITY[key] = {
        "untrusted_context": state.untrusted_context,
        "untrusted_sources": list(dict.fromkeys(state.untrusted_sources)),
        "sensitive_values": list(dict.fromkeys(state.sensitive_values)),
    }


def reset_session_security(session_key: str | None = None) -> None:
    """Forget persisted session taint — for a fresh chat/branch, or test isolation."""
    if session_key is None:
        _SESSION_SECURITY.clear()
    else:
        _SESSION_SECURITY.pop(session_key.strip(), None)


def is_gated_side_effect(descriptor: ToolDescriptor | None, tool_id: str) -> bool:
    """Return True if this tool mutates state and must be gated while tainted.

    Descriptor-derived (Codex P2) so new MCP/browser/message tools are gated
    automatically. Read-only external sources (web.*) are never gated as effects.
    """
    if descriptor is None:
        return tool_id in SIDE_EFFECT_TOOLS
    if descriptor.category in _READONLY_EXTERNAL_CATEGORIES:
        return False
    if descriptor.side_effect == "write":
        return True
    if descriptor.category in _MUTATING_CATEGORIES:
        return True
    # external + not a read-only web source = an outbound effect (message send,
    # API POST, shell-style action) — gate it.
    if descriptor.side_effect == "external":
        return True
    return tool_id in SIDE_EFFECT_TOOLS


def approval_key(request: ToolExecutionRequest) -> str:
    """Bind an approval to the EXACT call: tool id + canonical-argument digest.

    Codex P1: approvals were keyed by target (path/command), so approving one
    write to out.txt let a *different* later write to out.txt ride free. Keying on
    the argument digest means an approval covers only that exact action.
    """
    payload = json.dumps(request.arguments or {}, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{request.tool_id}:{digest}"


def _target_key(request: ToolExecutionRequest) -> str:
    """Human-readable target for timelines/approval prompts (not an auth key)."""
    args = request.arguments or {}
    for key in ("command", "path", "url", "target", "title", "query"):
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
    descriptor: ToolDescriptor | None = None,
) -> ToolExecutionResult | None:
    """Return a blocking result if the Barricade should stop this call, else None.

    Checks, all only active when the Barricade is enabled:
    - egress guard on ``web.fetch`` (always, regardless of taint)
    - egress guard on ``web.search`` (the query is an outbound channel too)
    - side-effect gate (descriptor-derived) while the run is tainted
    """
    if not barricade_enabled():
        return None

    if request.tool_id == "web.fetch":
        blocked = _egress_guard(request, context)
        if blocked is not None:
            return blocked

    if request.tool_id == "web.search":
        blocked = _search_egress_guard(request, context)
        if blocked is not None:
            return blocked

    if is_gated_side_effect(descriptor, request.tool_id):
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
    # Operator already approved this EXACT call (tool id + argument digest)
    # earlier in the run — a different call to the same target is NOT covered.
    approved = context.ephemeral.get("barricade_approved")
    if isinstance(approved, set) and approval_key(request) in approved:
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

    # An operator-configured allowlist entry means "trusted" for both purposes:
    # it exempts a private host from the loopback/metadata block below, AND it
    # skips the approval prompt for an otherwise-unknown public destination.
    allowlisted = host_matches_allowlist(parsed.hostname, fetch_allowlist())
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

    if reason is not None:
        state.record(SecurityEvent("egress_blocked", "web.fetch", reason))
        return _egress_blocked_result("web.fetch", raw_url, reason, state)

    if not allowlisted:
        # Not private, no leaked secret, no secret-shaped query param — but not a
        # destination the operator has vetted either. Ask instead of silently
        # fetching an unknown host (this is the "approval-escapable" tier, not a
        # hard block — unlike the reasons above, which can never be approved).
        approval_id_target = parsed.hostname or raw_url
        state.record(SecurityEvent("egress_approval_required", "web.fetch", approval_id_target))
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=False,
            summary=f"Approval required: fetch '{approval_id_target}' is not on the trusted fetch allowlist",
            error="barricade_fetch_not_allowlisted",
            output={
                "command": None,
                "target": raw_url,
                "policyDecision": "approval_required",
                "policySummary": (
                    f"Barricade: '{approval_id_target}' is not on the fetch allowlist "
                    f"(extend it via {_FETCH_ALLOWLIST_ENV})."
                ),
                "barricade": {"reason": "fetch_not_allowlisted", "hostname": approval_id_target},
            },
        )

    return None


def _search_egress_guard(
    request: ToolExecutionRequest,
    context: ToolExecutionContext,
) -> ToolExecutionResult | None:
    """Block a web.search whose query smuggles out a previously-read secret.

    Codex P1: the egress guard only covered web.fetch, but web.search POSTs a
    model-chosen query to the search engine — an exfiltration channel of its own.
    """
    query = str((request.arguments or {}).get("query") or "")
    if not query:
        return None
    state = get_security_state(context)
    leaked = _leaked_secret(query, state)
    if leaked is None:
        return None
    reason = f"search query appears to carry a previously-read secret value ('{leaked[:8]}…')"
    state.record(SecurityEvent("egress_blocked", "web.search", reason))
    return _egress_blocked_result("web.search", query[:120], reason, state)


def _egress_blocked_result(tool_id: str, target: str, reason: str, state: RunSecurityState) -> ToolExecutionResult:
    """A HARD block (not approval_required): egress to attacker targets is never
    operator-approvable through the tainted flow, so it must not park the run for
    an approval the wrapper can't clear (Codex P2). Use the allowlist env for
    legitimately-trusted internal hosts instead."""
    return ToolExecutionResult(
        tool_id=tool_id,
        ok=False,
        summary=f"Egress blocked: {reason}",
        error="barricade_egress_blocked",
        output={
            "target": target,
            "policyDecision": "egress_blocked",
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

    # Carry taint + recorded canaries forward to the next turn in this session.
    _persist_state_to_session(context, state)


def _record_sensitive_read(
    request: ToolExecutionRequest,
    result: ToolExecutionResult,
    state: RunSecurityState,
) -> None:
    path = str((request.arguments or {}).get("path") or "")
    if not (_SENSITIVE_PATH_RE.search(path) or _SENSITIVE_PATH_DIR_RE.search(path)):
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
