# Frontend → Backend Contract Checklist

**Status:** Frontend mocked. Backend not yet implemented.  
**Purpose:** Precise handoff document — every field, event, and RPC the UI assumes the backend will provide.

When implementing the backend, each item in this checklist should be explicitly delivered or explicitly deferred with a note.

---

## 1. Artifact Fields

### 1a. `approval_request` Artifact

Emitted when the harness intercepts a gated tool call. Stored as a regular artifact in the session's artifact list with kind `approval_request`.

```typescript
{
  // Standard artifact fields
  id: string;                     // UUID
  kind: 'approval_request';
  title: string;                  // Human-readable headline, e.g. "Approval required: send_message"
  oneLine: string;                // Gallery subtitle
  producedAt: string;             // ISO timestamp (when emitted)
  runId: string;

  // Approval-specific payload
  approvalData: {
    approvalId: string;           // UUID — used to correlate with resolution RPC
    runId: string;
    sessionKey: string;
    status: 'pending' | 'approved' | 'rejected' | 'modified' | 'expired';
    actionClass:
      | 'external_communication'
      | 'filesystem_write'
      | 'process_execution'
      | 'network_side_effect'
      | 'credential_or_sensitive_target';
    toolId: string;               // e.g. "send_message"
    proposedAction: {
      description: string;        // One sentence: what will happen
      target?: string | null;     // e.g. "telegram:@copenet_ops"
      payload?: Record<string, unknown>; // Full tool arguments (may contain 'message' key)
    };
    rationale: string | null;     // Why the agent wants to do this
    createdAt: string;            // ISO — when approval was requested
    resolvedAt: string | null;    // ISO — when decided; null if still pending
    outcome: {                    // null if still pending
      decision: 'approved' | 'rejected' | 'modified';
      modifiedPayload?: Record<string, unknown>;
      note?: string | null;       // Operator note
      decidedAt: string;          // ISO
    } | null;
  };
}
```

**Who emits:** Approval subsystem in the harness, before pausing the run.  
**When:** Immediately when the harness intercepts a gated tool call.  
**Delivery:** Via WebSocket event `artifact:approval_request` AND persisted to the session's artifact store.

---

### 1b. `outbound_message` Artifact

Emitted when `send_message` is called (immediately, even before approval/send).

```typescript
{
  id: string;
  kind: 'outbound_message';
  title: string;                  // e.g. "Message sent → Telegram @copenet_ops"
  oneLine: string;                // e.g. "Delivered · 47 chars · approved by operator"
  producedAt: string;
  runId: string;

  outboundData: {
    messageId: string;            // UUID
    runId: string;
    sessionKey: string;
    platform: string;             // 'telegram'
    target: string;               // 'telegram:@copenet_ops'
    targetDisplayName: string | null; // '@copenet_ops'
    messageText: string;          // The message content (original or modified)
    status: 'drafted' | 'pending_approval' | 'approved' | 'sent' | 'failed';
    approvalId: string | null;    // Links to associated approval_request artifact
    sentAt: string | null;        // ISO — confirmed delivery time
    failureReason: string | null; // Human-readable error if status = 'failed'
    createdAt: string;            // ISO
  };
}
```

**Who emits:** `send_message` tool handler.  
**When:** When the agent calls `send_message(action='send')`.  
**Updates:** The artifact status should update as the message progresses (pending_approval → approved → sent/failed). Use the `artifact:outbound_updated` event for partial updates.

---

## 2. Run / Session State Fields

### 2a. Run-paused state

When a run pauses for approval, the frontend needs to know the run is paused and why.

Required on `Session` or `SessionRunRecord`:

```typescript
// New field needed on Session (already has inFlightRunId):
pausedReason: 'awaiting_approval' | null;
pausedApprovalId: string | null;          // The approvalId blocking the run
```

Currently `Session.inFlightRunId` tells the UI a run is happening. The UI also needs `pausedReason` so it can show the banner and route to the Approvals tab.

**Alternative:** A dedicated WebSocket event (`run:paused`) is sufficient for the live UI; the session record stores this for reconnection recovery.

---

### 2b. Approval list per session

The Approvals tab shows history across all runs in a session. The backend needs:

```
GET /api/sessions/{sessionKey}/approvals
→ ApprovalRequest[]          // sorted by createdAt DESC
```

Or via the existing WebSocket RPC pattern:

```
approval.list(sessionKey) → ApprovalRequest[]
```

The frontend currently seeds this from mock data. When the backend lands, the adapter's `useApprovalHistory` hook will call this and replace the mock.

---

## 3. Approval RPC Methods

All of these follow the existing WebSocket RPC frame shape (`{ type: 'req', method, params }`).

### 3a. `approval.resolve`

Operator submits a decision.

```typescript
// Request
{
  method: 'approval.resolve',
  params: {
    approvalId: string;
    outcome: {
      decision: 'approved' | 'rejected' | 'modified';
      modifiedPayload?: Record<string, unknown>;
      note?: string | null;
      decidedAt: string;           // ISO — frontend provides this
    };
  }
}

// Response
{
  ok: true;
  payload: { approvalId: string; status: ApprovalStatus; }
}
```

**Side effects:**
- Run resumes with the decision outcome
- `approval_request` artifact status updates
- `outbound_message` artifact status updates (if applicable)
- `approval:resolved` event is broadcast so all open tabs update

---

### 3b. `approval.list`

```typescript
// Request
{ method: 'approval.list', params: { sessionKey: string } }

// Response
{ ok: true; payload: { approvals: ApprovalRequest[] } }
```

---

### 3c. `approval.get`

```typescript
// Request
{ method: 'approval.get', params: { approvalId: string } }

// Response
{ ok: true; payload: { approval: ApprovalRequest } }
```

---

## 4. send_message Tool Payloads

### 4a. Model-facing tool schema

```typescript
// Tool: send_message
// action='list': returns configured destinations
// action='send': sends to the specified target

// Input
{
  action: 'list' | 'send';
  target?: string;             // required for action='send'. Format: "platform:address"
  message?: string;            // required for action='send'
}

// Output for action='list'
{
  destinations: Array<{
    target: string;
    displayName: string;
    platform: string;
    requiresApproval: boolean;
    isDefault: boolean;
  }>;
}

// Output for action='send' (immediate, before delivery)
{
  messageId: string;
  status: 'pending_approval' | 'sent';
  approvalId?: string | null;   // populated when status='pending_approval'
  message: 'Approval required — run paused.' | 'Sent.';
}
```

---

### 4b. Destination configuration (backend → frontend)

The frontend's `DestinationDirectory` component shows configured destinations. These need to be served:

```typescript
interface MessageDestination {
  id: string;
  platform: string;             // 'telegram'
  target: string;               // 'telegram:@copenet_ops'
  displayName: string;
  threadLabel?: string | null;
  isDefault: boolean;
  requiresApproval: boolean;
  status: 'configured' | 'unconfigured' | 'error';
}
```

Delivery method (one of):
- Via the initial WebSocket handshake payload (preferred — same pattern as providers/models)
- Via `messaging.listDestinations()` RPC on demand

**Open question:** Should the frontend fetch destinations on every session open, or only on first connect?

---

## 5. WebSocket Events

All of these are `{ type: 'event', event: string, payload: {...} }` frames.

| Event | Direction | Payload | When |
|---|---|---|---|
| `approval:requested` | backend → frontend | `ApprovalRequest` | Harness intercepts gated tool call |
| `approval:resolved` | backend → frontend | `{ approvalId, outcome, status }` | Decision submitted (by any session tab) |
| `approval:expired` | backend → frontend | `{ approvalId, sessionKey }` | TTL elapsed without decision |
| `run:paused` | backend → frontend | `{ runId, sessionKey, reason: 'awaiting_approval', approvalId }` | Run loop suspended |
| `run:resumed` | backend → frontend | `{ runId, sessionKey }` | Run loop resumed after decision |
| `artifact:approval_request` | backend → frontend | Full `ApprovalRequest` wrapped in artifact shape | Approval artifact emitted |
| `artifact:outbound_message` | backend → frontend | Full `OutboundMessageRecord` wrapped in artifact shape | Outbound artifact emitted |
| `artifact:outbound_updated` | backend → frontend | `{ messageId, status, sentAt?, failureReason? }` | Outbound message status changed |
| `messaging:destinations` | backend → frontend | `MessageDestination[]` | On connect or on config change |

---

## 6. Frontend Adapter Wiring Points

When the backend ships, these adapter functions need to be updated to call real RPCs instead of returning mock data:

| Adapter Function | File | Currently | Needs |
|---|---|---|---|
| `usePendingApproval` | `runtime/adapter.ts` | Falls back to mock | Read from store (populated by WebSocket event) |
| `useApprovalHistory` | `runtime/adapter.ts` | Loads `getMockApprovalHistory()` on first render | Call `approval.list(sessionKey)` RPC |
| `useDestinations` | `runtime/adapter.ts` | Loads `getMockDestinations()` on first render | Receive from `messaging:destinations` event or RPC |
| `useMockTransitions` | `runtime/adapter.ts` | Full mock — mutates store directly | Replace with real WS RPC calls; mock stays for demo mode |
| `useArtifacts` | `runtime/adapter.ts` | Reads from `getArtifacts()` mock | Already tries `wsClient.listSessionRuns`; artifact endpoint needed |

---

## 7. wsClient.ts Methods Needed

Add these to `/Users/copeharder/Programming/CopeNet/src/copenet/host/frontend/src/lib/wsClient.ts`:

```typescript
// Submit approval decision
resolveApproval(approvalId: string, outcome: ApprovalOutcome): Promise<void>

// List all approvals for a session
listApprovals(sessionKey: string): Promise<ApprovalRequest[]>

// List configured messaging destinations
listDestinations(): Promise<MessageDestination[]>
```

And register these WebSocket event handlers in the connection setup:

```typescript
case 'approval:requested':   store.setPendingApproval(payload);
case 'approval:resolved':    store.resolveApproval(payload.approvalId, payload.outcome);
case 'approval:expired':     store.upsertApprovalInHistory({ ...payload, status: 'expired' });
case 'run:paused':           store.setRunPausedReason('awaiting_approval');
case 'run:resumed':          store.setRunPausedReason(null);
case 'messaging:destinations': store.setDestinations(payload);
case 'artifact:outbound_updated': // update outbound artifact status in artifact list
```

---

## 8. Open Questions & Assumptions

### Open Questions

1. **Approval TTL:** What is the default TTL for a pending approval before it expires? The UI treats expiry the same as rejection (run resumes, banner disappears). Recommend: 30 minutes, operator-configurable.

2. **Multiple pending approvals:** The UI currently assumes one pending approval at a time (V1 serialization). If the backend ever allows concurrent approvals, the `pendingApproval: ApprovalRequest | null` store field becomes `pendingApprovals: ApprovalRequest[]`. This is a breaking store change — flag before shipping concurrency.

3. **Destinations source of truth:** Are destinations in CopeNet config (bot token + chat IDs), or are they dynamically discoverable? Currently UI assumes static config. If dynamic, add a refresh button to `DestinationDirectory`.

4. **Operator-initiated send_message:** The `SendMessageComposer` lets the operator compose a message outside an agent run. Does the backend need a separate RPC for this (`messaging.send`), or does it always go through the agent tool loop? Assuming direct RPC for operator-initiated sends is simplest.

5. **Reconnection state:** If the operator refreshes the browser while a run is paused for approval, the UI needs to restore the pending approval state. This requires either `Session.pausedApprovalId` or `approval.list()` on reconnect.

6. **Approval in run record:** Should each `SessionRunRecord` include the `approvalId` of any approval that blocked it? This would allow the Activity tab to link tool calls → approvals without a separate lookup.

7. **`send_message` from operator vs. from agent:** These are semantically different — one is explicit operator intent, one is agent-proposed. Should they produce the same `outbound_message` artifact shape? Current assumption: yes, same shape, distinguished by `runId` (operator sends use a synthetic `operator_action` run ID).

### Assumptions

- All approval decisions are persisted in the session's run record (audit trail).
- The harness serializes approval requests: only one pending approval per run at a time.
- The frontend is stateless w.r.t. approval history on reload — it calls `approval.list()` to repopulate.
- `send_message` always emits an `outbound_message` artifact, even on failure. The artifact is the canonical failure record.
- Destinations not in the configured address book are rejected at the tool-policy level, before an approval request is emitted.
- The `requiresApproval` field on `MessageDestination` is backend-configured, not hardcoded per platform.
- For V1, only `send_message` routes through the approval subsystem. Other action classes come later.

---

## 9. Component → Backend Dependency Summary

| Component | Reads from backend | Writes to backend |
|---|---|---|
| `ApprovalRequestCard` | None (store) | `approval.resolve()` RPC |
| `ApprovalQueuePanel` | `approval.list()` RPC | `approval.resolve()` (via card) |
| `PausedRunBanner` | `run:paused` event (store) | None |
| `SendMessageComposer` | `messaging:destinations` event | `messaging.send()` RPC (future) |
| `DestinationDirectory` | `messaging:destinations` event | None (read-only) |
| `OutboundMessageCard` | `artifact:outbound_message` event | None |
| `ArtifactsPanel` | `approval_request` / `outbound_message` artifacts | None |
| `RightPanel` → Approvals tab | `approval.list()` on mount | Via child components |

---

*Generated: 2026-04-27. Update this checklist as backend fields are confirmed or changed.*
