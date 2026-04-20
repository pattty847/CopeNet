# CopeNet

CopeNet is a local-first agent operator studio for people who want more than a chat box. It gives you a persistent workspace for running local and CLI-backed models, inspecting what they actually did, and turning useful sessions into repeatable workflows.

<img width="1920" height="928" alt="CopeNet Home dashboard" src="https://github.com/user-attachments/assets/64146bd1-15f2-4357-acd5-3fa04f891f37" />
<img width="1920" height="929" alt="CopeNet agent console" src="https://github.com/user-attachments/assets/97683804-f2df-4265-93be-b1ed917e9501" />

## Why CopeNet

Most local AI tools stop at “send a prompt, get a reply.” CopeNet is built for the workflows that happen after that:

- **Operate locally**: keep models, transcripts, and sensitive context close to your machine
- **Inspect runs**: see traces, tool activity, runtime drift, and session state instead of guessing
- **Reuse workflows**: move from one-off chats to repeatable operator surfaces
- **Compare runtimes**: lock sessions to provider/model combinations so behavior stays explainable
- **Extend without cloud lock-in**: add prompts, tools, workflows, and knowledge sources without giving up local control

## What You Can Do

CopeNet is evolving into an operator workspace, not just a chat client. Today it already supports:

- **Agent sessions** with persistent transcripts, first-send runtime locking, archive/restore, and inline tool execution
- **Observability** with run pulse views, recent traces, provider/tool distributions, and session activity inspection
- **Workflow surfaces** such as `Meme Lab`, built on top of a stateless ideation API for structured local-model generation
- **Media imports** for transcription and download-first workflows, including mobile-friendly remote use over Tailscale
- **Experiments** for comparing provider/model behavior across real runs
- **Prompt layering** with editable profile + task-mode markdown presets

## Providers

CopeNet currently supports local and CLI-backed runtimes through a shared harness:

- `codex-cli`
- `lm-studio`
- `ollama`

The goal is provider-agnostic operator tooling: one workspace, multiple runtimes, consistent session semantics.

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

```bash
uv sync
```

### 3) Run CopeNet

```bash
uv run copenet
```

Open the desktop UI at:

- `http://127.0.0.1:17123`

### 4) Optional: open it remotely on your own devices

CopeNet also works well over your tailnet for private mobile access:

```bash
COPNET_HOST=0.0.0.0 COPNET_PORT=17123 uv run copenet
```

Then open it from another device using your Tailscale hostname or tailnet IP.

## Local Setup Notes

1. Start your local runtimes first (Ollama and/or LM Studio).
2. Run `uv run copenet`.
3. Open the UI and create a new session.
4. Pick provider, model, profile, and task mode.
5. Send the first message to create and lock that session.

If you want to compare another runtime/model combination, start a new chat rather than mutating the existing one.

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
- `COPNET_MEME_KB_ROOT` (optional local knowledge-library root for Meme Lab extensions)
- `COPNET_MEME_KB_CACHE_DIR` (optional cache directory for generated knowledge indexes)

Example:

```bash
export COPNET_TOKEN="change-me"
export COPNET_PORT=17123
uv run copenet
```

## Bring Your Own Knowledge Base

CopeNet can integrate with curated local knowledge sources, including markdown-based creative or research libraries. The public repo does **not** assume any personal vault or branded workflow setup.

To sketch your own local setup, start with:

- `config/knowledge-sources.example.toml`

Then create your own ignored local override:

- `config/knowledge-sources.local.toml`

See [`docs/KNOWLEDGE-BASES.md`](docs/KNOWLEDGE-BASES.md) for the pattern.

## Prompt Presets

Prompt presets are markdown files under:

- `src/copenet/prompts/presets/profiles/`
- `src/copenet/prompts/presets/task-modes/`

The loader composes:

- **profile** for base behavior
- **task mode** for situational instruction

Add your own by dropping `.md` files into those directories.

## CLI Entry Points

- Full app (recommended):

```bash
uv run copenet
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

### Getting Started

- [Startup](docs/STARTUP.md)
- [Testing](docs/TESTING.md)
- [Knowledge Bases](docs/KNOWLEDGE-BASES.md)

### Architecture

- [Architecture](docs/ARCHITECTURE.md)
- [App API](docs/APP-API.md)
- [Event Contract](docs/EVENT-CONTRACT.md)
- [Session Continuity](docs/SESSION-CONTINUITY.md)
- [Capability Matrix](docs/CAPABILITY-MATRIX.md)

### Runtime Debugging

- [Tracing](docs/TRACING.md)
- [Debugging](docs/DEBUGGING.md)
- [Runbook](docs/RUNBOOK.md)

## Troubleshooting

### Models not showing up

- Verify the runtime server is running:
  - Ollama: `http://127.0.0.1:11434`
  - LM Studio: `http://127.0.0.1:1234`
- Check environment-variable overrides
- Restart CopeNet after changing endpoints

### Debugging a weird run

- Enable tracing: `COPNET_TRACE=1 uv run copenet`
- Reproduce the run once
- Open the newest file under `~/.copenet/logs/runs/`
- Inspect the event order:
  - `harness_planned`
  - `tool_requested`
  - `tool_executed` or `tool_blocked`
  - `assistant_finalized`

See [`docs/TRACING.md`](docs/TRACING.md) for the trace schema and workflow.

### Prompt/profile changes not applying

- Start a new session after changing profile/task mode
- Ensure preset markdown files are in the correct preset directories

### Port already in use

```bash
COPNET_PORT=17124 uv run copenet
```

## Project Status

CopeNet is actively evolving, but it is already a real operator workspace: persistent sessions, local-provider support, workflow surfaces, observability, and mobile-friendly remote access are all in place.

The direction is simple: make local agent systems inspectable, composable, and actually useful for real workflows.
