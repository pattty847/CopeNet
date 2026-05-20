# HarnessDecision + Tool Display Contract V1

## Summary

Implement trace-only `HarnessDecision` and richer tool effect metadata without changing runtime behavior. The model declares semantics through schema/enums/exact tool ids; the harness validates, records, executes existing flow, and exposes structured data for chat/inspector displays.

Before implementing, checkpoint the current dirty work for Claude inspection: create a branch from `main`, stage all non-ignored current changes, commit them as a pre-implementation checkpoint, and push the branch. Leave ignored local audit notes alone unless explicitly promoted into tracked docs.

## Key Changes

- Add `HarnessDecisionRecord` as the persisted/streamed wrapper:
  ```ts
  type HarnessDecisionRecord = {
    schema_version: "harness_decision_record.v1";
    decision_id: string;
    turn_id: string;
    control_mode: "trace_only";
    status: "parsed" | "repaired" | "fallback" | "unavailable";
    decision: HarnessDecision | null;
    error_summary?: string;
  };
  ```
- Add model-authored `HarnessDecision` with enum-only control fields:
  - `request_kind`, `route`, `next_action`, `risk`, `evidence_requirements`
  - `tool_decision.selected_tool_id` must match an exact visible tool id
  - free-text fields use `trace_note`, `user_goal`, `missing`, and `assumptions`; they are displayed/logged only and never drive control logic
- Add `decision_id` and `turn_id` to decision records, tool call payloads, tool result payloads, run metadata, and inspector-normalized frontend types so UI rows can link decision → calls → results → run record without timestamp guessing.
- Add `control_mode: "trace_only"` and make `status: "unavailable"` a normal outcome for providers/model outputs that cannot produce a valid decision.
- Extend tool manifest entries with `evidenceRole`, `sideEffect`, and `requiresConfirmation`; expand category vocabulary for future `shell-write` and `browser` while preserving current policy behavior.
- Add versioned tool effect metadata:
  ```ts
  type ToolEffect = {
    schema_version: "tool_effect.v1";
    effect_id: string;
    decision_id?: string | null;
    turn_id: string;
    tool_id: string;
    kind: "file_read" | "repo_search" | "shell_command" | "file_write" | "file_edit" | "artifact" | "context" | "raw";
    target?: string | null;
    preview?: Record<string, unknown> | null;
    artifact_id?: string | null;
    evidence_role: ToolManifestEntry["evidenceRole"];
  };
  ```
- Frontend v1 displays:
  - inline chat remains compact tool receipts
  - clicking a tool/artifact opens inspector detail
  - inspector shows exact tool id, structured args/effect, path/command/query, preview/artifact link, policy receipt, evidence role, and decision prose fields

## Implementation Notes

- Add the router as an isolated trace-only decision pass before the normal turn. It records traces and run metadata, but does not suppress tools, force tools, or block final answers.
- Use `trace_note`, not `reason`, for prose explanation. If a machine-readable reason is needed later, add `reason_code` as an enum.
- Keep prompted tool behavior unchanged in this v1 except for documenting the future strict parser. Later, `{"command":"pwd"}` should be rejected because it does not name an exact tool id.
- Update AGENTS/CLAUDE and architecture/tracing/event docs with the rule: model declares semantics; harness validates exact schema and authority; no keyword routing.

## Test Plan

- Unit tests:
  - valid `HarnessDecisionRecord` parses with `decision_id`, `turn_id`, `control_mode`, and `trace_note`
  - `unavailable` and `fallback` records persist without throwing
  - unknown enum values and invented tool ids fail validation
  - prose fields are preserved but never used for branching
  - tool manifest/effect metadata includes schema versions and evidence roles
- Integration tests:
  - valid decision is recorded and normal turn behavior is unchanged
  - invalid decision records fallback and run still completes
  - decision says `CALL_TOOL` but scripted provider answers directly; assert no tool is forced
  - decision says direct response but normal tool loop still executes if model calls tools; assert v1 is truly trace-only
  - run records expose `metadata.harnessDecision`
- Frontend tests:
  - `wsClient` normalizes decision/effect fields with ids intact
  - inline tool rows still render compactly
  - inspector renders file read, shell command, artifact-backed long output, and decision trace notes
- Regression checks:
  - existing tool loop and run-record tests stay green
  - no production substring/keyword routing is added
  - stale docs around final gating / old batch behavior are corrected when touched

## Assumptions

- V1 is trace-only and inspector-visible, not behavior-steering.
- Agentic scenario bench is a separate follow-up plan.
- Current dirty work should be checkpointed on a pushed branch before implementation starts.
- Frontier models are the initial target; local small-model strict mode is deferred.
