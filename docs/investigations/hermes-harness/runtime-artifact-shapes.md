# Runtime Artifact Shapes — CopeNet Design Spec

## Summary

This document defines the complete set of runtime artifact types, their frontend representations, the backend fields required to populate them, and which UI surfaces render each kind.

---

## Artifact System Overview

Artifacts are inspectable records produced during a run. They persist with the run record and are displayed in the **Artifacts tab** of the Inspector panel. Each artifact has:
- A `kind` discriminant that determines which card component renders it
- A short `oneLine` summary for the gallery view
- Optional extended payload fields for detailed inspection

Artifacts should make the operator's question "what did the agent actually do?" answerable without reading raw logs.

---

## Artifact Kinds

### 1. `summary`

A prose summary of what the agent found or concluded.

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique artifact ID |
| `title` | string | Headline (one short sentence) |
| `oneLine` | string | Gallery subtitle |
| `producedAt` | ISO string | When this artifact was written |
| `runId` | string | Producing run |
| `bodyMarkdown` | string | Full markdown body |

**UI:** Text card with markdown body. Open button → InspectorDrawer renders body.

---

### 2. `answer`

A direct answer to the operator's question, backed by file evidence.

Same shape as `summary`. Semantically distinct: an `answer` is a direct response to a task question; a `summary` is a synthesis of findings.

---

### 3. `patch_plan`

A proposed code change spanning one or more files.

| Field | Type | Description |
|---|---|---|
| `files` | `ArtifactFile[]` | Files touched, with additions/deletions counts |
| `diffBlocks` | `ArtifactDiffBlock[]` | Structured diff hunks per file |

**UI:** Compact file list in gallery card. Open button → InspectorDrawer renders diff view with syntax-highlighted hunks.

---

### 4. `diff`

A raw diff, not necessarily a patch plan — could be "what changed since last run."

Same extended fields as `patch_plan`. Shown with a diff icon.

---

### 5. `tool_bundle`

A record of a batch of tool calls that were executed together.

| Field | Type | Description |
|---|---|---|
| `toolIds` | `string[]` | IDs of tools in the bundle |

**UI:** Count + tool list in gallery card. Open button → InspectorDrawer shows tool list.

---

### 6. `approval_request` *(new)*

A record that the agent requested approval to take a higher-risk action.

| Field | Type | Description |
|---|---|---|
| `approvalData` | `ApprovalRequest` | Full approval request payload (see below) |

**`ApprovalRequest` shape:**

```typescript
{
  approvalId: string;
  runId: string;
  sessionKey: string;
  status: 'pending' | 'approved' | 'rejected' | 'modified' | 'expired';
  actionClass: ApprovalActionClass;
  toolId: string;
  proposedAction: {
    description: string;
    target?: string | null;
    payload?: Record<string, unknown>;
  };
  rationale: string | null;
  createdAt: string;
  resolvedAt: string | null;
  outcome: ApprovalOutcome | null;
}
```

**`ApprovalOutcome` shape:**

```typescript
{
  decision: 'approved' | 'rejected' | 'modified';
  modifiedPayload?: Record<string, unknown>;
  note?: string | null;
  decidedAt: string;
}
```

**`ApprovalActionClass` values:**

```typescript
| 'external_communication'
| 'filesystem_write'
| 'process_execution'
| 'network_side_effect'
| 'credential_or_sensitive_target'
```

**UI:** `ApprovalRequestCard` component. Interactive when `status === 'pending'` — shows Approve / Reject / Modify buttons. Shows decision state when resolved. Appears as an artifact card in Artifacts tab and as an in-line card in the Runtime tab.

---

### 7. `outbound_message` *(new)*

A record of an outbound message that the agent attempted to send.

| Field | Type | Description |
|---|---|---|
| `outboundData` | `OutboundMessageRecord` | Full outbound message record (see below) |

**`OutboundMessageRecord` shape:**

```typescript
{
  messageId: string;
  runId: string;
  sessionKey: string;
  platform: string;               // 'telegram', 'slack', etc.
  target: string;                 // 'telegram:@copenet_ops'
  targetDisplayName: string | null;
  messageText: string;
  status: OutboundMessageStatus;
  approvalId: string | null;      // Links to associated ApprovalRequest if one was required
  sentAt: string | null;
  failureReason: string | null;
  createdAt: string;
}
```

**`OutboundMessageStatus` values:**

```typescript
| 'drafted'          // Composed but not yet sent (e.g. awaiting approval)
| 'pending_approval' // Approval required, run paused
| 'approved'         // Operator approved, send in progress
| 'sent'             // Delivery confirmed by platform adapter
| 'failed'           // Send attempted but adapter returned error
```

**UI:** `OutboundMessageCard` component. Shows destination badge, message body, status, and timestamps. Links to associated approval request if one exists.

---

## Backend Emission Rules

| Artifact Kind | When Emitted | Who Emits |
|---|---|---|
| `summary` | Agent produces a synthesis | Harness artifact writer |
| `answer` | Agent produces a direct answer | Harness artifact writer |
| `patch_plan` | Agent produces a file-change plan | Harness artifact writer |
| `diff` | Diff computed by a diff tool | Harness artifact writer |
| `tool_bundle` | A batch of reads completes | Harness, when collapsing a read batch |
| `approval_request` | Harness intercepts gated tool call | Approval subsystem |
| `outbound_message` | `send_message` tool is called | send_message tool handler |

---

## UI Surface Mapping

| Artifact Kind | Artifacts Tab | Runtime Tab | Activity Tab | InspectorDrawer |
|---|---|---|---|---|
| `summary` | ✓ (text card) | — | — | Body view |
| `answer` | ✓ (text card) | — | — | Body view |
| `patch_plan` | ✓ (file list card) | — | — | Diff view |
| `diff` | ✓ (diff card) | — | — | Diff view |
| `tool_bundle` | ✓ (bundle card) | — | Call listed in activity | Tool list view |
| `approval_request` | ✓ (ApprovalRequestCard) | ✓ at top when pending | send_message call visible | — (card is self-contained) |
| `outbound_message` | ✓ (OutboundMessageCard) | — | tool_call entry | — (card is self-contained) |

---

## Frontend Component Map

| Artifact Kind | Component | File |
|---|---|---|
| `summary`, `answer` | `ArtifactCard` (generic) | `components/runtime/ArtifactsPanel.tsx` |
| `patch_plan`, `diff` | `ArtifactCard` + `DiffArtifactView` | `ArtifactsPanel.tsx` + `runtime/DiffArtifactView.tsx` |
| `tool_bundle` | `ArtifactCard` (generic) | `ArtifactsPanel.tsx` |
| `approval_request` | `ApprovalRequestCard` | `components/ApprovalRequestCard.tsx` |
| `outbound_message` | `OutboundMessageCard` | `components/OutboundMessageCard.tsx` |

---

## WebSocket Events

New events needed to stream approval and outbound artifacts to the frontend in real time:

```
event: 'artifact:approval_request'   payload: ApprovalRequest
event: 'artifact:outbound_message'   payload: OutboundMessageRecord
event: 'artifact:outbound_updated'   payload: { messageId, status, sentAt?, failureReason? }
event: 'approval:resolved'           payload: { approvalId, outcome: ApprovalOutcome }
event: 'run:paused'                  payload: { runId, reason: 'awaiting_approval', approvalId }
event: 'run:resumed'                 payload: { runId }
```

---

## Existing Artifact Infrastructure

CopeNet already has:
- `src/copenet/core/runtime/artifacts.py` — backend artifact store
- `tests/integration/test_tool_loop.py:733` — artifact emission tests
- `runtime/types.ts` — frontend type definitions
- `runtime/adapter.ts` — async resource hooks
- `runtime/mocks.ts` — demo data for all artifact kinds

The new approval and outbound kinds plug into the existing artifact system. No new storage model is needed — they are regular artifacts with a richer payload.

---

## Open Questions

1. **Artifact retention:** How long are artifacts kept? Currently session-scoped. Should approval history be kept even if the session is archived? Recommendation: yes — the audit value is high.
2. **Artifact ordering in the gallery:** Currently shown newest-first. Should `approval_request` artifacts be pinned to the top when `pending`? Current UI: yes, because `ArtifactsPanel` receives the array in emission order. The backend should emit approval artifacts at the front, or the frontend should sort by status.
3. **`patch_plan` + approval:** When an agent wants to write files (a `filesystem_write` action class), the approval request and the patch plan artifact are separate records. How do they link? Recommendation: `ApprovalRequest.proposedAction.payload` should include the `artifactId` of the associated patch plan.
4. **Multi-artifact runs:** A single run may produce several artifacts. The gallery should support filtering by kind. The "All kinds" filter button in `ArtifactsPanel` is already stubbed.
5. **Artifact promotion:** The "Promote" button is stubbed. Promoted artifacts should be pinned across sessions (useful for keeping an approved patch plan accessible). Defer to V2.
