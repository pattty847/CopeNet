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
`~/.copenet/sessions/observability.json` (the settings file sits beside the session
store, not at the data-dir root; under `COPNET_DATA_DIR` it follows the same
relative path). `COPNET_TRACE=1` remains a startup-compatible fallback, but the
persisted operator setting is the canonical runtime control once it exists.

Inspector tabs, since workstream 2: **Internals** (the shared per-turn view, and
the default), **Timeline**, **Model input**, **Raw trace**. The old standalone
Tools tab is now the "What it did" section inside Internals.

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

### Workstream 1 — always-on lifecycle tracing — **shipped 2026-08-02**

`runtime.py` built the writer with `enabled=debug_capture` **and** `debug=debug_capture`
from the same flag, so with Debug capture off a run wrote no trace at all. Measured before
the fix: 672 runs, 341 trace files.

Every row now carries a `tier`:

- **Lifecycle (always on):** run/session identity, provider and model, harness plan
  (`willAttemptToolLoop`, `promptedToolUse`, offered tool ids), tool requested / executed
  / blocked with tool id and status, token estimates, trim events, terminal reason,
  timings. No prompt text, no message history, no reasoning content, no tool result bodies.
- **Debug capture (opt-in, unchanged):** `model_input_snapshot`, `run_input`,
  `tool_arguments`, `tool_result_body`, reasoning content.

Three design points worth keeping:

**Arguments are digested, not dropped.** A `shell.exec` command or an `files.rg` pattern
*is* the trace — omitting it would make the lifecycle tier useless for the question
Patrick actually asked ("are the models getting the context on the tools?"). `argument_digest`
in `tool_loop_common.py` passes short scalars through verbatim and replaces anything over
`ARGUMENT_VALUE_CHAR_LIMIT` (400) with `{"chars": n, "omitted": true}`, so a `files.write`
body never lands in the always-on tier. The full arguments go to `tool_arguments` on the
debug tier. Note this changes no disclosure surface: `RunRecord.toolSteps` already persists
full arguments and result previews unconditionally, deliberately.

**The writer owns the tier, not the call site.** The harness tool loops are handed a bare
`trace(event, payload)` callable rather than the writer, so they cannot reach
`record_debug` directly. `DEBUG_TIER_EVENTS` in `core/tracing/__init__.py` is the explicit
table that routes those events to the debug tier from inside `record()`. Threading a
second callable through three loops plus the registry would have been the alternative;
this keeps one named list instead of a parameter in six signatures.

**`debugCaptured` had to be redefined.** It was `bool(events)`, which now reports every
run as debug-captured. It is `any(event.tier == "debug")`, and the detail payload gained
`lifecycleCaptured` so `RunInspector` can show three states — `debug captured`,
`lifecycle traced`, `no trace` (purged, or pre-dating always-on tracing).

Retention: `RunTraceWriter` caps one run at 8 MiB (`trace_truncated` row, then silence),
`ObservabilityStore.prune_traces()` runs oldest-first at orchestrator startup against a
256 MiB / 2,000-file ceiling, and `observability.traces.purge` backs a **Purge traces**
button beside the trace-storage readout in the Observability header. Run records,
transcripts, and artifacts are untouched by any of it.

Verified live: with Debug capture off, a tool-calling run wrote 26 lifecycle events
(16 KB) including `tool_requested` with the real ripgrep pattern and a `tool_blocked`
carrying its policy reason, and zero debug rows. With it on, the same shape plus
`run_input`, `model_input_snapshot`, `tool_arguments`, and `tool_result_body`. Purge took
337 traces / 7.9 MB to zero and flipped the open run's badge to `no trace` while its run
record stayed intact.

### Workstream 2 — one per-turn internals component — **in-thread + Observability shipped 2026-08-02**

`runtime/runInternals.ts` is the single derivation — a `SessionRunRecord` plus, optionally,
that run's lifecycle trace becomes a collapsed stat line and the four sections. Pure and
React-free so verdicts and tone are unit-testable (`tests/runInternals.test.ts`).

Rendered by `components/runtime/RunInternals.tsx` at two of the three mount points:
in-thread under every assistant turn (`TurnInternals`, `operator-*` palette) and in the
Observability inspector as its first tab (`shell-*`). `RunStepCard` and `internalsPalette`
are extracted so a tool call looks the same in both; the palette is an explicit class table
because Tailwind cannot see interpolated class names. `RunInspector`'s local
`Preview`/`ToolStepCard` are gone and its standalone Tools tab is now the shared
"What it did" — 75 lines deleted there.

`runtime/runIndex.ts` collapses the data path: one `sessions.runs` call per session, shared
by every turn via a module-level promise cache keyed by (sessionKey, revision), and the
trace fetched only on expand. This also retires `useRunActivity`'s fetch-ten-render-one.

Three corrections the honest version required:

- **`inputTokenEstimate` charges the messages array only.** Labeling it "input tokens" let
  a turn read as *5 tokens* while the model was handed an 11.5k-char system prompt and
  21.5k of tool schemas. The line now says `731 msg`; the expanded row says
  "history only — prompt and schemas are above", with those sizes as their own rows.
- **Blocked ≠ failed.** A block is a policy decision the operator may want to change; a
  failure is a bug. The old card collapsed both to a red X. `isBlockedStep` / `isFailedStep`
  split them, with a shield vs an X and separate badges.
- **"Not fetched yet" ≠ "no trace".** The first render of an expanded turn printed
  "No trace for this run — it predates always-on tracing, or was purged" as fact while the
  fetch was still in flight. Hence `TraceStatus`.

Layout-shift rule verified live rather than argued: sampling the DOM every 200 ms through a
real composer send, the streaming turn carries no line (12 bubbles / 5 lines) and the line
appears only after the run lands (6 lines at +1.0 s). Note the honest tradeoff — the line
*appearing* is itself a change, just never a mid-stream one; the alternative (a placeholder
reserving space on every turn) is more noise, not less.

**Restructured the same day — see "Agents thread UX" below.** The in-thread mount shipped as
an inline expandable panel, and living with it for an hour showed the problem: its
"What it did" section re-listed the tool calls already rendered as inline rows directly
above. The panel is gone; the thread now groups tool calls per turn and routes all detail
to the `InspectorDrawer` overlay. `RunInternalsBody` survives unchanged as the shared
derivation's renderer — it just mounts in the overlay and in Observability instead of
in the thread.

### Workstream 3 — emit the provider-resolved model

See "Next work" item 0 below. Prerequisite for model comparison in workstream 4.

### Workstream 4 — cross-run queries

The Observability list becomes session-grouped and expandable to turns (scanning 672 flat
runs is unusable regardless of anything else), plus the saved queries listed above.

## Agents thread UX

The constraint: **insight without obstruction.** The thread is for working; the internals
must be available at a glance and invisible otherwise. Everything below is shipped except
the right-drawer item, which is called out as open.

- Every assistant turn carries **one collapsed line** beneath it, muted by default:
  `model · duration · 4 tools · 731 msg`. Color appears only when something deserves
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
Nothing here may shift layout while a run streams; expansion is user-initiated only.

### The shape it actually landed on — 2026-08-02

The bullets above describe an inline expandable panel. That shipped, and was wrong. Three
things only became visible once it was on screen:

1. **"What it did" was pure duplication.** `InlineToolRows` already renders every tool call
   as its own row immediately above. A panel that re-lists them is noise, not insight.
2. **Long content does not belong in a thread.** Tool output is often a whole file or a
   command dump. The `InspectorDrawer` overlay — 680px, own scroll, Escape to close — is
   the surface with room to read it, and it already existed.
3. **The internals are not a special class of object.** They are one more thing that
   happened in the turn. Once framed that way they become a row in the same list, and the
   separate panel has no reason to exist.

The shipped shape: one group per turn (`TurnToolGroup`) with a summary header —
"Searched 1×, ran command 2×" plus a failed count — expanding to one row per action. Every
row opens the overlay. The last row is the turn's internals (`InspectorTarget`
`{kind: 'run'}` → `RunInternalsDrawerBody` → `RunInternalsBody` with `showDid={false}`).

Details worth keeping:

- **A chat-only turn keeps a bare "Context it saw" row.** Load-bearing: a turn with no
  tools is exactly where "why didn't it use one?" is asked, and `promptedToolUse = false`
  is the usual answer. Hiding the row when there is nothing to group hides it where it
  matters most.
- **Grouping is by run, not adjacency**, so narration between calls does not split a turn
  into two groups.
- **The group stays open after a live run ends.** Collapsing content out from under someone
  who just watched it appear is worse than one extra expanded row. History starts collapsed.

`RunActivityPanel` retires from the Inspector column, which goes back to runtime state,
destinations, and approvals. `LiveToolFeed` is untouched — it is the only thing that
renders *during* a run.

### Raw policy dump — fixed 2026-08-02

A blocked `shell.exec` used to print its entire policy object into the transcript. Cause:
`_preview_payload` had no branch for it, so `_generic_preview` JSON-dumped the body beside a
UI already rendering `policyDecision`, `target`, and `policySummary` as fields — the same
refusal twice, once as prose and once as a wall of JSON. A body that is nothing but its
policy verdict now previews as `None`.

### Trace reset — **done 2026-08-02**

Existing traces were mostly from testing and predated the tier split, so they carried no
`tier` field and could not be backfilled. Purged via the new button: 337 files / 7.9 MB to
zero. Runs from before that date show `no trace` in the inspector; their run records,
transcripts, and artifacts are unaffected.

### Verification

Workstream 1 (done): `tests/unit/test_observability_store.py` (tier gating, size cap,
prune, purge), `tests/unit/test_trace_argument_digest.py` (digest boundaries),
`tests/integration/test_lifecycle_tracing.py` (a real run traces with Debug capture off,
carries no prompt text, and `debugCaptured` distinguishes the tiers). Live probes and the
browser purge run are recorded under workstream 1 above.

Still to do for later workstreams:

- Unit: session-grouped list shaping.
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
