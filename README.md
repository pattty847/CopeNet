# CopeNet

Local agent gateway: orchestrator, providers, WebSocket RPC, session and transcript storage. Wrapper for CLI AI agents (e.g. Codex) with a web UI.

- **Host**: FastAPI + WebSocket RPC server (`/ws`) and web UI at `/`
- **Orchestrator**: session resolution, provider execution, event fanout
- **Providers**: e.g. Codex CLI adapter
- **Sessions**: JSON/JSONL session index and transcript store
- **Client**: `GatewayClient` for talking to a CopeNet gateway from Python

## Setup (uv)

From the project root:

```bash
uv sync
```

This creates a venv and installs the package. No global install needed.

## Run

```bash
cope
```

Or with uv (no need to activate the venv):

```bash
uv run cope
```

Then open **http://127.0.0.1:17123** in a browser. The UI lets you pick a session, send messages, and stream replies from the agent.

Backend-only (no UI): `uv run copenet-host` or `python -m copenet.host`.

## Config

- **Host / port**: `COPNET_HOST`, `COPNET_PORT` (default `127.0.0.1:17123`)
- **Auth**: `COPNET_TOKEN` (default `dev-token`; set in prod)
- **Sessions**: `COPNET_DATA_DIR` or `~/.copenet/sessions` (created on first run)
- **Codex execution**: `COPNET_EXECUTION_MODE` — `safe` | `tools-enabled` | `unrestricted`

## System prompts

The UI lets you pick a **system prompt preset** so the model gets instructions before your message. Presets live in the repo under `src/copenet/prompts/presets/` as `.md` files:

- **default** – General-purpose coding assistant.
- **code-review** – Focus on review and actionable feedback.
- **refactor** – Refactoring with behavior preserved.

To add a preset: create `src/copenet/prompts/presets/your-id.md`. The first line can be a `# Title` (shown in the UI); the rest is the system prompt text. The backend sends it to the provider as `system_prompt + "\n\n---\n\n" + your_message`.

## Use from Python

```python
from copenet import GatewayClient, GatewayConfig, Orchestrator, CopeNetWsServer
```
