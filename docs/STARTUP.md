# CopeNet Startup Guide

A practical bring-up checklist for running CopeNet on a fresh machine.

## 1) Install prerequisites

- Python 3.12+
- Node.js 22+ with npm (frontend build and background indicator alerts)
- Git
- `uv` package manager
- Optional local model runtimes:
  - Ollama
  - LM Studio (local server mode)
- One model provider: CopeNet OpenAI Codex OAuth, an authenticated Claude/Codex CLI, or a running local runtime

## 2) Clone + install

```bash
git clone https://github.com/pattty847/CopeTech-Edgar.git
git clone https://github.com/pattty847/CopeNet.git
cd CopeNet
npm --prefix src/copenet/host/frontend ci
npm --prefix src/copenet/host/frontend run build
uv sync
```

CopeTech-Edgar must be a sibling directory: `pyproject.toml` currently resolves it
from `../CopeTech-Edgar` as an editable dependency. The frontend build creates both
the browser UI and the Node indicator evaluator. Without the built UI, `/` returns 503.

## 3) Configure a provider

For OpenAI Codex through CopeNet's OAuth adapter:

```bash
uv run copenet auth login --provider openai-codex
```

For `claude-cli` or `codex-cli`, install and authenticate the corresponding CLI first.
For local models, start the runtime and load a model:

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

For the chart agent:

1. Open **Market** and search for a ticker.
2. Wait for the chart to load, then select **Agent** beside the chart.
3. Choose a provider and model with chart-tool support.
4. Ask about the chart; use **Inspect context** to review the captured evidence.

Market does not run a broad scan just because the page opened. If data is missing,
use the relevant acquisition control; named scans require reviewing their scope
before running. Missing provider data is shown as unavailable, not replaced by a demo.

For a general agent session, open **Agents**, create a new chat, choose provider,
model, profile and Access, and send a prompt.

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
npm --prefix src/copenet/host/frontend ci
npm --prefix src/copenet/host/frontend run build

# Full app (only `copenet` and `copenet-browser-demo` entry points exist)
uv run copenet

# Run with a custom port
COPNET_PORT=17124 uv run copenet

# Point full-access file/shell tools at a specific workspace root
# (defaults to the directory you launched from)
COPNET_WORKDIR=/path/to/project uv run copenet
```

## Configuration reference

| Variable | Purpose / default |
| --- | --- |
| `COPNET_HOST` | Bind address; `127.0.0.1` by default, or `tailscale` for a private tailnet bind |
| `COPNET_PORT` | Host port; `17123` |
| `COPNET_TOKEN` | `dev-token` is loopback-only; use a private token for remote access |
| `COPNET_DATA_DIR` | Data root override; sessions are stored in its `sessions/` subdirectory (default sessions: `~/.copenet/sessions`) |
| `COPNET_WORKDIR` | Workspace for file/shell tools; launch directory by default |
| `COPNET_TRACE` | Set to `1` to enable debug capture; lifecycle traces are always written |
| `COPNET_LM_STUDIO_BASE_URL` | LM Studio endpoint; `http://127.0.0.1:1234` |
| `COPNET_OLLAMA_BASE_URL` | Ollama endpoint; `http://127.0.0.1:11434` |

For a puzzling run, open **Observability**, enable **Debug capture**, then reproduce
it. Capture applies to subsequent runs. See [TRACING.md](TRACING.md) for retained
content and [DEBUGGING.md](DEBUGGING.md) for the investigation workflow.

Optional calendar and broker configuration lives in [INTEGRATIONS.md](INTEGRATIONS.md).
Knowledge-source overrides and cache settings are in [KNOWLEDGE-BASES.md](KNOWLEDGE-BASES.md).
