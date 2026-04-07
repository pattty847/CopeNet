# CopeNet Capability Matrix

This is the current provider/runtime capability matrix. It should be updated whenever provider behavior changes.

| Provider | Model Listing | Model Selection | Streams Deltas | Resume Support | Tool Loop | Auth Expectation | Local / Offline | Structured Output Reliability |
|---|---|---:|---:|---:|---:|---|---|---|
| `codex-cli` | No | Provider-managed | Yes | Yes | Yes | Codex CLI installed and authenticated | No | High for CopeNet prompted tool use |
| `lm-studio` | Yes | Yes | Yes | No | No today | LM Studio local server running | Yes | Medium; model-dependent |
| `ollama` | Yes | Yes | Yes, but may batch into one chunk | No | No today | Ollama daemon running | Yes | Medium; model-dependent |

## Notes

### `codex-cli`

- richest current execution path
- reference backend for tool-enabled turns
- not local-first in the same way as LM Studio / Ollama
- model selection is not currently exposed through this adapter

### `lm-studio`

- local HTTP runtime using an OpenAI-style API surface
- can expose both chat and embedding models
- good fit for private/local interactive use
- currently chat-only in CopeNet’s harness unless prompted tool use is added later

### `ollama`

- local HTTP runtime
- model metadata is available through `/api/tags`
- delta streaming behavior may appear coarser than LM Studio
- currently chat-only in CopeNet’s harness unless prompted tool use is added later

## Meaning Of “Tool Loop”

In this matrix, “Tool Loop” means the provider currently participates in CopeNet’s one-step tool-enabled turn path, not just that the underlying model might be able to follow tool instructions in principle.

## Meaning Of “Structured Output Reliability”

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
