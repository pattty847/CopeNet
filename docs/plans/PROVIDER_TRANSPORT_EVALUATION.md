# Provider Transport Evaluation

Status: decision memo
Date: 2026-07-25
Scope: Claude subscription transport and OpenAI Codex subscription transport

## Executive recommendation

The two providers should not receive the same migration treatment.

- **Claude:** prototype a migration from raw `claude -p` subprocess handling to
  the Python Claude Agent SDK. Keep it in a strict transport-only configuration:
  CopeNet supplies the system prompt, CopeNet owns tools and policy, built-in
  Claude tools are disabled, and filesystem settings/memory are disabled. This
  is intended to be a low-semantic-change migration, subject to a shadow proof.
  Its immediate benefits would be typed events/results, typed transport errors,
  and pinned CLI compatibility. A later stateful-client phase could also add
  explicit interruption and detailed context telemetry.
- **OpenAI:** do not replace the current `openai-codex` adapter with Codex SDK or
  app-server as if they were equivalent transports. The current adapter is a raw
  Responses-style model transport controlled by CopeNet. Codex SDK/app-server is
  a complete coding-agent runtime with its own threads, instructions, tools,
  approvals, persistence, and compaction. Evaluate it as a separate provider
  mode or specialist, not a transparent backend swap.
- **OpenAI long-term supportability:** a public Responses API adapter using an
  API key is the supported equivalent of CopeNet's current raw transport, but it
  uses API billing rather than the ChatGPT subscription. The current custom
  OAuth + ChatGPT backend adapter can remain useful for personal subscription
  use, but should be labeled experimental and protected by contract probes
  because its endpoint and auth contract are not the documented public API.

No live paid/subscription prompts were spent for this evaluation.

## What CopeNet does today

### Claude

`ClaudeCliProvider` starts `claude -p` with:

- `--output-format stream-json`
- `--system-prompt <CopeNet prompt>`
- `--tools ""`
- `--setting-sources=`
- an explicit model
- `--resume <provider_session_id>` after the first turn

That last point corrects an important assumption: **CopeNet does not reconstruct
the entire Claude conversation on every turn once it has a Claude session ID.**
The first request starts a Claude session. Later requests send the new prompt
and resume Claude's persisted conversation.

CopeNet parses JSONL text and session IDs itself. Claude's native tools,
filesystem settings, and `CLAUDE.md` context are deliberately disabled. CopeNet
uses its provider-agnostic prompted tool protocol and owns the tool loop.

### OpenAI Codex

`OpenAICodexProvider` currently:

- implements browser OAuth and token refresh inside CopeNet;
- sends the ChatGPT access token to
  `https://chatgpt.com/backend-api/codex/responses`;
- sends a Responses-style request with `store: false`;
- supplies CopeNet instructions, a reconstructed and budgeted transcript
  history, and tool schemas;
- receives native function calls, lets the CopeNet harness execute them, and
  posts function-call outputs back to the model.

This gives CopeNet strong ownership of context, tools, policy, transcripts, and
provider parity. It also means CopeNet owns an integration against an
undocumented ChatGPT backend endpoint and a custom OAuth flow.

The public Responses API supports both manual `store: false` history replay and
server-managed continuation. OpenAI's documentation explicitly shows replaying
all response output items when manually managing state, and also supports
`previous_response_id` or durable Conversation objects. These public API
surfaces use Platform authentication and billing.

CopeNet does not currently preserve every raw Responses output item. It carries
assistant text, function calls, and function outputs, but normally does not
request/replay encrypted reasoning and does not retain opaque compaction or
unknown future item types. A public Responses provider therefore requires a
canonical raw-item persistence/replay lane; it is not merely an endpoint and
authentication swap.

## Claude: CLI versus Agent SDK

### What the SDK actually is

The Claude Agent SDK is a programmatic wrapper around the Claude Code runtime,
not a separate low-level inference API. The Python package bundles a compatible
Claude CLI, exposes typed message/content/error objects, and provides both:

- `query()` for one-shot process-style requests, including session resume; and
- `ClaudeSDKClient` for a live bidirectional conversation with interruption and
  runtime control.

Anthropic's current SDK controls can reproduce CopeNet's context goals, but its
defaults are not sufficiently isolated:

- no Claude Code system prompt unless explicitly selected;
- `tools=[]` disables all built-in tools;
- `setting_sources=[]` explicitly disables filesystem setting sources.
- `strict_mcp_config=True` prevents project, user, and plugin MCP servers from
  being loaded outside the supplied SDK configuration;
- `skills=[]` suppresses skills rather than relying on CLI defaults.

The stateful SDK client also exposes context usage by category,
total/effective/raw context limits, autocompaction information, typed usage
data, and explicit interruption. Those are not all available from the simpler
one-shot `query()` interface.

### Subscription behavior

As of 2026-07-25, Anthropic says its previously announced separation of
programmatic usage is paused: Claude Agent SDK, `claude -p`, and third-party app
usage all still draw from the user's subscription usage limits. Therefore:

- changing to the SDK does not currently change subscription eligibility;
- staying on `claude -p` is not currently a billing workaround;
- `ANTHROPIC_API_KEY` must remain unset when subscription usage is intended,
  because Claude Code prioritizes that key and switches to API billing.

This policy is explicitly temporary and must be rechecked before a release that
depends on subscription-backed third-party usage.

### Decision matrix

| Concern | Current `claude -p` | Claude Agent SDK |
|---|---|---|
| Subscription usage today | Supported | Supported |
| Session continuation | `--resume` | Typed resume/session APIs |
| Prompt isolation | Explicit CLI flags | First-class options/defaults |
| CopeNet-owned tools | Yes, prompted protocol | Yes, with `tools=[]` |
| Event parsing | Hand-written JSONL parser | Typed messages/content blocks |
| Errors and cancellation | Process/runner level | Typed transport errors; explicit interrupt with stateful client |
| Context telemetry | Not currently exposed | Detailed context/autocompact usage with stateful client |
| Runtime compatibility | Installed CLI can drift | Package pins a compatible CLI |
| Operational complexity | Small, already working | New dependency and async lifecycle |
| Risk of duplicate harness | Low | Low if transport-only; high if SDK tools/hooks are enabled |

### Claude recommendation

Move toward the SDK, but do it because it improves the adapter contract—not
because it should produce better answers or use a different subscription pool.

Start with `query()` plus `resume`, because that matches the existing
one-process-per-turn lifecycle and minimizes change. Configure:

```python
ClaudeAgentOptions(
    model=model,
    system_prompt=system_prompt,
    tools=[],
    setting_sources=[],
    strict_mcp_config=True,
    mcp_servers={},
    skills=[],
    plugins=[],
    resume=provider_session_id,
)
```

Do not initially enable Claude Code's system prompt, built-in tools, MCP
servers, plugins, skills, hooks, subagents, or filesystem memory. Those would
create a second harness inside CopeNet. Explicitly detect or scrub an inherited
`ANTHROPIC_API_KEY` and make the active billing/auth source visible; an empty SDK
`env` option must not be assumed to remove variables inherited by the child
process.

The adapter must map both exception failures and error-bearing `ResultMessage`
values into CopeNet provider failures. Catching only SDK exceptions would miss
model/API failures represented as terminal result data.

Consider a long-lived `ClaudeSDKClient` later only if measured startup latency,
interruption, or live context telemetry justifies the added responsibility of
mapping CopeNet sessions to resident client processes and recovering them after
host restarts.

## OpenAI: raw Responses versus Codex SDK/app-server

### These are different abstraction levels

The official Codex SDK controls local Codex agents. The Python SDK controls
Codex app-server over JSON-RPC and ships a pinned Codex runtime. App-server
owns:

- persisted threads, resume, fork, and compaction;
- base and developer instructions;
- model and working-directory state;
- sandbox and approval policy;
- built-in tools, MCP, dynamic tools, and tool-result events;
- account login and ChatGPT subscription state.

This is attractive for a Codex-native experience. It is not a transparent
replacement for a provider adapter whose job is to expose model generation and
function calls to the CopeNet harness.

App-server does offer useful integration points. It supports custom
`baseInstructions` and `developerInstructions`, and experimental
`dynamicTools`. It also provides an officially managed ChatGPT browser/device
login and reports the user's plan. These features make a proof of concept
worthwhile, but they do not remove Codex's own agent loop or built-in runtime
semantics. Supplied instructions also do not guarantee a sterile prompt:
app-server can report automatically loaded instruction-file sources, which must
be audited and isolated in the proof.

### Authentication and billing boundary

OpenAI documents:

- ChatGPT login for subscription access in Codex clients;
- API-key login for usage-based Codex access;
- app-server account methods for official ChatGPT browser/device login;
- Platform API keys for general OpenAI API calls.

OpenAI specifically directs general API calls to Platform API keys. It does not
document the current CopeNet pattern—using a consumer ChatGPT OAuth token
directly against the ChatGPT Codex Responses backend—as a public third-party
Responses API authentication method.

That does not prove the current adapter is prohibited. It does mean its protocol
is private, has a larger compatibility/support risk, and should not be described
as the official OpenAI API integration. CopeNet also owns the copied OAuth
client configuration, token refresh/rotation, and JSON credential storage,
whereas official Codex clients own refresh and can use the OS credential store.

### Decision matrix

| Concern | Current custom OAuth Responses | Public Responses API | Codex SDK/app-server |
|---|---|---|---|
| Billing | ChatGPT subscription | Platform usage | ChatGPT subscription or API key |
| Publicly documented transport | No | Yes | Yes |
| CopeNet owns context | Yes | Yes | Shared/mostly Codex-owned |
| CopeNet owns tool loop | Yes | Yes | Codex owns agent loop; custom tools are integration points |
| Provider parity | Strong | Strong | Weak: Codex-specific semantics |
| Session state | CopeNet replay, `store:false` | Replay, response chain, or Conversation | Codex threads/rollouts |
| Prompt control | Direct instructions/input | Direct instructions/input | Base/developer instructions plus Codex runtime context |
| Built-in compaction | No | Available, but opaque items must be preserved | Yes |
| Auth maintenance | CopeNet owns OAuth/refresh | Official SDK/API key | Official Codex auth |
| Endpoint drift risk | High | Low | Medium; high for experimental dynamic-tool parity |
| Best role | Personal experimental raw provider | Supported raw provider | Codex specialist/full agent provider |

### OpenAI recommendation

Do not perform an in-place SDK migration of `openai-codex`.

Use three explicit product concepts:

1. **`openai-codex` compatibility transport:** retain the current
   subscription-backed raw adapter, label it experimental, and keep deterministic
   request/response contract tests around it. Never log authorization headers or
   token payloads; probe token rotation, logout/revocation, account switching,
   static model-catalog drift, endpoint shape, and SSE event drift.
2. **OpenAI API transport:** eventually add the official public Responses API
   for users who prefer supported Platform authentication and usage billing.
   This is the architectural peer of the current adapter, but it must preserve
   and replay reasoning, compaction, phase, and unknown future output items—or
   use a server-managed response chain with an explicit retention decision.
3. **Codex agent provider:** prototype app-server separately for users who want
   the official subscription-backed Codex runtime. Treat it as a specialist with
   Codex-owned threads and agent behavior, not as a generic model provider.

CopeNet should not silently merge Codex's stored thread with CopeNet's replayed
transcript. Pick one model-context owner per provider mode. CopeNet should still
capture live Codex events in its append-only audit transcript because
app-server's reconstructed thread-item views may omit interactions.

## Validation plan

### Claude SDK shadow adapter

Run the existing deterministic provider and prompt matrix first, then perform a
small live A/B using a fresh session for each transport:

1. first-turn system prompt and no hidden filesystem settings;
2. same-session follow-up and restart/resume;
3. cross-transport resume from a session created by the installed raw CLI into
   the SDK's bundled CLI;
4. prompted CopeNet tool request and tool-result continuation;
5. cancellation during streaming;
6. invalid/expired session behavior;
7. long-chat context usage and autocompaction telemetry;
8. authentication with `ANTHROPIC_API_KEY` deliberately absent.

Acceptance criteria:

- equivalent visible answers and tool behavior;
- no Claude built-in tool calls or filesystem prompt injection;
- stable CopeNet `provider_session_id` mapping across restart;
- existing raw-CLI sessions either resume correctly or remain explicitly pinned
  to the legacy transport—never silently restart;
- no new duplicate transcript/history;
- exception and error-result failures remain actionable;
- context usage can be attached to run traces without exposing hidden reasoning.

### Codex app-server proof of concept

Keep this outside the production provider path initially. Probe:

1. official ChatGPT login reuse and automatic refresh;
2. exact effective prompt with custom base/developer instructions, reported
   `instructionSources`, an isolated `CODEX_HOME`, and controlled user/project
   configuration and workspace instruction loading;
3. whether built-in tools can be fully suppressed;
4. mapping CopeNet tool schemas through experimental dynamic tools;
5. whether CopeNet can execute a dynamic tool and return its result without
   surrendering policy authority;
6. thread resume after CopeNet restart;
7. cancellation, compaction, model switching, and event mapping;
8. lossless live audit capture, model-context ownership, and duplicate-history
   behavior.

The proof succeeds only if one of these coherent boundaries emerges:

- Codex is an explicit specialist and owns its entire thread/tool loop; or
- app-server can act as a controlled model transport without hidden tools,
  duplicated context, or conflicting policy.

If neither is true, keep the current adapter for subscription access and add the
public Responses transport when supported raw integration is needed.

The controlled-transport branch is currently unproven. The generated
`thread/start` schema has no documented `tools=[]` equivalent, and adding
experimental dynamic tools does not itself disable Codex's shell, patch, or MCP
capabilities. Prompting the model not to use those tools is not policy
enforcement. Use the pinned Python SDK over stdio for the proof rather than the
experimental app-server WebSocket transport.

## Sources

### Anthropic

- [Agent SDK subscription policy update](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)
- [Claude Code with Pro or Max](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan)
- [Claude Code API-key precedence](https://support.claude.com/en/articles/12304248-manage-api-key-environment-variables-in-claude-code)
- [Official Claude Agent SDK Python repository](https://github.com/anthropics/claude-agent-sdk-python)
- [Claude Agent SDK changelog](https://github.com/anthropics/claude-agent-sdk-python/blob/main/CHANGELOG.md)
- [Claude Agent SDK Python types](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/types.py)

### OpenAI

- [Codex SDK](https://developers.openai.com/codex/sdk/)
- [Codex app-server](https://developers.openai.com/codex/app-server/)
- [Codex authentication](https://developers.openai.com/codex/auth/)
- [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive/)
- [Responses API conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
- [Responses API compaction](https://developers.openai.com/api/docs/guides/compaction)
