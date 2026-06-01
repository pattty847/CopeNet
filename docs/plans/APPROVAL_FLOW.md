# Approval Flow — design + contract (Tier 1, part 2)

**Status:** spec ready for implementation. Frontend UI is ~80% built (mock-driven);
the gap is backend run-lifecycle pause/resume + the WS events and decide RPC that
drive the existing UI. Touches Codex-owned files (`runtime.py`, `tool_loop.py`,
`ws_server.py`) → coordinate before landing.

Author: Claude (frontend lane). Written after mapping both ends of the contract.

---

## Why

Full-access sessions can run `files.write` / `files.edit` (now with diffs) and
unrestricted shell. High-risk shell patterns already return
`policyDecision: "approval_required"` — but today that just returns a *blocked*
result and the model continues. A real harness pauses, asks the operator, and
resumes the exact proposed action on approval. This is the line between "safe but
dumb" (current) and "an agent you trust with write access" (goal).

## What already exists (don't rebuild)

**Backend**
- `shell.py::_approval_required()` returns a `ToolExecutionResult` with
  `policyDecision: "approval_required"` and the command in `output.command`/`target`.
- `turn_state.pending_approvals: dict` — declared, never populated. Reserved slot.
- The Responses tool loop (`tool_loop.py::run_with_responses_tools`) owns
  `working_messages: list` (the `input[]` array) and replays it each step — this is
  the state that must be persisted to resume.

**Frontend (~80%, all mock-driven — see `runtime/adapter.ts::useMockTransitions`)**
- `components/PausedRunBanner.tsx` — shows when `runPausedReason === 'awaiting_approval'`. Already rendered in `ChatWorkspace`.
- `components/RunTimeline.tsx` + `ApprovalRequestCard` — approve/reject/modify UI, rendered in `RightPanel` when `pendingApproval` is set.
- Store (`store/useAppStore.ts`): `pendingApproval`, `runPausedReason`,
  `approvalHistory`, `resolveApproval(approvalId, outcome)`, `setRunPausedReason`,
  `setRunTimeline`. All present.
- Types (`types/backend.ts`): `ApprovalRequest`, `ApprovalOutcome`,
  `ApprovalStatus`, `ApprovalActionClass`, `RunTimeline`. Match the mock data in
  `runtime/mocks.ts` exactly — that mock IS the intended contract.

`ApprovalRequest` shape the backend must emit:
```ts
{
  approvalId, runId, sessionKey,
  status: 'pending',
  actionClass: 'process_execution' | 'filesystem_write' | ...,
  toolId,                       // e.g. "shell.exec"
  proposedAction: { description, target?, payload? },  // payload = the exact args to re-run
  rationale: string | null,
  createdAt, resolvedAt: null, outcome: null,
}
```

## The hard part: pause/resume a streaming async run

`send_chat` runs the tool loop as an async generator and streams events over
`emit`. To pause:

1. When the loop hits an `approval_required` result, it must **stop** (not feed the
   blocked result back to the model), **persist** enough to resume, emit a paused
   event, and return cleanly — releasing the run but NOT marking it errored.
2. Resume happens in a **separate RPC call** with a fresh `emit` channel. It must
   reconstruct the loop from persisted state and continue.

**State to persist for resume** (keyed by `approvalId` → a durable record, likely a
new `PendingApprovalStore` or a field on the run record):
- `working_messages` (the full `input[]` array at pause time)
- the pending `function_call` (id, call_id, name, arguments) that needs approval
- `turn_id`, `decision_id`, `step_index`
- `session_key`, `run_id`, provider/model/instructions/reasoning (or re-derive from session)

This is the crux. The `input[]` array is JSON-serializable (it's what we POST), so
persistence is tractable — store it on a durable record, not just in memory.

## Proposed contract

### WS event: run paused
Emitted from `send_chat` when the loop pauses. New chat state value:
```json
{ "state": "awaiting_approval",
  "runId": "...", "sessionKey": "...",
  "approval": { ...ApprovalRequest... },
  "timeline": { ...RunTimeline... } }
```
Frontend handler (add to `wsClient.ts`): on `state === "awaiting_approval"` →
`setPendingApproval(approval)` + `setRunPausedReason('awaiting_approval')` +
`setRunTimeline(timeline)`. The run leaves `in_flight` (it's parked, not running).

### RPC: decide + resume
New method in `ws_server.py` / `rpc_dispatch.py`:
```
chat.decide_approval { approvalId, decision: 'approved'|'rejected'|'modified', modifiedPayload?, note? }
```
- **approved**: load the persisted state, execute the proposed command (bypassing the
  approval gate this once — pass an `approved_call_id` allowlist into the tool
  context), append its `function_call_output` to `working_messages`, re-enter
  `run_with_responses_tools` from the persisted array with a fresh emit, stream to
  completion.
- **rejected**: append a synthetic `function_call_output` saying the operator
  declined, re-enter the loop so the model can react/finish. (Or finalize with a
  "declined" note — simpler.)
- **modified**: same as approved but run `modifiedPayload` instead of the original args.

### WS event: resumed
On resume start, emit `{ state: "resumed", runId }` → frontend clears
`runPausedReason`/`runTimeline`. Then normal delta/tool/final events flow.

## Frontend wiring (my lane — small once the contract lands)
1. `wsClient.ts`: handle `awaiting_approval` + `resumed` states (set/clear store).
2. `wsClient.ts`: add `decideApproval(approvalId, outcome)` → sends `chat.decide_approval`.
3. Replace `useMockTransitions` calls in `RunTimeline`/`ApprovalRequestCard` with the
   real `decideApproval`. Keep `resolveApproval` for optimistic local update.
4. Delete the mock simulate* path (or gate behind a dev flag).

## Risks / care
- **Session semantics** (AGENTS.md): preserve `in_flight_run_id` locking. A paused run
  must release the lock cleanly so the session isn't stuck "busy"; resume re-acquires.
- **Abort path**: a pause must not race the abort handler. Resume after abort = no-op.
- **Idempotency cache**: resume is a new run-ish action; don't double-finalize.
- **Double execution**: the approved command must run exactly once — the
  `approved_call_id` allowlist must be single-use.
- Don't narrow `SessionStateRecord`; don't break `run_with_native_tools`.

## Suggested sequencing
1. `PendingApprovalStore` (durable, JSON) + persist on pause. (backend)
2. Pause path in `run_with_responses_tools` + `send_chat` emit. (backend, Codex-owned)
3. `chat.decide_approval` RPC + resume entry. (backend, Codex-owned)
4. Frontend wiring (4 small steps above). (Claude lane)
5. End-to-end: full-access session, trigger a high-risk shell pattern, approve, watch it run.

**Recommendation:** steps 1–3 are Codex's run-lifecycle territory and should be his
or paired with him. Step 4 is mine and is ~an hour once 1–3 land. The diff feature
(Tier 1 part 1) is already shipped and verified independent of this.
