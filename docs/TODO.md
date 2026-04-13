# CopeNet Circle-Back TODO

This doc is the higher-level backlog for ideas we want to revisit after the current frontend + harness stabilization work. The repo-root `TODO.md` stays the practical near-term checklist; this file is for medium-term product and architecture follow-ups.

## Immediate Next

- Review and commit the deterministic tool prompt matrix tests.
- Build the live provider probe layer for Codex and local models using the same prompt matrix.
- Debug the intermittent Codex prompted-tool refusal with traces from fresh vs resumed sessions.
- Do a full manual smoke pass on the React UI after the current frontend fixes are reviewed.

## Harness / Runtime

- Add explicit run-state / transition logging for retries, aborts, resume, tool-attempt, tool-follow-up, and failure states.
- Treat session resume as restoring a session envelope, not just loading transcript history.
- Consider a separate debug artifact lane for normalized provider requests/responses and tool payloads without polluting the transcript.
- Revisit concurrency-safe streaming tool execution only after the single-tool loop is fully stable.

## Testing

- Keep expanding deterministic harness/provider tests before adding more real-model probe complexity.
- Add a live probe runner that records real provider/model outcomes for:
  - tool success
  - tool refusal
  - blocked tool paths
  - resumed-session drift
  - follow-up stability after tool use
- Add browser automation only if it stays lightweight and clearly useful.

## Frontend / UX

- Tighten archive/restore UX so resurfacing archived sessions feels intentional and obvious.
- Improve distinction between policy-blocked tools and genuine tool failures.
- Decide how visible provider/runtime health and auth state should be in the operator console.
- Keep the UI focused on clarity and trust, not dashboard bloat.

## Product Direction

- Clarify CopeNet’s wedge beyond “agent harness with a UI.”
- Strong candidate direction:
  - local-first reproducible AI workbench for durable workspace sessions
- Brainstorm product bets around:
  - reproducible workspace sessions
  - multi-provider comparison workflows
  - research/investigation console patterns
  - mode-driven operator workflows

## Ideas Worth Revisiting

- durable pre-response transcript commits
- explicit run-state machine / transition logs
- session envelope restore model
- richer provider capability surfacing
- future multi-tool orchestration
