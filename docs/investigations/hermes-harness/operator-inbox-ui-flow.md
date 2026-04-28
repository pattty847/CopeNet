# Operator Inbox / Action Center — CopeNet UI Design Spec

## Summary

The Operator Action Center is the primary "what needs my attention right now?" surface for a CopeNet operator. It aggregates urgent items — paused runs, pending approvals, failed sends — into a single priority-ordered view so the operator doesn't have to scan multiple tabs to understand the system state.

---

## Design Goal

Make the operator's first question — *"is anything blocked?"* — answerable in under 2 seconds without opening any modals or switching tabs.

Secondary goal: show enough context inline that the operator can approve or reject a pending action without leaving the inbox view.

---

## Priority Model

Items are bucketed into three priority tiers:

| Priority | Kind | Signal |
|---|---|---|
| `urgent` | `paused_run` | A live run is suspended, waiting for the operator |
| `attention` | `pending_approval` | An approval is pending but no run is currently blocked |
| `info` | `resolved_approval`, `sent_message` | History — recently decided or delivered |

Within each tier, items are ordered newest-first.

This ordering is intentional:
- **Paused runs** are the most disruptive state — the agent is doing nothing until the operator acts.
- **Pending approvals** matter but may not block the current run (e.g. approval requested but run not yet paused, or multiple runs in different sessions).
- **History** is informational — useful for audit and review but requires no action.

---

## Component: `OperatorActionCenter`

File: `src/copenet/host/frontend/src/components/OperatorActionCenter.tsx`

### Layout

```
┌──────────────────────────────────────────┐
│ ● Action Center          [2 need action] │
├──────────────────────────────────────────┤
│ Demo: simulate paused run          [Pause]│  ← demo-only strip
├──────────────────────────────────────────┤
│                                          │
│ RUN PAUSED · 1                           │
│ ┌────────────────────────────────────┐  │
│ │ ⏸ Run paused — action required     │  │  ← urgent, auto-expanded
│ │   send_message → @copenet_ops       │  │
│ │   45s ago                           │  │
│ │   ▼ message text (expanded)         │  │
│ │   ▼ why: user asked to notify       │  │
│ │   [Approve] [Reject] [Detail →]     │  │
│ └────────────────────────────────────┘  │
│                                          │
│ ✓ ALL CLEAR (if no pending)              │
│                                          │
│ ▾ RECENT · 3                             │
│   ✓ Approved · 30m ago                   │
│   ✎ Modified · 73m ago                   │
│   ✗ Rejected · 5h ago                    │
└──────────────────────────────────────────┘
```

### Quick actions

The `InboxItemRow` component shows inline approve/reject buttons for urgent and attention items. The buttons call `simulateApprove` / `simulateReject` from `useMockTransitions`. When the backend ships, these call `wsClient.resolveApproval()`.

A "Detail →" button navigates the right panel to the `approvals` tab, where the full `ApprovalQueuePanel` renders.

### All-clear state

When there are no urgent or attention items, a green `AllClearBanner` is shown. This is the desired steady-state. The inbox should feel _quiet_ when nothing needs attention.

---

## Placement

The inbox lives as the **first tab** of the right panel Inspector (`inbox` tab, icon: `Inbox`).

The tab shows a badge with the count of urgent + attention items. When the count is 0, the badge is hidden.

```
[Inbox ①] [Runtime] [Artifacts] [Activity] [Approvals ①]
```

---

## Data Model: `InboxItem`

```typescript
interface InboxItem {
  id: string;
  priority: 'urgent' | 'attention' | 'info';
  kind: 'paused_run' | 'pending_approval' | 'failed_send' | 'resolved_approval' | 'sent_message';
  title: string;
  subtitle: string;
  createdAt: string;       // ISO — used for sorting within tier
  sessionKey: string;
  runId: string | null;
  // At most one linked data field:
  approvalData?: ApprovalRequest;
  outboundData?: OutboundMessageRecord;
}
```

`InboxItem` is a derived/computed type. It is not persisted on the backend — it is assembled from approval history and outbound message records by `buildInboxItems()` in `mocks.ts` (and eventually by the backend adapter).

---

## Frontend Wiring

| Hook | Where called | Returns |
|---|---|---|
| `useInboxItems(sessionKey)` | `OperatorActionCenter`, `RightPanel` badge | `InboxItem[]` |
| `useMockTransitions()` | `OperatorActionCenter` (approve/reject buttons) | simulation fns |

`useInboxItems` aggregates `useApprovalHistory` (from the store) and `runPausedReason` (from the store) into a sorted `InboxItem[]`. When the backend ships, a real aggregation endpoint (or derived from `approval.list()` + `outbound.list()`) replaces `buildInboxItems`.

---

## Backend Dependencies

| Item | Status | Required field/event |
|---|---|---|
| Paused run item | Backend needed | `run:paused` WebSocket event |
| Pending approvals | Backend needed | `approval:requested` event + `approval.list()` RPC |
| Resolved approvals | Backend needed | `approval:resolved` event |
| Failed sends | Future | `artifact:outbound_updated` event with `status: 'failed'` |
| Sent messages | Future | `artifact:outbound_message` event with `status: 'sent'` |

---

## Open Questions

1. **Cross-session inbox:** Should the inbox aggregate items from all sessions, or only the active session? Current assumption: only the active session. V2: add a global inbox surface.

2. **Operator notifications:** If the operator is away from the UI when a run pauses, how do they find out? Current answer: polling the UI. V2: browser push notifications or a Telegram notification back to the operator.

3. **Inbox persistence:** If the operator reloads, the inbox should restore from the server. This requires `approval.list(sessionKey)` on reconnect (already in the contract checklist).

4. **`failed_send` items:** Not yet wired — these need `OutboundMessageRecord` with `status: 'failed'` available as a queryable list.

5. **Stale paused-run badge:** If the run resumes (because approval was resolved from the Approvals tab), the inbox badge should decrement immediately. This works correctly today because the badge derives from live store state.

---

*Generated: 2026-04-28. Update when backend fields are confirmed.*
