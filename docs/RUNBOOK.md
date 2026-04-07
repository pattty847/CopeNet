# CopeNet Runbook

This is the shortest path from “something feels off” to “I know what happened.”

## Start

```bash
uv sync
uv run cope
```

Open:

- `http://127.0.0.1:17123`

## Verify Healthy

Checklist:

- UI loads
- connect handshake succeeds
- `providers.list` shows the runtimes you expect
- `models.list` returns chat models for LM Studio / Ollama
- `tools.list` returns the built-in safe tool catalog

## Enable Debug Mode

```bash
COPNET_TRACE=1 uv run cope
```

Then reproduce one run and inspect:

- [TRACING.md](TRACING.md)
- [DEBUGGING.md](DEBUGGING.md)
- [TRACE-FINDINGS.md](TRACE-FINDINGS.md)

## Common Failure Causes

- provider runtime not actually running
- wrong runtime base URL in env
- port already in use
- provider unavailable at startup
- locked session binding mismatch
- tool blocked by workdir or allowlist policy
- local model answered in chat-only mode instead of using tools

## Reset / Recover

### Port conflict

```bash
kill $(lsof -tiTCP:17123 -sTCP:LISTEN)
```

Or run another port:

```bash
COPNET_PORT=17124 uv run cope
```

### Fresh trace session

```bash
COPNET_TRACE=1 uv run cope
ls -lt ~/.copenet/logs/runs/ | head -10
```

### Verify runtime availability

Use the UI provider list or inspect the local runtime directly:

- LM Studio: `http://127.0.0.1:1234/v1/models`
- Ollama: `http://127.0.0.1:11434/api/tags`

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
