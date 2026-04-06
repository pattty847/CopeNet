# CopeNet Run Tracing

CopeNet can write one structured JSONL trace per run for debugging harness, tool, provider, and response-synthesis behavior.

## Enable Tracing

Tracing is off by default.

Enable it for a focused debug session:

```bash
COPNET_TRACE=1 uv run cope
```

Trace files are written to:

- `COPNET_DATA_DIR/logs/runs/`
- or `~/.copenet/logs/runs/` by default

Each run creates one file:

- `<run-id>.jsonl`

If the requested provider fails to initialize before tracing starts, no trace file is created. In that case the client still receives an error event, so check the UI response or `providers.list` output first.

## Event Shape

Every line is a JSON object with:

- `timestamp`
- `event`
- `runId`
- `sessionKey`
- `provider`
- `model`
- optional `payload`

## Expected Event Types

Typical successful tool-assisted run:

1. `run_started`
2. `session_resolved`
3. `harness_planned`
4. `provider_turn_started`
5. `provider_session_updated` (optional)
6. `provider_turn_completed`
7. `tool_requested`
8. `tool_executed` or `tool_blocked`
9. `assistant_finalized`
10. `run_completed`

Typical failed run:

1. `run_started`
2. `session_resolved`
3. `harness_planned`
4. `run_failed`

## What To Inspect First

For debugging a surprising answer:

1. Open the newest run file.
2. Check `harness_planned`.
   - Did CopeNet try a tool loop?
   - Which tool ids were available?
   - `availableToolIds` may still be populated even when `willAttemptToolLoop` is `false`; the real gate is the capability decision, not the presence of registered tools.
3. Check `tool_requested`.
   - Did the model ask for the tool you expected?
   - Were the arguments correct?
4. Check `tool_executed` or `tool_blocked`.
   - Was this a policy rejection?
   - Was it a real execution failure?
5. Check `assistant_finalized`.
   - Did the final answer include a tool execution summary?
   - Does the response length or tool attachment line up with the UI?

For latency debugging, compare the timestamps on `provider_turn_started` and `provider_turn_completed`. A `deltaCount` of `1` can be normal for providers like Ollama that send the final text in one chunk.

## Example Scenarios

### Successful repo-local tool run

Use a prompt that requires reading a file inside the current CopeNet workdir.

Expect:

- `tool_requested`
- `tool_executed`
- `assistant_finalized`
- `run_completed`

### Blocked path escape

Ask the model to inspect a path outside the configured CopeNet workdir.

Expect:

- `tool_requested`
- `tool_blocked`
- reason like `path escapes workdir`
- final answer explaining the restriction

### Provider or synthesis failure

If the provider run fails or the tool loop breaks:

Expect:

- `run_failed`
- payload with the relevant error

## Claude Inspection Workflow

Claude should use traces as an inspection artifact, not as implementation scaffolding.

Recommended report format:

- scenario name
- run id
- expected behavior
- observed behavior
- key trace events
- concise finding summary

Good first scenarios:

- successful repo-local tool read/search
- blocked path escape
- shell allowlist success
- shell allowlist rejection
- local-model chat-only run
- Codex tool-assisted run

## Cleanup

There is no automatic retention in v1. Delete old trace files manually when needed.
