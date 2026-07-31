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
3. Choose profile + Access
4. Send your first prompt

After first send, provider/profile/persona/workspace remain locked. The operator may
change model within the same provider and may change Access; each run records what it
actually used. See [SESSION-CONTINUITY.md](SESSION-CONTINUITY.md).

## 6) Recommended production-ish baseline

CopeNet's file-backed stores support concurrent operations from threads, tasks,
and multiple store instances inside one server process. Run exactly one CopeNet
writer process per persistence workspace. Multiple Uvicorn workers, independent
hosts, or containers must not share the same `COPNET_DATA_DIR` (or default
`~/.copenet` directory). Multi-process writers require migration to SQLite or
another transactional store; file locking across processes and network
filesystems is not a supported deployment mode.

```bash
umask 077
printf 'COPNET_TOKEN="%s"\nCOPNET_PORT=17123\n' \
  "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" > .copenet.env
uv run --env-file .copenet.env copenet
```

For a private tailnet bind:

```bash
COPNET_HOST=tailscale uv run --env-file .copenet.env copenet
```

## Common gotchas

- **No models listed**: local runtime server not running or wrong base URL.
- **Profile change didn’t apply**: create a new chat session.
- **Port conflict**: change `COPNET_PORT`.
- **Codex provider unavailable**: Codex CLI not installed/authenticated.
- **Tailnet launch refuses `dev-token`**: put a random `COPNET_TOKEN` in the
  gitignored root `.copenet.env` and use `uv run --env-file .copenet.env`.
- **Remote UI says unauthorized**: enter the `.copenet.env` token in the authentication
  banner. CopeNet stores it only in that browser and reconnects. Never put it in
  a shared URL.

## Useful commands

```bash
# Build the React UI first. Without frontend/dist, the host returns 503 at /.
# Run this before packaging a wheel so the production UI is included.
cd src/copenet/host/frontend && npm ci && npm run build && cd -

# Full app (only `copenet` and `copenet-browser-demo` entry points exist)
uv run copenet

# Run with a custom port
COPNET_PORT=17124 uv run copenet

# Point full-access file/shell tools at a specific workspace root
# (defaults to the directory you launched from)
COPNET_WORKDIR=/path/to/project uv run copenet
```
