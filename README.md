![CopeNet Market Intelligence — a retro 1990s book-fair cover with a kid at a computer, planets, and a brighter tomorrow](docs/imgs/copenet-book-fair-banner.png)

# CopeNet

CopeNet is a *continuity engine* agent operator for people who want more than a chat box. It gives you a persistent workspace for running local and CLI-backed models, inspecting what they actually did, and turning useful sessions into repeatable workflows.

## Product Tour

CopeNet keeps the operator surface compact: start from Home, work with agents, investigate markets, and inspect the evidence behind every run. The full catalog lives in the [Feature Glossary](docs/FEATURE-GLOSSARY.md).

### Home

Home is the launchpad for active sessions, provider health, recent work, quick actions, market context, and system status.

![CopeNet Home Dashboard](docs/imgs/copenet-home-dashboard.png)

### Agents

Agents keeps persistent conversations beside their runtime context. Provider, model, profile, persona, Access, tools, and retained evidence stay visible instead of disappearing behind the answer.

![CopeNet Agents Console](docs/imgs/copenet-agents-console.png)

### Market

Market is a sectioned research workstation rather than a wall of tickers. The daily brief combines watchlists, SEC evidence, rotation, accumulation signals, macro context, and an accountable forward ledger.

![CopeNet Market Monitor](docs/imgs/market-briefing.png)

### Ticker workspace

Each ticker opens a chart-first workspace for price history, filings, financial overlays, alerts, comparisons, position context, and scoped agent research.

![CopeNet ticker workspace](docs/imgs/market-ticker-workspace.png)

### Observability

Observability reconstructs the work behind a response: model input, provider metadata, tool arguments and results, reasoning provenance, final output, usage, and the raw trace.

![CopeNet Observability run inspector](docs/imgs/copenet-observability-run-inspector.jpg)

## Why CopeNet

CopeNet started as a local-only project — small models on-device, no cloud dependency. That fell apart fast: small local models can't reliably plan multi-step tool use or hold an operator workflow together, so CopeNet grew a CLI-backed and subscription-backed provider layer (`claude-cli`, `openai-codex`) and, in September 2026, dropped the local runtimes entirely. Local-first is still the posture — sessions, transcripts, and control stay on your machine — but the models doing the reasoning are frontier-capable.

Most local AI tools stop at “send a prompt, get a reply.” CopeNet is built for the workflows that happen after that:

- **Operate locally**: keep models, transcripts, and sensitive context close to your machine
- **Inspect runs**: see traces, tool activity, runtime drift, and session state instead of guessing
- **Reuse workflows**: move from one-off chats to repeatable operator surfaces
- **Compare runtimes**: lock sessions to provider/model combinations so behavior stays explainable
- **Extend without cloud lock-in**: add prompts, tools, workflows, and knowledge sources without giving up local control

## What You Can Do

CopeNet is evolving into an operator workspace, not just a chat client. Today it already supports:

- **Agent sessions** with persistent transcripts, first-send runtime binding (provider/profile lock; model + Access changeable mid-session), archive/restore, and inline tool execution
- **Fleet rooms** where ChatGPT and Claude independently research the same question, share evidence receipts after reveal, and critique each other in attributed follow-up turns
- **Observability** with a per-run timeline, provider reasoning provenance, exact tool evidence, model-input snapshots, and raw local traces
- **Workflow surfaces** such as `Meme Lab`, built on top of a stateless ideation API for structured generation
- **Media imports** for transcription and download-first workflows, including mobile-friendly remote use over Tailscale
- **Experiments** for comparing provider/model behavior across real runs
- **Profile + Access layering**: behavioral Profiles (markdown presets) plus a separate **Read-only · Ask · Full Access** permission axis with operator approvals and a persisted shell allowlist
- **Market Monitor**: a daily model-generated brief backed by live SEC filings, sector rotation, and a pre-registered forward ledger that scores its own calls

## Providers

CopeNet runs two frontier lanes through one shared harness:

- `claude-cli` — local `claude` CLI subprocess
- `openai-codex` — OpenAI Codex via OAuth (`uv run copenet auth login --provider openai-codex`)

The goal is provider-agnostic operator tooling: one workspace, multiple runtimes, consistent session semantics. See [`docs/CAPABILITY-MATRIX.md`](docs/CAPABILITY-MATRIX.md) for tool-loop and feature support per provider.

## Quickstart

### 1) Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ and npm

You do **not** need a model provider or the separate CopeTech-Edgar repository
before installing. CopeNet starts first, then Home walks you through either OpenAI
Codex OAuth or Claude CLI setup.

### 2) Install dependencies

```bash
git clone https://github.com/pattty847/CopeNet.git
cd CopeNet
./scripts/setup.sh
```

That one command installs the Python environment, installs the frontend packages,
and builds the UI. To include SEC filings, fundamentals, and insider evidence in
Market, use `./scripts/setup.sh --with-sec`. The optional package is fetched from
GitHub; no sibling checkout is required. Market charts and price data still work
without it.

### 3) Run CopeNet

```bash
uv run copenet
```

Open the desktop UI at:

- `http://127.0.0.1:17123`

On first launch, the Home page shows provider readiness:

- **OpenAI Codex:** choose **Start OpenAI OAuth** and finish in the browser.
- **Claude CLI:** install `claude` if it is missing, then run `claude auth login`.

You only need one ready provider to create a chat. The terminal equivalents are:

```bash
uv run copenet auth login --provider openai-codex
claude auth login
```

### 4) Optional: open it remotely on your own devices

CopeNet also works well over your tailnet for private mobile access:

```bash
# One-time setup: keep a random token in the dedicated, gitignored host env file.
umask 077
printf 'COPNET_TOKEN="%s"\nCOPNET_PORT=17123\n' \
  "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" > .copenet.env

# Launch on this Mac's Tailscale IPv4 only (not every local network interface).
COPNET_HOST=tailscale uv run --env-file .copenet.env copenet
```

Then open it from another device using your Tailscale hostname or tailnet IP. When
the authentication banner appears, enter the same token once; CopeNet stores it
only in that browser and reuses it on later visits. Do not embed the token in a
shared URL.

## Local Setup Notes

1. Run `./scripts/setup.sh` once.
2. Run `uv run copenet`.
3. Open Home and finish setup for at least one provider.
4. Create a new session and pick provider, model, profile, and Access.
5. Send the first message to create the session and lock provider/profile/persona/workspace.

The operator may change model within the same provider and may change Access on later
runs. Start a new chat for another provider, profile, persona, or workspace.

## Configuration

Environment variables:

- `COPNET_HOST` (default: `127.0.0.1`)
- `COPNET_PORT` (default: `17123`)
- `COPNET_TOKEN` (default: `dev-token` on loopback only; a private token is required beyond localhost)
- `COPNET_DATA_DIR` (default: `~/.copenet/sessions`)
- `COPNET_EXECUTION_MODE` (`safe` | `tools-enabled` | `unrestricted`)
- `COPNET_TRACE` (`1` to enable per-run JSONL traces)
- `COPNET_MEME_KB_ROOT` (optional local knowledge-library root for Meme Lab extensions)
- `COPNET_MEME_KB_CACHE_DIR` (optional cache directory for generated knowledge indexes)

Example:

```bash
umask 077
printf 'COPNET_TOKEN="%s"\nCOPNET_PORT=17123\n' \
  "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" > .copenet.env
uv run --env-file .copenet.env copenet
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
- **Access overlay** for runtime authority (`none`, `ask`, or `full-access`)

Add your own by dropping `.md` files into those directories.

## CLI Entry Points

- Full app (recommended):

```bash
uv run copenet
```

- Direct module entrypoint (normally unnecessary):

```bash
python -m copenet.host
```

## Python Usage

```python
from copenet import GatewayClient, GatewayConfig, Orchestrator, CopeNetWsServer
```

## Docs

### Getting Started

- [Feature Glossary](docs/FEATURE-GLOSSARY.md)
- [Startup](docs/STARTUP.md)
- [Testing](docs/TESTING.md)
- [Knowledge Bases](docs/KNOWLEDGE-BASES.md)

### Architecture

- [Architecture](docs/ARCHITECTURE.md)
- [App API](docs/APP-API.md) — `/api/v1` REST + SSE for external apps
- [Event Contract](docs/EVENT-CONTRACT.md) — `/ws` frame protocol
- [Session Continuity](docs/SESSION-CONTINUITY.md)
- [Capability Matrix](docs/CAPABILITY-MATRIX.md)
- [Operator UX Model](docs/OPERATOR-UX-MODEL.md) — three-layer tool truth (transcript / activity / inspector)

### Runtime Debugging

- [Tracing](docs/TRACING.md)
- [Debugging](docs/DEBUGGING.md)
- [Runbook](docs/RUNBOOK.md)

### Prototypes & Investigations

- [Browser Agent Prototype](docs/BROWSER-AGENT-PROTOTYPE.md)

## Troubleshooting

### Provider unavailable

- Check the provider setup panel on Home first; it shows whether each provider is
  missing, signed out, or ready.
- `claude-cli`: install Claude Code so `claude` is on PATH, then run `claude auth login`.
- `openai-codex`: use **Start OpenAI OAuth** on Home, or run
  `uv run copenet auth login --provider openai-codex`.
- SEC-backed Market data missing: rerun `./scripts/setup.sh --with-sec`. A separate
  CopeTech-Edgar checkout is not required.

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

- Start a new session after changing the profile of a locked session
- Change Access explicitly in the runtime control; it applies to the next run
- Ensure preset markdown files are in the correct preset directories

### Port already in use

```bash
COPNET_PORT=17124 uv run copenet
```

## Project Status

CopeNet is actively evolving, but it is already a real operator workspace: persistent sessions, local-provider support, workflow surfaces, observability, and mobile-friendly remote access are all in place.

The direction is simple: make local agent systems inspectable, composable, and actually useful for real workflows.
