# CopeNet Startup Guide

A practical bring-up checklist for running CopeNet on a fresh machine.

## 1) Install prerequisites

- Python 3.11+
- `uv` package manager
- Optional local model runtimes:
  - Ollama
  - LM Studio (local server mode)
- Optional Codex CLI (for `codex-cli` provider)

## 2) Clone + install

```bash
git clone <your-repo-url>
cd CopeNet
uv sync
```

## 3) Start local runtimes (optional but recommended)

- Ollama endpoint default: `http://127.0.0.1:11434`
- LM Studio endpoint default: `http://127.0.0.1:1234`

If you use non-default ports, set env vars before launch:

```bash
export COPNET_OLLAMA_BASE_URL="http://127.0.0.1:11434"
export COPNET_LM_STUDIO_BASE_URL="http://127.0.0.1:1234"
```

## 4) Run CopeNet

```bash
uv run copenet
```

Open:

- `http://127.0.0.1:17123`

## 5) First-run flow in UI

1. Click **New Chat**
2. Choose provider + model
3. Choose profile + task mode
4. Send your first prompt

After first send, runtime/model/profile/task mode are treated as locked for that session.

## 6) Recommended production-ish baseline

```bash
export COPNET_HOST="127.0.0.1"
export COPNET_PORT="17123"
export COPNET_TOKEN="set-a-real-token"
uv run copenet
```

## Common gotchas

- **No models listed**: local runtime server not running or wrong base URL.
- **Profile change didn’t apply**: create a new chat session.
- **Port conflict**: change `COPNET_PORT`.
- **Codex provider unavailable**: Codex CLI not installed/authenticated.

## Useful commands

```bash
# Build the React UI first (the host serves frontend/dist; without it you
# silently get the legacy vanilla fallback UI from host/static/).
cd src/copenet/host/frontend && npm install && npm run build && cd -

# Full app (only `copenet` and `copenet-browser-demo` entry points exist)
uv run copenet

# Run with a custom port
COPNET_PORT=17124 uv run copenet

# Point full-access file/shell tools at a specific workspace root
# (defaults to the directory you launched from)
COPNET_WORKDIR=/path/to/project uv run copenet
```
