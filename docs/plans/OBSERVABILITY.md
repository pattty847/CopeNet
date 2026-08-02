# Observability Run Inspector

## Product goal

Observability should explain a model run from the operator's point of view: what
CopeNet sent, which tools the model could see, which tools it called, what those
tools returned, and which reasoning signal the provider actually exposed. It
must not imply access to private chain-of-thought when a provider only returns a
summary—or no reasoning channel at all.

## Delivered surface

The Observability workspace is a run-first, master-detail inspector:

- recent durable runs across active sessions
- chronological user, reasoning, tool, and assistant events
- exact tool arguments plus retained result previews or artifacts
- debug-only model input snapshots with effective instructions, messages, tool
  manifest, harness decision, transport, and reasoning configuration
- raw per-run JSONL trace events
- provider, model, duration, status, tool count, and debug-capture provenance

The Debug capture switch applies to subsequent runs and persists in
`~/.copenet/observability.json` (or under `COPNET_DATA_DIR`). `COPNET_TRACE=1`
remains a startup-compatible fallback, but the persisted operator setting is the
canonical runtime control once it exists.

## Data flow

```text
Observability UI
  ├─ observability.settings.get/update
  └─ observability.run.get(sessionKey, runId)
       └─ Orchestrator ObservabilityFacade
            ├─ RunStore durable record
            ├─ transcript entries stamped with runId
            ├─ ArtifactStore records stamped with runId
            └─ logs/runs/<runId>.jsonl
```

Standard run records remain lightweight. Debug capture adds a
`model_input_snapshot` trace event at the harness boundary, after CopeNet has
resolved the actual provider transport. This keeps prompted-tool pretext,
Responses instructions, chat messages, and offered tool schemas aligned with
what the provider received.

## Reasoning provenance

Reasoning is normalized without flattening its source:

| Provider lane | Current evidence | Inspector label |
| --- | --- | --- |
| OpenAI Codex Responses | reasoning summary delta/item | `Reasoning summary` |
| OpenAI raw reasoning-text event, if emitted | raw reasoning text | `Raw reasoning` |
| Claude CLI | no reasoning channel in CLI stream | no reasoning section |
| LM Studio / Ollama | model- and template-dependent; pending local testing | derived from runtime event metadata |

The OpenAI probe matrix tested medium/auto, high/detailed, and tool-enabled
variants. All returned short reasoning summaries. Increasing effort and summary
detail did not materially expand them, which indicates upstream summary behavior
rather than CopeNet truncation. Raw response fixtures from probes stay under the
ignored `tmp/` tree and are never committed.

## Privacy and security

- Debug capture is off by default because prompts, history, tool schemas, and
  tool output can contain sensitive operator or repository data.
- Trace serialization recursively redacts credential-shaped keys such as
  authorization, cookies, passwords, secrets, and access/refresh/API tokens.
- Traces remain local and are not sent to an analytics service.
- Existing runs cannot be retroactively upgraded to debug captures.
- Screenshots and fixtures must use synthetic sessions and prompts.

## Phase 2 plan — run transparency

Goal: **you should be able to look at any turn and see exactly what the model was given,
what it could call, what it did call, and why it stopped** — without leaving the
conversation, and without having predicted in advance that you would want to know.

### What we found

There are currently **four** renderings of the same run data:

| Surface | Scope | Where |
| --- | --- | --- |
| `LiveToolFeed` | the run in flight | right panel |
| `RunActivityPanel` | the **last** run only | right panel |
| `ToolTraceCard` | one message's tool execution | inline in `MessageBubble` |
| `RunInspector` | any run, any session | Observability page |

So the Observability inspector is not redundant with Agents by accident — it is the
fourth implementation of one idea. Two concrete symptoms:

- `useRunActivity` calls `listSessionRuns(sessionKey, 10)` and then renders
  `runs[runs.length - 1]`, discarding nine runs it already fetched. Per-turn history is
  paid for and thrown away.
- Nothing outside Agents produces runs. Market, Fleet, and Messaging create no
  `RunRecord`s, so "runs with no chat thread" is an empty set today and cannot justify a
  separate viewer on its own.

### The split

> **Agents** answers *"what happened in this turn?"* — you are already here when you
> notice something is off.
> **Observability** answers *"what happens across all my turns?"* — questions a single
> thread structurally cannot express.
> **One component** renders per-turn internals, mounted in both.

What genuinely belongs only in Observability, because it is a query across runs rather
than a view of one:

- every run where a tool was **blocked by policy**, across all sessions
- registered tools that have **never once been called** — the strongest available signal
  that a tool description is wrong
- runs whose context was **trimmed** (`tool_loop_input_trimmed` fires today and nothing
  surfaces it)
- **model comparison**: same prompt, different model or Access, diffed on manifest, tool
  behavior, latency, and terminal reason
- error rates, retention, purge

Those become answerable only once tracing is always on — which is workstream 1.

### Workstream 1 — always-on lifecycle tracing

`runtime.py` builds the writer with `enabled=debug_capture` **and** `debug=debug_capture`
from the same flag, so with Debug capture off a run writes no trace at all. Measured:
672 runs, 341 trace files.

Split the tiers:

- **Lifecycle (always on):** run/session identity, resolved model, harness plan
  (`willAttemptToolLoop`, `promptedToolUse`, offered tool ids), tool requested / executed
  / blocked with tool id and status, token estimates, trim events, terminal reason,
  timings. No prompt text, no tool arguments, no tool results — cheap and not sensitive.
- **Debug capture (opt-in, unchanged):** model input snapshot, effective instructions,
  message history, tool arguments and results, reasoning payloads.

Keep the existing redaction on both tiers. Retention matters once this is unconditional,
so pair it with a size cap and a purge control rather than shipping an unbounded writer.

### Workstream 2 — one per-turn internals component

Extract the run-internals view used by `RunInspector` into a shared component with three
mount points: live (in-flight), in-thread (any turn), cross-session (Observability).
`RunActivityPanel`'s grouped-breadcrumb design is the right visual language and should
survive — it is already tuned not to overwhelm.

### Workstream 3 — emit the provider-resolved model

See "Next work" item 0 below. Prerequisite for model comparison in workstream 4.

### Workstream 4 — cross-run queries

The Observability list becomes session-grouped and expandable to turns (scanning 672 flat
runs is unusable regardless of anything else), plus the saved queries listed above.

## Agents thread UX

The constraint: **insight without obstruction.** The thread is for working; the internals
must be available at a glance and invisible otherwise.

- Every assistant turn carries **one collapsed line** beneath it, muted by default:
  `model · duration · 4 tools · 12k ctx`. Color appears only when something deserves
  attention — a policy block, a failure, a trimmed context.
- Clicking that line expands **in place**, not into a side panel, because the question is
  about *this* message. Four sections, in the order a person actually debugs:
  1. **What it saw** — prompt blocks assembled with sizes, and the tool manifest with each
     tool's visibility plus the reason any were withheld.
  2. **What it did** — calls in order, arguments, results, artifacts.
  3. **Why it stopped** — terminal reason in plain language.
  4. **Raw trace** — the escape hatch, collapsed.
- A one-line **verdict** at the top when the answer is already knowable, e.g. *"No tool
  loop attempted: promptedToolUse = false"*. Per this repo's own triage order that is the
  single most common confusion, and it should never require reading JSONL.
- The right drawer stops showing only the last run and becomes the **session-level** view:
  every turn, scannable, with the same expansion.

Nothing here may shift layout while a run streams; expansion is user-initiated only.

### Trace reset

Existing traces are mostly from testing and predate the tier split, so they carry no
lifecycle events and cannot be backfilled. Purge `~/.copenet/logs/runs/` when workstream 1
lands and start clean rather than maintaining two shapes.

### Verification

- Unit: tier gating (lifecycle events present with Debug capture off, payloads absent),
  redaction on both tiers, session-grouped list shaping.
- Live: `uv run copenet chat send` against the standing probe session with Debug capture
  off, then on; confirm the lifecycle skeleton exists in both and payloads only in the
  second.
- Browser: expand a turn in-thread, confirm no layout shift during a live run.

## Next work

0. **Record the provider-resolved model.** Both the trace writer and `RunRecord` are
   stamped with `request.model`, which is the model *requested*, not the one that
   answered. Measured 2026-08-01: **95 of 334 local traces (28%) carry a null model**,
   including recent `openai-codex` runs — so more than a quarter of the run history
   cannot tell you what produced it, which also undercuts the per-turn auditability that
   mid-session model switching depends on. No provider currently reports the model it
   used; they only send it in the request. Closing this means each adapter emitting the
   resolved model (OpenAI Responses returns `response.model`; LM Studio and Ollama return
   `model` in the response body), the four tool loops forwarding that meta event rather
   than swallowing it, and the orchestrator updating both the trace writer and the run
   record. It touches the provider contract, so scope it deliberately rather than in
   passing.
1. Test LM Studio and Ollama models that explicitly advertise a thinking stream.
2. Add side-by-side run comparison for prompt, tool, latency, and reasoning
   differences.
3. Add derived diagnostics (malformed tool attempts, repeated calls, policy
   blocks, tool-result utilization) without interpreting prose as control flow.
4. Add retention controls and an explicit local trace purge workflow.
5. Add exportable, sanitized run bundles for cross-provider evaluation.
