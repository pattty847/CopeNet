# CopeNet Run Tracing — Findings

This document records findings from trace validation passes. Use it to understand what has been verified, what gaps exist, and what to watch for during debugging.

---

## Pass 1 — 2026-04-06

**Commit:** `83c14f3` (main) + local tracing changes
**Inspector:** Claude trace validation pass

### Summary

Per-run JSONL tracing works for LM Studio and Ollama chat-only paths. The core ordered event sequence emits correctly. Main gaps are around provider-init observability, default-model visibility in traces, and latency fields.

### Findings

**F1 — Happy-path tracing works.**
LM Studio and Ollama runs emitted the expected ordered event sequence for successful chat-only runs.

**F2 — Provider init errors produce no trace file.**
If a requested provider is unavailable when `send_chat` runs, the error is raised before `RunTraceWriter` can record anything. The client receives an error event but no `.jsonl` file is written. This makes it impossible to trace init-time failures via the run log alone.

**F3 — `model: null` when no explicit model is requested.**
The trace writes the request's `model` field, not the provider-resolved default. When the client omits a model, the field is `null` throughout the entire trace, even though the provider used a real model. Resolution requires surfacing the resolved default into the trace stream after `session_resolved`.

**F4 — `provider_turn_completed` has no elapsed timing.**
Latency can be inferred by diffing `provider_turn_started` and `provider_turn_completed` timestamps, but a direct `elapsed_ms` field would make this much easier in tooling and reports.

**F5 — Ollama `deltaCount: 1` is normal.**
Ollama may deliver the entire response in one chunk. A `deltaCount` of `1` is not a streaming failure — it's a provider behavior difference.

**F6 — Codex tool loop path unvalidated on live hardware.**
The `tool_requested`, `tool_executed`, and `tool_blocked` events exist in code and are believed correct, but the full tool loop path (S1–S4) has not been exercised against a real Codex CLI installation. Chat-only paths (LM Studio, Ollama) are confirmed working.

### Recommended Follow-Up

1. Add `elapsed_ms` to `provider_turn_completed` payload.
2. After `session_resolved`, surface the provider-resolved default model into the trace (e.g., in `harness_planned` or a new `model_resolved` event).
3. Decide whether provider-init failures should create an early `run_failed` trace entry or a separate lightweight error log.
4. Re-run the scenario pack with Codex CLI available to validate `tool_requested`, `tool_executed`, and `tool_blocked` on live tool-enabled turns.

---

## Known Permanent Behaviors (not bugs)

These are expected behaviors that look surprising without context:

| Observation | Explanation |
|---|---|
| `model: null` in trace | No model specified in request; provider resolved a default silently |
| `deltaCount: 1` for Ollama | Ollama streams entire reply in one chunk; not a failure |
| No trace file for failed provider | `RunTraceWriter` is created after provider is confirmed available |
| `availableToolIds` populated but `willAttemptToolLoop: false` | Capability gate (`promptedToolUse`) is separate from tool registration |
| Two `provider_turn_started/completed` pairs in tool run | Tool-assisted runs make two provider calls: tool-attempt then tool-follow-up |

---

## How to Add a New Finding

When running a trace validation pass, append a new dated section above with:
- Commit or branch context
- Inspector identity
- Each finding labeled F1, F2, ... with a short title and description
- Recommended follow-up items
