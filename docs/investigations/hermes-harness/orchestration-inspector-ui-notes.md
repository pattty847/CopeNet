# Orchestration Run Inspector — CopeNet UI Design Notes

## Summary

This document describes the UX surface for inspecting `orchestration_run` artifacts — the frontend prototype for a future Hermes-style `execute_code` / bounded multi-tool orchestration tool. No backend behavior is implemented yet; this is a design + type scaffolding pass.

---

## Background: Why This Exists

Hermes's `execute_code` tool compresses multi-step tool workflows into a single bounded scripted run. It is framed as the right tool when:
- a task needs 3+ tool calls
- results need filtering before hitting prompt context
- the logic needs branching, looping, or retries

CopeNet does not have this tool yet. The design sequencing from the Telegram/Approvals/Orchestration plan (Phase D) says: add orchestration only after approvals exist.

But we can prototype the **inspector UX now** so when the backend tool ships, the operator surfaces are already designed and typed.

---

## `orchestration_run` Artifact Kind

An orchestration run is a first-class artifact, like `approval_request` or `outbound_message`. It appears in the Artifacts panel and provides full inspection without needing raw logs.

### Shape

```typescript
interface OrchestrationRun {
  orchestrationId: string;
  runId: string;
  sessionKey: string;
  status: OrchestrationRunStatus;
  goal: string;                        // operator-readable goal description
  scriptSummary: string | null;        // what the script logic does
  toolsUsed: OrchestrationToolInvocation[];
  toolBudget: number;                  // max tool calls
  toolCallsUsed: number;               // actual calls made
  timeoutSeconds: number;
  durationMs: number | null;
  outputSummary: string | null;
  relatedArtifactIds: string[];
  approvalRequired: boolean;
  approvalId: string | null;
  startedAt: string;
  completedAt: string | null;
  error: string | null;
}

interface OrchestrationToolInvocation {
  toolId: string;
  count: number;
  summary: string;   // e.g. "probe output paths → 12 files found"
}

type OrchestrationRunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'approval_required'
  | 'cancelled';
```

### Status transitions

```
pending → running → completed
                  → failed
                  → approval_required → [operator decides] → running (if approved)
                                                           → cancelled (if rejected)
          → cancelled (by operator or timeout)
```

---

## `OrchestrationRunCard` Component

File: `src/copenet/host/frontend/src/components/OrchestrationRunCard.tsx`

### Collapsed view (gallery card)

```
┌──────────────────────────────────────────────┐
│ ⚡ [CPU] Orchestration Run                    │
│   Completed · 4.2s                   18m ago  │
│   Probe analysis: grounding distribution      │
│   ⚡ 8 tool calls  🛡 Auto-run                │
└──────────────────────────────────────────────┘
```

### Expanded view

```
┌──────────────────────────────────────────────┐
│ ⚡ [CPU] Orchestration Run                    │
│   Completed · 4.2s                   18m ago  │
│   Probe analysis: grounding distribution      │
│   ⚡ 8 tool calls  🛡 Auto-run                │
│                                               │
│ SCRIPT LOGIC                                  │
│   Search for probe output files, read each,   │
│   tally grounded vs listing-only outcomes.    │
│                                               │
│ TOOL BUDGET ▓▓▓▓▓▓▓▓░░  8/10                │
│   timeout: 30s                                │
│                                               │
│ TOOLS USED                                    │
│   ⚙ files.search × 3  probe output paths →12 │
│   ⚙ files.read × 4    probe run data → 412ln │
│   ⚙ context.prepare ×1  session/repo overview│
│                                               │
│ OUTPUT                                        │
│   3 of 8 repo-explain probes are now          │
│   grounded via files.read. 5 others remain    │
│   listing-only. patch-plan: 2/4 grounded.     │
│                                               │
│ RELATED ARTIFACTS                             │
│   🔗 a-summary-1                              │
│                                               │
│ id: e7a1b2c3 · Bounded run · safe tools only  │
└──────────────────────────────────────────────┘
```

### Key UX details

- **Tool budget bar** is a visual indicator showing `toolCallsUsed / toolBudget`. Turns orange above 70%, red above 90%. Communicates "this was a thrifty run" vs "this run hit the ceiling."
- **`approvalRequired: false`** → "Auto-run" badge (ShieldCheck, green). **`approvalRequired: true`** → "Needed approval" badge (ShieldAlert, accent). This tells the operator whether this orchestration step went through the approval flow.
- **`error`** field renders as a red inline box — the canonical failure record, visible without reading logs.
- **`relatedArtifactIds`** are shown as monospace badges so the operator can cross-reference with the Artifacts tab.
- **Safety footer:** "Bounded run · safe helper tools only" — a subtle design signal that orchestration runs are constrained to pre-approved tools, not arbitrary execution.

---

## Suggested Backend Design (deferred)

When CopeNet adds a bounded orchestration tool (`execute_code`-style), it should:

1. **Expose only the currently-enabled helper set** in the schema description — not all tools. (Learned from Hermes `execute_code`'s dynamic schema shaping.)
2. **Clearly document the execution environment** — temp dir vs working dir, filesystem access scope.
3. **Enforce a tool call budget** (`toolBudget`) and time limit (`timeoutSeconds`). Both hard-wired in the tool descriptor.
4. **Emit an `orchestration_run` artifact** when the script starts (status: `running`) and update it on completion (status: `completed` or `failed`).
5. **Classify the run's action class** — if it touches any approval-required action (e.g. `send_message`), upgrade the orchestration run to `approval_required` and emit an `approval_request` artifact before executing that step.
6. **Link the run to its parent run** — the `orchestration_run` artifact carries the `runId` of the orchestrator turn that invoked it.

---

## Suggested Use Cases (first-pass framing)

These are the cases where a bounded orchestration tool would most reduce turn-by-turn fragility in CopeNet:

| Use case | Why orchestration helps |
|---|---|
| Scan many probe output files, count grounded successes | Avoids 8+ sequential tool calls; model can't keep state across turns |
| Process a list of artifacts before summarizing | Filtering before hitting prompt context; matches Hermes's motivation |
| Retry a structured file-search + read + verify workflow | Gives the model a retry loop without burning conversation turns |
| Generate a draft from multiple artifact reads | Combines tool results into one context-rich synthesis pass |

Non-goals for V1 orchestration:
- Writing to the filesystem
- Calling external APIs
- Installing packages
- Long-running background work

---

## Operator Visibility Goals

The operator should be able to answer:
- What goal was the orchestration trying to accomplish?
- How many tools did it use (and was that within budget)?
- What did it produce?
- Did it require approval for any of its steps?
- Did it succeed or fail, and if it failed, why?

All five questions are answered by `OrchestrationRunCard` from the `OrchestrationRun` artifact shape.

---

## Open Questions

1. **Orchestration approval granularity:** Should the whole orchestration run require one approval upfront, or should individual steps within the script be individually approvable? Leaning toward: the harness intercepts the script at the first gated step, not before. This matches how Hermes approval works.

2. **Script inspection:** Should the operator be able to see the actual script code? Current answer: no — the operator sees the `goal` and `scriptSummary` fields, not raw code. Raw code is in the trace. This avoids surfacing implementation details but may limit operator trust.

3. **Re-run after modification:** If the operator rejects an orchestration run mid-step, can the agent retry with a modified approach? Current assumption: the agent handles rejection as a normal tool error and decides how to proceed.

4. **Tool call quota vs. action count:** `toolCallsUsed` counts distinct tool invocations. Batched reads (e.g. 4 `files.read` calls) each count as one. This matches the most natural mental model.

5. **Nested orchestration:** Can an orchestration run call another orchestration run? For V1, no. Flag as a hard constraint to add to the tool description.

---

*Generated: 2026-04-28. This is a design prototype — no backend orchestration tool exists yet.*
