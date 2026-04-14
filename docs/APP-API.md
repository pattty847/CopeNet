# App API (`/api/v1`)

CopeNet now exposes a second transport for external local apps like Subtext.

- Internal UI and automation still use `/ws` JSON-RPC.
- External apps use bearer-authenticated REST plus SSE under `/api/v1`.
- External app session ids are app-local. CopeNet keeps the internal `sessionKey` private.

## Security model

Each external app gets its own bearer token.

- tokens are stored hashed with SHA-256 in `apps.json`
- auth is app-scoped, not shared with the `/ws` token
- each app only sees sessions mapped to its own app id
- external apps default to `allowTools: false`

That default means Subtext and similar clients do **not** get workspace tool execution unless you explicitly provision an app with `allow_tools=True`.

## Provision an app

Today provisioning is done in process code, for example during local setup:

```python
from copenet.core.orchestrator import Orchestrator

orchestrator = Orchestrator()
app, token = orchestrator.register_app(
    app_id="subtext",
    display_name="Subtext",
    default_provider="codex-cli",
    default_model=None,
    allow_tools=False,
)
print(app)
print(token)  # capture once and give to the app
```

The returned plain token is only available at registration time. Stored state keeps only the hash.

## Session mapping

When Subtext creates session `abc123`, CopeNet creates an internal session key like:

```text
app-subtext-7b2d4d2ce8fa
```

The mapping is persisted in `apps.json`, but the REST API only returns the app-local id:

```json
{
  "id": "abc123",
  "title": "Draft reply",
  "provider": "codex-cli"
}
```

## Endpoints

All requests require:

```http
Authorization: Bearer <app-token>
```

### Catalog

- `GET /api/v1/providers`
- `GET /api/v1/models?provider=<id>`

### Sessions

- `GET /api/v1/sessions`
- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `PATCH /api/v1/sessions/{session_id}`

Create body:

```json
{
  "id": "subtext-thread-42",
  "title": "Inbox reply",
  "provider": "codex-cli",
  "model": null,
  "systemPromptId": "default",
  "taskPromptId": "general"
}
```

### Messages and history

- `GET /api/v1/sessions/{session_id}/messages`
- `POST /api/v1/sessions/{session_id}/messages`
- `GET /api/v1/sessions/{session_id}/messages/stream?content=...`

Send body:

```json
{
  "content": "Draft a concise reply.",
  "provider": "codex-cli",
  "model": null,
  "idempotencyKey": "optional-client-run-id"
}
```

### Cancel

- `POST /api/v1/runs/{run_id}/cancel`

## SSE contract

`GET /api/v1/sessions/{session_id}/messages/stream` returns `text/event-stream`.

Current events:

- `event: chat` with one streamed chat payload
- `event: done` when the stream is finished

Example `chat` payload:

```json
{
  "runId": "run-123",
  "sessionKey": "app-subtext-hidden",
  "seq": 1,
  "state": "delta",
  "message": {
    "role": "assistant",
    "content": "Hello"
  }
}
```

Subtext should ignore `sessionKey` and use its own session id from the request path.

## Subtext integration notes

Recommended flow:

1. Provision one CopeNet app id for Subtext.
2. Store the bearer token in Subtext local config.
3. On first local thread creation, call `POST /api/v1/sessions` with Subtext’s thread id.
4. For history, call `GET /api/v1/sessions/{id}/messages`.
5. For live replies, prefer `GET /api/v1/sessions/{id}/messages/stream?content=...` and render deltas as they arrive.
6. If the user stops generation, call `POST /api/v1/runs/{run_id}/cancel`.

## Reasonable v1 design choices

- SSE send uses `GET` with query params to keep browser/EventSource integration simple.
- External apps do not receive raw internal session keys as stable ids.
- Tool execution is off by default for safer app embedding.
