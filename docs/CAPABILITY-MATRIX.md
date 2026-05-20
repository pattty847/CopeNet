# CopeNet Capability Matrix

This is the current provider/runtime capability matrix. It should be updated whenever provider behavior changes.

| Provider        | Model Listing | Model Selection | Streams Deltas              | Resume Support | Tool Loop                | Auth Expectation                                          | Local / Offline | Structured Output Reliability     |
|-----------------|---------------|-----------------|-----------------------------|----------------|--------------------------|-----------------------------------------------------------|-----------------|-----------------------------------|
| `openai-codex`  | Yes (static)  | Yes             | Yes                         | No             | CopeNet prompted tools    | OAuth via `uv run copenet auth login --provider openai-codex` | No          | High                              |
| `codex-cli`     | No            | Provider-managed | Yes                        | Yes            | External Codex harness   | Codex CLI installed and authenticated                     | No              | Provider-managed                   |
| `claude-cli`    | Yes (static)  | Yes             | Yes                         | Yes            | External Claude Code harness | `claude` CLI on PATH and authenticated                 | No              | Provider-managed                   |
| `lm-studio`     | Yes           | Yes             | Yes                         | No             | Yes (native, when exposed) | LM Studio local server running                          | Yes             | Model-dependent                    |
| `ollama`        | Yes           | Yes             | Yes, but may batch into one chunk | No       | No CopeNet-managed loop  | Ollama daemon running                                     | Yes             | Model-dependent                    |

## Notes

### `codex-cli`

- local subprocess adapter for the headless Codex CLI harness
- the Codex CLI brings its own large harness/system prompt and tool semantics
- CopeNet should treat this as a text interface to an external harness, not as the main CopeNet-controlled frontier baseline

### `claude-cli`

- subprocess adapter against Claude Code via `claude -p`; supported model ids are pinned in `providers/claude_cli.py`
- Claude Code manages its own harness behavior; CopeNet treats results as provider events
- requires the user to be already authenticated to Claude Code locally

### `openai-codex`

- OAuth-backed subscription runtime; auth state lives in `core/provider_auth/openai_codex.py`
- this is the preferred frontier baseline for CopeNet-controlled harness comparisons because it uses the subscription endpoint without the Codex CLI harness wrapped around it
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

- `openai-codex` is the preferred OAuth/subscription frontier lane for CopeNet-controlled prompted tool use.
- Compatible local HTTP runtimes use native tool calls when their adapter exposes `chat_completion`.
- `codex-cli` and `claude-cli` are external harness lanes: CopeNet streams their output and should evaluate them separately from CopeNet-controlled tool loops.
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
