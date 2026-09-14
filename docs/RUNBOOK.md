# CopeNet Runbook

This is the shortest path from “something feels off” to “I know what happened.”

## Start

```bash
uv sync
uv run copenet
```

Open:

- `http://127.0.0.1:17123`

## Verify Healthy

Checklist:

- UI loads
- connect handshake succeeds
- `providers.list` shows the runtimes you expect
- `models.list` returns chat models for `openai-codex` and `claude-cli`
- `tools.list` returns the built-in safe tool catalog

## Enable Debug Mode

```bash
COPNET_TRACE=1 uv run copenet
```

Then reproduce one run and inspect:

- [TRACING.md](TRACING.md)
- [DEBUGGING.md](DEBUGGING.md)

## Common Failure Causes

- provider runtime not actually running
- wrong runtime base URL in env
- port already in use
- provider unavailable at startup
- locked session binding mismatch
- tool blocked by workdir or allowlist policy
- model answered in chat-only mode instead of using tools

## Reset / Recover

### Port conflict

```bash
kill $(lsof -tiTCP:17123 -sTCP:LISTEN)
```

Or run another port:

```bash
COPNET_PORT=17124 uv run copenet
```

### Fresh trace session

```bash
COPNET_TRACE=1 uv run copenet
ls -lt ~/.copenet/logs/runs/ | head -10
```

### Verify runtime availability

Use the UI provider list, `uv run copenet auth status` for `openai-codex`, and `which claude` for `claude-cli`.

## Best First Questions

When debugging, ask these in order:

1. Did the run happen at all?
2. Did the harness think tools were allowed?
3. Did the model request a tool?
4. Did policy block it or did execution fail?
5. Did the final answer reflect what actually happened?
6. Did continuity stay intact?

## Related Docs

- [EVENT-CONTRACT.md](EVENT-CONTRACT.md)
- [SESSION-CONTINUITY.md](SESSION-CONTINUITY.md)
- [CAPABILITY-MATRIX.md](CAPABILITY-MATRIX.md)
- [TRACING.md](TRACING.md)
- [DEBUGGING.md](DEBUGGING.md)
