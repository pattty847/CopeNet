# CopeNet React Frontend Handoff

## Product

CopeNet’s React frontend is a dark operator-console UI that talks to the existing WebSocket RPC backend. The frontend owns client-side draft state, transport lifecycle, optimistic chat rendering, and inline tool trace presentation. The backend remains responsible for orchestration, tool execution, persistence, session semantics, and streamed chat events.

## Actual Backend Contract

### Handshake and frames

- client connects to `/ws`
- server sends `connect.challenge`
- client sends a request frame for `connect`
- all non-streaming RPC calls use:
  - `{ type: "req", id, method, params }`
- responses are:
  - `{ type: "res", id, ok, payload?, error? }`
- streaming events are:
  - `{ type: "event", event, payload }`

### RPC methods

- `connect`
- `providers.list`
- `models.list`
- `prompts.list`
- `tools.list`
- `sessions.list`
- `sessions.create`
- `sessions.rename`
- `sessions.archive`
- `sessions.resolve`
- `chat.history`
- `chat.send`
- `chat.abort`

### Important parameter names

- `sessions.list` uses `includeArchived`
- `sessions.rename` uses `key`
- `sessions.archive` uses `key` and `archived`
- `sessions.resolve` uses `key`
- `chat.history` uses `sessionKey`
- `chat.send` uses `sessionKey`, `message`, `provider`, `model`, `systemPromptId`, `taskPromptId`
- `chat.abort` accepts `sessionKey` or `runId`

### Event usage

- `connect.challenge`
- `chat`

The `chat` event includes `state` values such as:
- `delta`
- `final`
- `error`
- `aborted`

Tool execution arrives as a single `toolExecution` object attached to chat payloads.

## Session Semantics

- Draft state lives client-side until first send.
- “New Chat” does not immediately call `sessions.create`.
- The first send creates the session using the current draft runtime settings.
- After first send, the session is treated as locked to provider/model/profile/task mode.
- Rename is allowed.
- Archive/restore uses `sessions.archive` with `archived: true|false`.
- Do not assume in-place message editing or mid-session model switching.

## UI/State Responsibilities

### Layout

- left session rail
- center chat timeline and composer
- right telemetry panel
- top status/header

### Store

The Zustand store should own:
- transport state: `wsStatus`, `authError`, `appError`, `activeRunId`
- catalog state: providers, models-by-provider cache, profiles, task modes, tools
- session state: sessions, `activeSessionKey`, `showArchived`, client-side `draftSettings`
- chat state: messages by session key and pending assistant placeholders keyed by `runId`

### Draft settings

Use real backend field names in the draft store:
- `provider`
- `model`
- `systemPromptId`
- `taskPromptId`

### Message model

Backend transcript/history payloads do not include stable frontend ids, so the frontend should normalize them into messages with a client-generated `localId`.

## Tooling Contract

Available tools currently include:
- `context.prepare`
- `files.list`
- `files.read`
- `files.search`
- `git.status`
- `git.diff`
- `shell.exec`

Implementation rules:
- `tools.list` provides the available catalog
- `toolExecution` on chat payloads shows what actually ran
- render tool calls inline in the message timeline as collapsible execution cards
- the right panel should show latest tool activity from real `toolExecution` data only
- do not render fake telemetry, fake progress, or fake thinking traces

## Implementation Notes

- load providers, prompts, tools, and sessions after successful `connect`
- load models lazily by provider and cache them
- select an existing session from the returned session list on boot when available
- load `chat.history` when selecting a persisted session
- user messages are optimistic client inserts because the backend does not echo them over `chat` events
- `chat.send` returns `runId`; use it to map streamed assistant deltas/finalization to one optimistic assistant placeholder
- after final/error, refresh the session catalog so updated metadata stays current

## Hosting

- React source lives in `src/copenet/host/frontend`
- Vite build output is served by FastAPI when `frontend/dist` exists
- built app should default to same-origin `/ws`
- development can override the WebSocket URL with `VITE_COPNET_WS_URL`
