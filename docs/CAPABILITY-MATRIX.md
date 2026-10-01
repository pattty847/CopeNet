# CopeNet Capability Matrix

Provider/runtime capabilities as of 2026-09-13. Update it whenever provider behavior changes.

| Provider       | Model Listing | Model Selection | Streams Deltas | Resume Support | Tool Loop                                   | Auth Expectation                                           | Full Access |
|----------------|---------------|-----------------|----------------|----------------|---------------------------------------------|------------------------------------------------------------|-------------|
| `openai-codex` | Yes (static)  | Yes             | Yes            | No (full replay each turn) | CopeNet native Responses loop (`tool_loop_responses.py`) | OAuth via `uv run copenet auth login --provider openai-codex` | Yes |
| `claude-cli`   | Yes (static)  | Yes             | Yes            | Yes (`--resume`) | CopeNet prompted loop (`tool_loop_prompted.py`) over `claude -p --tools ""` | `claude` CLI on PATH and authenticated | Yes |

## Notes

### `openai-codex`

- OAuth-backed subscription runtime; auth state lives in `core/provider_auth/openai_codex.py`
- the primary lane: CopeNet owns the input array, the tool schemas, the loop, and the trace, so this is where harness work is measured first
- exposes an `auth_service` for the `providerAuth.*` RPCs (status / beginLogin / completeLogin / logout)
- provider-reported token usage per model call lands in the run record

### `claude-cli`

- subprocess adapter against Claude Code via `claude -p`; supported model ids are pinned in `providers/claude_cli.py`
- Claude Code's built-in tools are disabled (`--tools ""`) and settings sources isolated, so CopeNet remains the tool and permission authority
- conversation continuity uses Claude's own session resume; Claude Code's internal context compaction runs on its side, invisible to CopeNet's trace

### `lm-studio`

- local models over LM Studio's OpenAI-compatible `/v1/responses`, so it runs on the same Responses tool loop as `openai-codex` (function tools, `function_call_output` replay, activity titles, `tools.load`, provider-reported usage)
- the server may live on another machine: `COPNET_LM_STUDIO_BASE_URL` (default `http://127.0.0.1:1234`), with LM Studio's Serve on Local Network turned on
- the model list comes from LM Studio's native `/api/v1/models`; a loaded model's budget uses the context it was LOADED with (LM Studio defaults to 4096), not the architecture maximum — load coding models with 16K+ or tool turns drop history
- `reasoning` and `prompt_cache_key` are not sent: both are model- or vendor-specific and would be guesses on an arbitrary local model
- Access is the only gate, same as the other lanes

## Removed lanes

`ollama` (local HTTP runtime), the Chat Completions tool loop that served it and the old `lm-studio` adapter, and `codex-cli` (Codex CLI subprocess) were removed. LM Studio came back on the Responses loop; `codex-cli` was superseded by the OAuth lane. Git history keeps the adapters.
