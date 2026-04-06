# CopeNet Run Tracing — Findings Report

**Date:** 2026-04-06
**CopeNet commit:** `83c14f3` (main) + local tracing changes
**Inspector:** Claude trace validation pass

## Summary

The initial trace validation pass confirmed that per-run JSONL tracing works for LM Studio and Ollama chat-only paths. The main remaining gaps are around observability for provider-init failures, resolved default-model visibility, and elapsed timing data.

## Top Findings

1. **Happy-path tracing works.**
   LM Studio and Ollama runs emitted the expected ordered event sequence for successful chat-only runs.
2. **Provider init errors produce no trace file.**
   If a requested provider is unavailable before `RunTraceWriter` is instantiated, the client gets an error but no trace file is created.
3. **`model: null` appears when no explicit model is requested.**
   The trace currently reflects the request model field, not the provider-resolved default model.
4. **`provider_turn_completed` has no elapsed timing.**
   Latency can be inferred from timestamps, but a direct `elapsed_ms` field would make performance inspection much easier.
5. **Ollama `deltaCount: 1` is normal.**
   Ollama may send the whole reply in a single chunk; that is not a streaming failure.
6. **The live Codex tool loop still needs a dedicated validation pass.**
   The richest tool path should be re-run in an environment where Codex CLI is available.

## Recommended Follow-Up

1. Add `elapsed_ms` to `provider_turn_completed`.
2. Surface the provider-resolved default model into the trace stream.
3. Decide whether provider-init failures should create an early `run_failed` trace or a separate lightweight provider-error log.
4. Re-run the trace scenario pack with Codex CLI available to validate `tool_requested`, `tool_executed`, and `tool_blocked` on live tool-enabled turns.
