# CopeNet Capability Matrix

This is the current provider/runtime capability matrix. It should be updated whenever provider behavior changes.

| Provider        | Model Listing | Model Selection | Streams Deltas              | Resume Support | Tool Loop                | Auth Expectation                                          | Local / Offline | Structured Output Reliability     |
|-----------------|---------------|-----------------|-----------------------------|----------------|--------------------------|-----------------------------------------------------------|-----------------|-----------------------------------|
| `codex-cli`     | No            | Provider-managed | Yes                        | Yes            | Provider-managed         | Codex CLI installed and authenticated                     | No              | Provider-managed                   |
| `claude-cli`    | Yes (static)  | Yes             | Yes                         | Yes            | Provider-managed         | `claude` CLI on PATH and authenticated                    | No              | Provider-managed                   |
| `openai-codex`  | No            | Provider-managed | Yes                        | Provider-managed | Yes (native)           | OAuth via `uv run copenet auth login --provider openai-codex` | No          | High                              |
| `lm-studio`     | Yes           | Yes             | Yes                         | No             | Yes (native, when exposed) | LM Studio local server running                          | Yes             | Model-dependent                    |
| `ollama`        | Yes           | Yes             | Yes, but may batch into one chunk | No       | No CopeNet-managed loop  | Ollama daemon running                                     | Yes             | Model-dependent                    |

## Notes

### `codex-cli`

- richest current execution path
- reference backend for tool-enabled turns
- not local-first in the same way as LM Studio / Ollama
- model selection is not currently exposed through this adapter

### `claude-cli`

- subprocess adapter against the local `claude` CLI; supported model ids are pinned in `providers/claude_cli.py`
- the CLI manages its own tool execution; CopeNet treats results as provider events
- requires the user to be already authenticated to Claude Code locally

### `openai-codex`

- OAuth-backed subscription runtime; auth state lives in `core/provider_auth/openai_codex.py`
- model + session continuity are provider-managed
- exposes an `auth_service` for the `providerAuth.*` RPCs (status / beginLogin / completeLogin / logout)

### `lm-studio`

- local HTTP runtime using an OpenAI-style API surface
- can expose both chat and embedding models
- good fit for private/local interactive use
- uses CopeNet-managed tools only when the adapter exposes native tool calls

### `ollama`

- local HTTP runtime
- model metadata is available through `/api/tags`
- delta streaming behavior may appear coarser than LM Studio
- currently streams through provider passthrough for CopeNet-managed turns

## Meaning Of "Tool Loop"

In this matrix, "Tool Loop" means the provider currently participates in CopeNet's tool-enabled turn path, not just that the underlying model might be able to follow tool instructions in principle.

- `openai-codex` and compatible local HTTP runtimes use native tool calls when their adapter exposes `chat_completion`.
- `codex-cli` and `claude-cli` are provider-managed: CopeNet streams their output and does not run a second tool loop around them.
- Providers without native tool-call support are plain provider passthrough.

## Meaning Of "Structured Output Reliability"

This is a practical judgment for CopeNet integration work:

- `High`: reliable enough to build around for tool invocation / normalized workflows
- `Medium`: usable, but format adherence is model-dependent
- `Low`: likely too inconsistent for normalized harness behavior without extra adaptation

## Future Columns To Add

When relevant, extend this table with:

- web search / grounding
- embeddings execution
- max context window
- branch / thread handoff support
- approval model
- cost / speed notes for operator routing
