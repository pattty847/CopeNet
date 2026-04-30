# Approval Lifecycle — CopeNet Design Spec

## Summary

This document defines the end-to-end lifecycle for operator approval of agent actions in CopeNet. It covers user flow, UI states, required backend fields, backend events, and open questions.

---

## Motivation

CopeNet's current `ToolPolicy` is a static allowlist — it can block a category of tool, but it cannot pause a live run, present a proposed action, and resume from the human's decision. That gap makes "ask before stronger actions" impossible without external platform tricks.

The design goal is a first-class approval subsystem modeled as **run state**, not a preflight toggle. The agent proposes; the operator decides; the run resumes.

---

## Actors

| Actor | Role |
|---|---|
| Agent (LLM + harness) | Emits a proposed action requiring approval |
| Backend harness | Detects that a tool call needs approval, pauses the run, emits the approval request event |
| Backend runtime | Persists approval state, exposes RPC to list/resolve approvals |
| Frontend | Renders approval state, lets the operator decide |
| Operator | Reviews and decides: approve / reject / modify |

---

## Lifecycle States

```
proposed → pending → approved  → run_resumed → tool_executed
                   → rejected  → run_resumed (tool skipped / error injected)
                   → modified  → run_resumed (modified payload used)
                   → expired   → run_resumed (treated as rejected after TTL)
```

---

## User Flow

### 1. Run in progress

Operator sees the normal chat workspace and runtime inspector. The agent is executing tool calls. Activity panel shows a `send_message` tool call pending.

### 2. Agent proposes a gated action

The agent calls `send_message` (or any other approval-gated tool). The harness intercepts this before execution, emits an `approval_requested` event over WebSocket, and suspends the tool loop.

**UI changes:**
- Paused-run banner appears at the top of ChatWorkspace (yellow/accent color, "Run paused — approval required")
- Banner is clickable and opens the Runtime tab in the Inspector
- The Runtime tab shows an `ApprovalRequestCard` at the very top (above session info)
- The Artifacts tab shows an `approval_request` artifact card
- The Activity tab shows the `send_message` tool call in the run timeline

### 3. Operator reviews

The `ApprovalRequestCard` shows:
- Tool being requested (`send_message`)
- Action class (`external_communication`)
- Destination target (`telegram:@copenet_ops`)
- The proposed message body (expandable)
- The agent's rationale for wanting to send now
- Three buttons: **Approve**, **Reject**, **Modify**

### 4. Operator decides

**Approve:** The backend resumes the run with the original proposed payload. The tool executes. An `outbound_message` artifact is produced with status `sent`.

**Reject:** The backend resumes the run with a rejection signal. The harness injects a synthetic tool result indicating rejection. The agent can handle this gracefully (e.g., summarize instead of sending).

**Modify:** The operator can edit the message text inline before approving. The modified payload is sent instead of the original. The `outbound_message` artifact shows the modified content.

### 5. Run resumes

Once the approval decision is recorded:
- The paused-run banner disappears
- The `ApprovalRequestCard` updates to show the decision (Approved / Rejected / Modified)
- The run continues from where it paused

---

## UI States

| State | Banner | Runtime Tab | Artifacts Tab |
|---|---|---|---|
| No pending approval | Hidden | Normal content | Normal artifacts |
| Pending approval | Visible, pulsing | ApprovalRequestCard at top | approval_request card |
| Decision made (approved) | Hidden | Card shows "Approved" | Card updated |
| Decision made (rejected) | Hidden | Card shows "Rejected" | Card updated |
| Decision made (modified) | Hidden | Card shows "Modified" | Card updated |
| Approval expired | Hidden | Card shows "Expired" | Card updated |

---

## Required Backend Fields

### `ApprovalRequest` (backend → frontend event payload)

```typescript
{
  approvalId: string;            // UUID
  runId: string;
  sessionKey: string;
  status: 'pending' | 'approved' | 'rejected' | 'modified' | 'expired';
  actionClass: ApprovalActionClass;
  toolId: string;                // e.g. "send_message"
  proposedAction: {
    description: string;         // Human-readable description of what will happen
    target?: string | null;      // e.g. "telegram:@copenet_ops"
    payload?: Record<string, unknown>; // Full tool arguments
  };
  rationale: string | null;      // Why the agent wants to do this
  createdAt: string;             // ISO timestamp
  resolvedAt: string | null;
  outcome: ApprovalOutcome | null;
}
```

### `ApprovalOutcome` (frontend → backend RPC payload)

```typescript
{
  decision: 'approved' | 'rejected' | 'modified';
  modifiedPayload?: Record<string, unknown>; // Only for 'modified'
  note?: string | null;          // Operator note
  decidedAt: string;             // ISO timestamp
}
```

### Action Classes

```typescript
type ApprovalActionClass =
  | 'external_communication'     // send_message, email, Slack
  | 'filesystem_write'           // file write, delete, patch
  | 'process_execution'          // shell, subprocess
  | 'network_side_effect'        // HTTP POST, webhook trigger
  | 'credential_or_sensitive_target'; // anything touching credentials
```

---

## Backend Events Needed

| Event | Direction | When |
|---|---|---|
| `approval:requested` | backend → frontend | Harness intercepts gated tool, emits before pausing run |
| `approval:resolved` | frontend → backend (RPC) | Operator submits decision |
| `approval:expired` | backend → frontend | TTL passed without decision |
| `run:paused` | backend → frontend | Run suspended waiting on approval |
| `run:resumed` | backend → frontend | Run continued after decision |

---

## RPC Surface (frontend → backend)

```
approval.resolve(approvalId, outcome: ApprovalOutcome) → void
approval.list(sessionKey) → ApprovalRequest[]
approval.get(approvalId) → ApprovalRequest
```

---

## Hardline Actions (never approvable)

Some actions should never be allowed through the agent regardless of operator approval. The backend should maintain an unconditional blocklist (analogous to Hermes's hardline blocklist in `tools/approval.py:76`):

- Writing to files outside the project root
- Deleting git history
- Reading credentials/secrets files directly
- Sending to unregistered destinations (not in the configured address book)

These should be blocked at the tool-policy layer before an approval request is even emitted.

---

## Open Questions

1. **TTL:** How long should an approval request stay `pending` before it expires? Likely session-scoped with a configurable timeout (e.g. 30 min).
2. **Multiple concurrent approvals:** Can two tool calls require approval in the same run at the same time? For V1, assume the harness serializes: one pending approval at a time.
3. **Persistent allowlist:** Should the operator be able to "always approve this tool for this session"? Hermes has permanent allowlists. Defer to V2.
4. **Mobile UX:** The approval card needs to work in the mobile sheet view. The current `ApprovalRequestCard` is built for desktop width. Add a mobile-aware version before shipping.
5. **Session restart after rejection:** If the operator rejects, can the operator also send a correction message directly in chat to redirect the agent? This is likely the natural flow — no special handling needed; the normal chat input still works.
6. **Audit trail:** All approval decisions should appear in the session transcript or run record so the operator can reconstruct what happened. Define the exact schema.

---

## Assumptions

- Approvals are session-scoped: a different session may have different approval state.
- The frontend is always the initiating side for resolution (the operator submits the decision via the UI).
- The backend is authoritative for approval state; the frontend is a view + action surface.
- For V1, only `send_message` (outbound communication) requires approval. Other gated tools come later.
