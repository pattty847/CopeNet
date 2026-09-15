# CopeNet Startup Guide

A practical bring-up checklist for running CopeNet on a fresh machine.

## 1) Install prerequisites

- Python 3.12+
- `uv` package manager
- Node.js 20+ and npm

Provider setup happens after CopeNet starts. You do not need Claude CLI, OpenAI
OAuth, or a CopeTech-Edgar checkout to install the core app.

## 2) Clone + install

```bash
git clone <your-repo-url>
cd CopeNet
./scripts/setup.sh
```

The script installs Python and frontend dependencies and builds the UI in the
required order. Use `./scripts/setup.sh --with-sec` to add SEC filings,
fundamentals, and insider evidence. It fetches the optional package directly;
there is no required sibling repository.

## 3) Start CopeNet and connect a provider

```bash
uv run copenet
```

Open `http://127.0.0.1:17123`. The Home page presents both supported paths and
their live readiness state:

- **OpenAI Codex:** click **Start OpenAI OAuth** and finish in the browser.
- **Claude CLI:** install Claude Code if needed, then run `claude auth login`.

Only one provider needs to be ready. Terminal-only OpenAI setup remains available:

```bash
uv run copenet auth login --provider openai-codex
```

## 4) Run CopeNet

CopeNet is already running from step 3. Return to the same command for later launches.

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

- **Provider unavailable**: Home shows the exact missing install or login step.
- **SEC evidence unavailable**: run `./scripts/setup.sh --with-sec`; core chat and
  price/chart features do not require it.
- **Profile change didn’t apply**: create a new chat session.
- **Port conflict**: change `COPNET_PORT`.
- **Tailnet launch refuses `dev-token`**: put a random `COPNET_TOKEN` in the
  gitignored root `.copenet.env` and use `uv run --env-file .copenet.env`.
- **Remote UI says unauthorized**: enter the `.copenet.env` token in the authentication
  banner. CopeNet stores it only in that browser and reconnects. Never put it in
  a shared URL.

## Useful commands

```bash
# Repeatable full setup (Python + frontend build)
./scripts/setup.sh

# Include optional SEC-backed Market features
./scripts/setup.sh --with-sec

# Full app (only `copenet` and `copenet-browser-demo` entry points exist)
uv run copenet

# Run with a custom port
COPNET_PORT=17124 uv run copenet

# Point full-access file/shell tools at a specific workspace root
# (defaults to the directory you launched from)
COPNET_WORKDIR=/path/to/project uv run copenet
```
