# CopeNet

Local-first agent harness for coding and research workflows.

CopeNet runs a WebSocket gateway + browser UI over local and CLI-backed models (Codex CLI, LM Studio, Ollama), with persistent sessions, transcripts, prompt profiles, and streaming responses.

## Why CopeNet

- **Local-first workflow**: run on your machine, keep context close.
- **Multi-runtime sessions**: lock each chat to a provider/model for reproducibility.
- **Streaming UX**: token deltas + final events over WebSocket.
- **Prompt composition**: base profile + task mode overlays.
- **Durable history**: JSON/JSONL session and transcript storage.
- **Python API included**: use `GatewayClient` from your own scripts/tools.

## Features

- FastAPI host + WebSocket RPC (`/ws`) and web app (`/`)
- Runtime catalog + model discovery for:
  - `codex-cli`
  - `lm-studio` (OpenAI-compatible local endpoint)
  - `ollama`
- Session management:
  - create/rename/archive
  - provider/model/profile/task-mode metadata
  - one in-flight run per session
- Prompt presets:
  - profiles (e.g. default, builder, teacher)
  - task modes (e.g. planning, debug, code-review)
- Provider-agnostic orchestrator + harness layer

## Quickstart

### 1) Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- Optional local runtimes:
  - Ollama running on `http://127.0.0.1:11434`
  - LM Studio local server on `http://127.0.0.1:1234`
- Optional CLI runtime:
  - Codex CLI installed and authenticated

### 2) Install dependencies

From repo root:

```bash
uv sync
```

### 3) Run CopeNet

```bash
uv run cope
```

Then open:

- `http://127.0.0.1:17123`

That’s it.

## Startup Tips (new machine in ~2 minutes)

1. Start your local model servers first (Ollama and/or LM Studio).
2. Run `uv run cope`.
3. Open the UI and click **New Chat**.
4. Pick runtime + model + profile/task mode.
5. Send first message (session locks to that runtime/model pair).

If you switch runtimes/models later, create a **new chat**.

## Configuration

Environment variables:

- `COPNET_HOST` (default: `127.0.0.1`)
- `COPNET_PORT` (default: `17123`)
- `COPNET_TOKEN` (default: `dev-token`)
- `COPNET_DATA_DIR` (default: `~/.copenet/sessions`)
- `COPNET_EXECUTION_MODE` (`safe` | `tools-enabled` | `unrestricted`)
- `COPNET_TRACE` (`1` to enable per-run JSONL traces)
- `COPNET_LM_STUDIO_BASE_URL` (default: `http://127.0.0.1:1234`)
- `COPNET_OLLAMA_BASE_URL` (default: `http://127.0.0.1:11434`)

Example:

```bash
export COPNET_TOKEN="change-me"
export COPNET_PORT=17123
uv run cope
```

## Prompt Presets

Prompt presets are markdown files under:

- `src/copenet/prompts/presets/profiles/`
- `src/copenet/prompts/presets/task-modes/`

The loader composes:

- **profile** (base behavior)
- + **task mode** (situational instruction)

Add your own by dropping `.md` files in those directories.

## CLI Entry Points

- Full app (recommended):

```bash
uv run cope
```

- Backend host only:

```bash
uv run copenet-host
# or
python -m copenet.host
```

## Python Usage

```python
from copenet import GatewayClient, GatewayConfig, Orchestrator, CopeNetWsServer
```

## Docs

- [Architecture](docs/architecture.md)
- [STARTUP](docs/STARTUP.md)
- [Event Contract](docs/EVENT-CONTRACT.md)
- [Session Continuity](docs/SESSION-CONTINUITY.md)
- [Capability Matrix](docs/CAPABILITY-MATRIX.md)
- [TRACING](docs/TRACING.md)
- [DEBUGGING](docs/DEBUGGING.md)
- [RUNBOOK](docs/RUNBOOK.md)

## Troubleshooting

### Models not showing up

- Verify runtime server is running:
  - Ollama: `http://127.0.0.1:11434`
  - LM Studio: `http://127.0.0.1:1234`
- Check your env var overrides.
- Restart CopeNet after changing endpoints.

### Debugging a weird tool run

- Enable tracing: `COPNET_TRACE=1 uv run cope`
- Reproduce the run once
- Open the newest file under `~/.copenet/logs/runs/`
- Inspect the event order:
  - `harness_planned`
  - `tool_requested`
  - `tool_executed` or `tool_blocked`
  - `assistant_finalized`

See [`docs/TRACING.md`](docs/TRACING.md) for the trace schema and workflow.

### Prompt/profile changes not applying

- Start a new session after changing profile/task mode.
- Ensure preset markdown files are in the correct presets directories.

### Port already in use

- Set another port:

```bash
COPNET_PORT=17124 uv run cope
```

## Project Status

Actively evolving. Core orchestration, sessions, prompts, local-provider support, and web UX are in place and improving rapidly.

---

If you build on top of CopeNet, open an issue or PR with your runtime/provider ideas. Local agent infra should be composable, inspectable, and fun to hack on.
