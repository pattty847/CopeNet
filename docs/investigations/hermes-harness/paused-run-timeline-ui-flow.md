# Paused Run Timeline — CopeNet UI Design Spec

## Summary

The Run Timeline is a vertical lifecycle view that shows the operator exactly what happened in a run, why it's paused, and what the agent is waiting on. It is shown in the Runtime tab when a run is in the `awaiting_approval` paused state.

---

## Motivation

When a run pauses for approval, the operator needs to answer three questions before deciding:

1. **Why is this run paused?** — What action did the agent propose, and what is its action class?
2. **What happened before this point?** — What tools did the agent run, and what did it find?
3. **What will happen if I approve / reject?** — What side effect follows from the decision?

The `ApprovalRequestCard` answers questions 1 and 3 well. The `RunTimeline` answers question 2: it gives the operator a complete trace of the run's tool call history, so they can evaluate the approval decision with full context.

---

## Lifecycle State Machine

```
run_started
    │
    ├── tool_called (files.read, context.prepare, etc.)
    │       └── tool_result (ok / error)
    │
    ├── tool_called (files.read ...)
    │       └── tool_result
    │
    │  ... (repeated per tool step) ...
    │
    ├── tool_called (send_message)   ← gated tool
    │       │
    │       ▼
    ╔═══════════════════╗
    ║ approval_requested ║  ← RUN PAUSED HERE
    ╚═══════════════════╝
    │
    ├── [operator decides]
    │
    ├── decision_made (approved / rejected / modified)
    │       │
    │       ▼
    ├── run_resumed
    │       │
    │       ▼
    ├── tool_result (tool executed with decision outcome)
    │
    └── run_completed / run_failed
```

---

## Event Kinds

| Kind | When | Icon | Tone |
|---|---|---|---|
| `run_started` | Run begins | ▶ Play | success |
| `tool_called` | Agent calls a tool | ⚙ Settings2 | muted |
| `tool_result` | Tool returns a result | ✓ Check | success / error |
| `approval_requested` | Harness intercepts gated tool | ⏸ Pause | error (red) |
| `decision_made` | Operator resolves | 🛡 ShieldCheck | success |
| `run_resumed` | Run continues | ▶ Play | success |
| `run_completed` | Run finishes normally | ✓ CheckCircle2 | success |
| `run_failed` | Run terminates with error | ✗ AlertCircle | error |
| `note` | Harness-generated annotation | → ExternalLink | muted |

---

## UI Design

### When a run is paused

```
┌──────────────────────────────────────────────┐
│ ⚡ Run Timeline   run_2b1a···             paused 45s ago │
├──────────────────────────────────────────────┤
│ ┌────────────────────────────────────────┐   │
│ │ ⏸ Run is paused                        │   │
│ │   Waiting for your approval decision   │   │
│ │   [Approve] [Reject] [Full view →]     │   │
│ └────────────────────────────────────────┘   │
│                                              │
│ ○  11:23:01  ▶ Run started                   │
│ │             Investigate provider init...   │
│ │                                            │
│ ○  11:25:14  ⚙ files.read_file               │
│ │             runtime.py (420 lines)  14ms   │
│ │                                            │
│ ○  11:25:37  ⚙ files.grep                    │
│ │             plan_turn usages → 7 hits 23ms │
│ │                                            │
│ ○  11:30:02  ⚙ trace.read                    │
│ │             run 2b1a-9e4f events    31ms   │
│ │                                            │
│ ○  11:34:58  ⚙ code.edit                     │
│ │             Drafted 3-file patch plan 182ms│
│ │                                            │
│ ●  11:35:45  ⏸ send_message → approval req'd │
│ │   ╔════════════════════════════════════╗  │
│ │   ║ APPROVAL REQUIRED                  ║  │
│ │   ║ Agent wants to send to @copenet_ops║  │
│ │   ║ [Open Approvals →]                 ║  │
│ │   ╚════════════════════════════════════╝  │
│                                              │
│ ⏱  11:35:45  Waiting for decision…           │
└──────────────────────────────────────────────┘
```

### When no run is paused

```
┌──────────────────────────────────────────────┐
│ ⚡ Run Timeline                              │
│                                              │
│   No run paused                              │
│   Timeline appears when a run is paused      │
│   for approval.                              │
│                                              │
│   [Simulate paused run →]  ← demo link      │
└──────────────────────────────────────────────┘
```

---

## `RunTimeline` Component

File: `src/copenet/host/frontend/src/components/RunTimeline.tsx`

### Props

```typescript
interface RunTimelineProps {
  sessionKey: string | null;
}
```

### Data source

The component calls `useRunTimeline(sessionKey)` from the adapter. This hook:
- Returns `null` when no run is paused
- Seeds from `getMockRunTimeline()` when `runPausedReason === 'awaiting_approval'` and the store has no real timeline yet
- When the backend ships, this hook will call the actual run-record endpoint to reconstruct the timeline from tool step records

### Spine rendering

Each event gets a dot on the vertical spine. The spine line between dots is colored by the event type:
- Default: `border-operator-border` (grey)
- `approval_requested`: `bg-operator-error/30` (red, above the pause point)

The `approval_requested` dot is ring-pulsed to draw attention.

---

## `RunTimeline` Data Types

```typescript
interface RunTimeline {
  runId: string;
  sessionKey: string;
  pausedAt: string | null;     // ISO — when run paused
  resumedAt: string | null;    // ISO — when run resumed (null if still paused)
  events: RunTimelineEvent[];
}

interface RunTimelineEvent {
  id: string;
  kind: RunTimelineEventKind;
  at: string;                  // ISO timestamp
  label: string;               // short label
  detail?: string | null;      // expandable one-line detail
  status: 'ok' | 'pending' | 'paused' | 'error' | 'skipped';
  toolId?: string | null;
  linkedApprovalId?: string | null;
  durationMs?: number | null;
}
```

---

## Placement

The `RunTimeline` renders inside the **Runtime tab** of the Inspector, immediately below the `ApprovalRequestCard` section, only when `pendingApproval` is non-null.

This keeps the operator's context together:
1. `ApprovalRequestCard` — what the agent wants to do
2. `RunTimeline` — what the agent did to get here

---

## Backend Dependencies

| Item | Required field/event |
|---|---|
| Timeline events | Run record `toolSteps` array + timestamps; or a dedicated `run.getTimeline(runId)` RPC |
| Paused-at timestamp | `run:paused` event `{ runId, pausedAt }` |
| Resumed-at timestamp | `run:resumed` event `{ runId, resumedAt }` |
| Tool durations | Each `toolStep` should include `durationMs` |

**Current state:** The frontend builds the timeline from `getMockRunTimeline()` mock data. The real timeline will be assembled from the `SessionRunRecord.toolSteps` array, enriched with timing data once the backend adds `durationMs` to each step.

---

## Open Questions

1. **Timeline granularity:** Should each individual tool call get its own event row, or should batches be collapsed? For V1, individual rows are cleaner. Batching can be added as a UX improvement later.

2. **Pre-approval context:** The timeline only shows events from the current run. If the operator wants to understand why the agent made this request (prior sessions, prior runs), they need the session transcript. Consider linking the timeline to the chat transcript view.

3. **Timeline after approval:** Once the operator approves or rejects, the timeline should continue to update (showing `decision_made`, `run_resumed`, `run_completed`). This requires the backend to push timeline events live, not just on-load.

4. **Multiple paused runs:** If two sessions are simultaneously paused, each session's timeline is independent. The current model handles this correctly since `useRunTimeline` is keyed by `sessionKey`.

5. **Long runs:** A run with 50+ tool calls would produce a very long timeline. Consider collapsing tool_called events into read-batches (matching the `RunActivity` batching) for cleaner display.

---

*Generated: 2026-04-28.*
