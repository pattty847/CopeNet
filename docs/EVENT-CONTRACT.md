# CopeNet Event Contract

This document describes the normalized WebSocket RPC contract that CopeNet clients consume. Treat it as the current transport ABI for the browser UI, `GatewayClient`, and future wrappers.

## Transport Overview

CopeNet uses a WebSocket endpoint at `/ws` with three frame types:

- `req`
- `res`
- `event`

Connection flow:

1. Server sends `event=connect.challenge`
2. Client replies with `method=connect`
3. Server returns `type=res, ok=true`
4. Client may now send RPC requests

The current protocol version is advertised in the `connect` response payload:

```json
{
  "type": "hello-ok",
  "protocol": 1,
  "features": { ... }
}
```

## Frame Shapes

### Request Frame

```json
{
  "type": "req",
  "id": "client-generated-id",
  "method": "chat.send",
  "params": {}
}
```

Required fields:

- `type = "req"`
- `id` non-empty string
- `method` non-empty string

### Response Frame

```json
{
  "type": "res",
  "id": "same-request-id",
  "ok": true,
  "payload": {}
}
```

Error responses use:

```json
{
  "type": "res",
  "id": "same-request-id",
  "ok": false,
  "error": {
    "code": "INVALID_REQUEST",
    "message": "..."
  }
}
```

### Event Frame

```json
{
  "type": "event",
  "event": "chat",
  "seq": 3,
  "payload": {}
}
```

Current event names:

- `connect.challenge`
- `chat`

## `chat` Event Payload

`chat` events are the normalized streaming contract for one run.

```json
{
  "runId": "run-id",
  "sessionKey": "session-key",
  "seq": 1,
  "state": "delta",
  "message": {
    "role": "assistant",
    "content": "Hello",
    "provider": "lm-studio",
    "model": "gemma-4-e4b-it"
  },
  "errorMessage": null,
  "provider": "lm-studio",
  "model": "gemma-4-e4b-it",
  "capabilities": {
    "toolCalls": false
  },
  "toolExecution": null
}
```

Known `state` values:

- `delta`
- `final`
- `error`
- `aborted`

### Field Meaning

- `runId`: stable id for one request/run
- `sessionKey`: chat session identifier
- `seq`: monotonic per-run event counter emitted by the server
- `state`: event stage
- `message`: assistant message payload when applicable
- `errorMessage`: populated for `state = error`
- `provider`: active provider id for the run
- `model`: request model field as currently surfaced by the orchestrator
- `capabilities.toolCalls`: whether the harness treated the run as tool-capable
- `toolExecution`: compact tool metadata attached when a tool ran

## Ordering Guarantees

For one `runId`:

- `seq` increases monotonically
- `delta` events arrive before `final`
- `final`, `error`, and `aborted` are terminal states
- only one terminal state should be treated as authoritative by clients

Expected normal ordering:

1. `res` for `chat.send`
2. zero or more `chat` events with `state = delta`
3. one terminal `chat` event with `state = final`, `error`, or `aborted`

## Terminal State Semantics

### `final`

`final` means the run finished from CopeNet’s perspective and the orchestrator emitted the final payload. It does not imply:

- provider subprocess lifetime details
- transcript save success beyond the normal current path
- that the provider itself has a concept of “done” identical to CopeNet’s

It does mean the client should stop waiting for more events for that `runId`.

### `error`

`error` means the run failed before a successful final assistant completion. The primary diagnostic is:

- `errorMessage` in the event payload
- trace-side `run_failed` when tracing is enabled

### `aborted`

`aborted` means the active run was explicitly cancelled through `chat.abort` or equivalent run interruption. Clients should treat it as terminal and stop waiting for more deltas.

## Idempotency Behavior

`chat.send` accepts `idempotencyKey`.

Current behavior:

- repeated use of the same key maps to the same logical run cache entry
- if the run is already active for that session, CopeNet may respond with `status = in_flight`
- if the run result is already cached, CopeNet may respond with `status = cached`

Clients should not assume every `chat.send` creates a brand-new run.

## Tool Metadata Contract

When a tool call succeeds or fails in a tool-enabled path, `toolExecution` may be attached to streamed and final chat payloads:

```json
{
  "toolId": "files.list",
  "ok": true,
  "summary": "Listed 12 entries under ."
}
```

Possible fields:

- `toolId`
- `ok`
- `summary`
- `error` when the tool failed or was blocked

This is intentionally compact and user-facing, not a full raw tool transcript.

## Compatibility Guidance

Safe assumptions for clients:

- unknown top-level fields may appear later
- unknown `capabilities` keys may appear later
- new RPC methods may be advertised in `connect.features.methods`

Unsafe assumptions:

- assuming every provider streams token-by-token
- assuming `model` is always non-null
- assuming `toolExecution` exists for all tool-capable runs
- assuming provider session continuity semantics from provider-specific behavior

## What Is Sacred

The most important invariants in this contract are:

- normalized `chat` event shape
- terminal-state semantics
- monotonic `seq` behavior within a run
- stable separation of request/response frames from streamed event frames

If those change, the UI, client wrapper, and future external integrations all need coordinated updates.
