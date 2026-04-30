# Notes

## Current State

- Investigation target: Hermes Agent harness behavior
- Reference repo path: `/Users/copeharder/Programming/hermes-agent`
- Date: 2026-04-27

## Observations

- Hermes is not a thin harness. The core agent loop is centralized in `/Users/copeharder/Programming/hermes-agent/run_agent.py`, and it owns continuation, retries, empty-response recovery, tool execution, budget handling, and context compression.
- Hermes uses native OpenAI-style `tools` in its main loop, with provider-specific normalization pushed into transport/adapters like `/Users/copeharder/Programming/hermes-agent/agent/transports/chat_completions.py`.
- Tool surfacing is heavily curated before the model ever sees schemas. `/Users/copeharder/Programming/hermes-agent/model_tools.py` filters by toolset, runtime availability, dynamic schema compatibility, and even strips misleading cross-references from tool descriptions when companion tools are unavailable.
- Hermes leans hard on prompt-level execution discipline. `/Users/copeharder/Programming/hermes-agent/agent/prompt_builder.py` injects tool-use enforcement, model-family-specific operational guidance, memory/session-search guidance, and mandatory skill-loading instructions.
- Hermes's file/tool descriptions actively steer away from cheap shell behavior. `/Users/copeharder/Programming/hermes-agent/tools/terminal_tool.py:736` says not to use `ls`, `cat`, or `grep` when dedicated tools exist. `/Users/copeharder/Programming/hermes-agent/tools/file_tools.py:1026` and `/Users/copeharder/Programming/hermes-agent/tools/file_tools.py:1070` explicitly position `read_file` / `search_files` as the preferred primitives.
- Hermes has at least one explicit anti-repetition hint in its search tool. `/Users/copeharder/Programming/hermes-agent/tools/file_tools.py:980` adds a warning after the same exact search is repeated 3 times consecutively: use the information you already have.
- Comparing repo/file affordances directly: CopeNet's file tools are much thinner. `/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/handlers/files.py:11` exposes `files.list`, `files.read`, and `files.search` with very short descriptions and minimal schema guidance. Hermes's equivalents in `/Users/copeharder/Programming/hermes-agent/tools/file_tools.py:1026` and `/Users/copeharder/Programming/hermes-agent/tools/terminal_tool.py:736` are much more directive about when to use each tool and when *not* to use shell primitives instead.
- CopeNet's `context.prepare` in `/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/handlers/context.py:11` is a compact repo/session bundle, but its description is broad and easy for a weak model to overvalue as evidence. Hermes does not seem to rely on an equivalent single 'prepare context' shortcut in the core loop; it leans more on memory/session-search plus direct tools.
- CopeNet's contract inference already tries to prefer `files.search`, `files.read`, and `context.prepare` in `/Users/copeharder/Programming/CopeNet/src/copenet/core/harness/planning.py:103`, and the follow-up prompts in `/Users/copeharder/Programming/CopeNet/src/copenet/core/harness/tool_loop.py:1004` / `:1107` already say `files.list` usually is not enough. The live Gemma failures show prompt preference alone is not strong enough.
- Hermes has broader agent-system primitives that go beyond CopeNet's current scope but matter for the longer-term 'Jarvis' vision: memory orchestration (`/Users/copeharder/Programming/hermes-agent/agent/memory_manager.py:1`), context compression (`/Users/copeharder/Programming/hermes-agent/agent/context_compressor.py:1`), session recall (`/Users/copeharder/Programming/hermes-agent/tools/session_search_tool.py:531`), delegation (`/Users/copeharder/Programming/hermes-agent/tools/delegate_tool.py:2299`), and scenario-specific toolsets (`/Users/copeharder/Programming/hermes-agent/toolsets.py:1`).
- Hermes has explicit large-tool-output hygiene in `/Users/copeharder/Programming/hermes-agent/tools/tool_result_storage.py:1`: oversized results are persisted to sandbox files and replaced in-context with previews + readback instructions. That keeps the model in a direct inspect/read loop instead of flooding context.
- Hermes's file tools have direct anti-loop behavior, not just passive descriptions. `/Users/copeharder/Programming/hermes-agent/tools/file_tools.py:600` warns on the 3rd identical read and hard-blocks on the 4th; `/Users/copeharder/Programming/hermes-agent/tools/file_tools.py:950` does the same for identical searches. This is extremely relevant to CopeNet's `files.list` / shallow-repeat problem.
- Hermes also resets repetition counters when another tool runs (`notify_other_tool_call`) and tracks file staleness after writes/patches, which means the tool layer itself participates in reasoning hygiene.
- Hermes session continuity is backed by a real SQLite state store with FTS5/trigram search in `/Users/copeharder/Programming/hermes-agent/hermes_state.py:1`, which reinforces the session-search tool and long-lived memory model.
- CopeNet's evidence ledger currently classifies `context.prepare` as grounding in `/Users/copeharder/Programming/CopeNet/src/copenet/core/runtime/turn_state.py:111`. Given our Gemma failures, that classification is likely too generous for repo/code tasks.
- CopeNet's current builtin tool set is still very small and local: registry bootstraps only context/files/git/shell in `/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/builtin_readonly.py:1`. There is no Hermes-equivalent `send_message`, `execute_code`, `delegate_task`, `memory`, or `session_search` tool layer yet.
- CopeNet's shell tool is intentionally strict and read-only in `/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/handlers/shell.py:11`, which is good for safety but also means we do not yet have Hermes-style background work, notifications, or approval-mediated expansion into stronger side effects.
- CopeNet's tool policy in `/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/policy.py:1` is a static allowlist/scope policy, not a conversational approval system. That is a notable gap relative to Hermes if we want user-confirmed autonomous action later.
- Skills are progressive disclosure, not just docs. The system prompt contains a compact index and explicitly tells the model to inspect relevant skills with `skill_view(name)` before acting.
- Hermes treats many bad model behaviors as recoverable states instead of terminal failures: invalid tool names, invalid JSON arguments, empty post-tool responses, truncated tool arguments, reasoning-only output, and incomplete Codex responses all have dedicated recovery paths in `/Users/copeharder/Programming/hermes-agent/run_agent.py`.
- Hermes records assistant tool calls and appends tool-role messages in canonical OpenAI history order, then continues the loop until real text completion or a bounded failure path.

## Confirmed By Code

- Main loop: `/Users/copeharder/Programming/hermes-agent/run_agent.py:9585`
  - `run_conversation()` owns the iterative tool loop.
- Budget / continuation loop: `/Users/copeharder/Programming/hermes-agent/run_agent.py:9951`
  - loop continues while API-call count and iteration budget allow, with a grace-call mechanism.
- Tool execution split: `/Users/copeharder/Programming/hermes-agent/run_agent.py:8552`
  - `_execute_tool_calls()` dispatches to sequential vs concurrent execution.
- Sequential execution: `/Users/copeharder/Programming/hermes-agent/run_agent.py:9032`
  - tool-level callbacks, checkpointing, interrupt handling, steer injection, tool-result append.
- Invalid tool self-repair and bounded retry: `/Users/copeharder/Programming/hermes-agent/run_agent.py:12184`
- Invalid JSON retry / recovery-tool-result injection: `/Users/copeharder/Programming/hermes-agent/run_agent.py:12234`
- Post-tool empty-response nudge: `/Users/copeharder/Programming/hermes-agent/run_agent.py:12540`
- Thinking-only prefill continuation: `/Users/copeharder/Programming/hermes-agent/run_agent.py:12589`
- Empty-response retry / fallback-provider activation: `/Users/copeharder/Programming/hermes-agent/run_agent.py:12633`
- Tool schema curation and sanitization: `/Users/copeharder/Programming/hermes-agent/model_tools.py:203`
- Terminal tool anti-misuse guidance: `/Users/copeharder/Programming/hermes-agent/tools/terminal_tool.py:736`
- File-tool schemas and repeated-search warning: `/Users/copeharder/Programming/hermes-agent/tools/file_tools.py:980`
- Dynamic execute-code / Discord / browser schema rewriting: `/Users/copeharder/Programming/hermes-agent/model_tools.py:280`
- System-prompt assembly and enforcement guidance: `/Users/copeharder/Programming/hermes-agent/run_agent.py:4543`
- Skill index + mandatory loading guidance: `/Users/copeharder/Programming/hermes-agent/agent/prompt_builder.py:650`

## Inferences

- Hermes gets leverage from two layers at once:
  - prompt-level behavioral steering
  - code-level recovery and continuation logic
- Hermes does not appear to use an explicit evidence-ledger/final-gate abstraction like CopeNet. Instead, it relies more on:
  - curated tool availability
  - strong execution discipline in prompting
  - retry/nudge/recovery loops after bad outputs
- Hermes is more tolerant of messy model behavior than CopeNet. It expects malformed or incomplete outputs and has a lot of glue code to recover instead of hard-failing.
- Hermes likely benefits from a richer tool ecosystem and skills system, which gives the model better action affordances than a small raw repo-tools surface alone.

## Pain Points In CopeNet

- CopeNet currently reasons more about whether a final answer is legal than about whether the model has taken a good next action.
- Our live Gemma failures are mostly tool-choice failures (`files.list` saturation), not protocol failures.
- CopeNet has some controller discipline (`FinalGate`, contracts, ledger) but much less action-recovery discipline than Hermes when the model behaves weakly.
- We currently do less schema shaping and less description hygiene than Hermes, so a model can still see cheap reconnaissance actions without stronger escalation pressure toward evidence-bearing reads/searches.
- CopeNet does not yet seem to have Hermes-style duplicate-search / reconnaissance fatigue warnings feeding back into the model.
- CopeNet also does not have tool-layer hard blocks for repeated identical reads/searches, so weak models can stay in low-value loops unless the harness catches them later.
- CopeNet's `files.list` tool is especially underspecified compared with Hermes's overall tool guidance, which likely makes it too attractive as a low-risk move for weaker local models.
- CopeNet's current ledger semantics may be part of the problem: if `context.prepare` counts as grounding, the controller can overcredit shallow progress.

## Reference Harness Strengths

- Strong prompt-level execution discipline tailored by model family.
- Tool-layer anti-loop warnings and hard blocks for repeated identical reads/searches.
- Many recovery paths for weak or malformed tool-using behavior.
- Dynamic tool-schema curation so the model sees a truer action space.
- Parallel tool execution when calls are independent.
- Good handling of interrupted / incomplete / empty turns without instantly giving up.
- Skills-based progressive disclosure gives the model procedural scaffolding without dumping every instruction into the base prompt.
- Scenario toolsets, session search, memory orchestration, delegation, context compression, and large-output persistence make Hermes feel much closer to an agent operating system than a plain chat harness.

## Questions

- Does Hermes have any explicit mechanism that discourages repeated reconnaissance tools, or does that emerge from better tool affordances plus prompting?
- Where exactly are repo/code tools defined, and how descriptive / opinionated are their schemas compared with CopeNet's `files.list`, `files.read`, `files.search`, and `context.prepare`?
- Does Hermes have any post-tool classification that approximates our `FinalGate`, just implemented implicitly through retries and nudges?

## Next Checks

- Read Hermes tool definitions for file/search/code tools and compare schema wording against CopeNet's built-ins.
- Trace how Hermes builds `self.valid_tool_names` and whether toolsets create stronger default action pressure than CopeNet.
- Inspect whether Hermes has any explicit anti-loop / anti-repetition handling for cheap tool calls.
- Compare Hermes continuation/recovery paths against CopeNet's native LM Studio loop in `/Users/copeharder/Programming/CopeNet/src/copenet/core/harness/tool_loop.py`.
- Keep separating near-term harness takeaways from larger long-term 'agent OS' product ideas.

## Broader Hermes System Aspects

- **Toolsets as first-class capability bundles** — `/Users/copeharder/Programming/hermes-agent/toolsets.py:1` groups tools by scenario (`debugging`, `browser`, `delegation`, `session_search`, etc.), which gives the agent a more semantically organized action space than a flat tool list.
- **Skills as procedural memory** — `/Users/copeharder/Programming/hermes-agent/agent/prompt_builder.py:650` injects a compact skill index and requires the model to load relevant skills before acting. This is stronger than just keeping docs in the repo.
- **Memory orchestration** — `/Users/copeharder/Programming/hermes-agent/agent/memory_manager.py:1` unifies built-in memory plus one external provider, and it cleanly separates prefetch/system-prompt/sync duties.
- **Cross-session search** — `/Users/copeharder/Programming/hermes-agent/tools/session_search_tool.py:531` and `/Users/copeharder/Programming/hermes-agent/hermes_state.py:1` make old work searchable and recallable without stuffing everything into the live prompt.
- **Context compression** — `/Users/copeharder/Programming/hermes-agent/agent/context_compressor.py:1` gives Hermes a structured handoff model for long sessions, instead of just trimming text.
- **Subagent delegation** — `/Users/copeharder/Programming/hermes-agent/tools/delegate_tool.py:2299` creates isolated subagents with separate context/terminal/toolsets. This is a real execution primitive, not just marketing.
- **Large-result persistence** — `/Users/copeharder/Programming/hermes-agent/tools/tool_result_storage.py:1` spills oversized tool outputs to files and teaches the model to re-open them with `read_file`, which preserves evidence without context blowup.
- **Background process / terminal lifecycle** — Hermes invests heavily in terminal/process ergonomics, which matters for a future operator-OS style product.

## Table-Stakes Features Hermes Has Beyond CopeNet Today

- **Progressive skills, but not progressive tools** — Hermes appears to pass the full enabled tool schema set into the model from the start of a turn via `/Users/copeharder/Programming/hermes-agent/run_agent.py:1481` and the transport kwargs built with `tools=self.tools` in `/Users/copeharder/Programming/hermes-agent/run_agent.py:7800`. The *tools* are globally available per session/toolset. The *skills* are progressive: the model only gets an index first, then is told to load relevant details with `skill_view(name)` from `/Users/copeharder/Programming/hermes-agent/agent/prompt_builder.py:650`.
- **Programmatic tool-building / multi-step execution** — Hermes has `execute_code` in `/Users/copeharder/Programming/hermes-agent/tools/code_execution_tool.py:1474`, which lets the model write Python that calls tools programmatically. This is a big deal for 'build its own tooling once allowed' behavior because it compresses many tool calls into one reasoning turn.
- **Cross-platform communication** — Hermes exposes `send_message` in `/Users/copeharder/Programming/hermes-agent/tools/send_message_tool.py:112` and has explicit Telegram support/config visibility in `/Users/copeharder/Programming/hermes-agent/hermes_cli/config.py:3966`. This is directly relevant to your 'Telegram is enough for now' direction.
- **Approval / permission system** — Hermes has a substantial dangerous-command approval layer in `/Users/copeharder/Programming/hermes-agent/tools/approval.py:1`, including session-scoped state, smart approvals, and hardline blocks. That is highly relevant if CopeNet should eventually let the model build tooling or act across the user's environment with confirmation.
- **Background / long-running task ergonomics** — Hermes terminal and process tools support tracked background work, notifications, and lifecycle management, which matters a lot for an always-helpful operator model instead of a pure request/response chat loop.

## Medium-Term Feature Investigation

- **Messaging is not a bolt-on in Hermes; it is a normalized tool surface.** `/Users/copeharder/Programming/hermes-agent/tools/send_message_tool.py:111` defines one `send_message` schema that covers `send` and `list`, teaches the model to list targets first when the target is ambiguous, and resolves human-friendly names before sending. This is a strong pattern for CopeNet: expose one stable outbound communication tool, not separate ad hoc Telegram-specific prompt hacks.
- **Telegram is first-class but not special-cased into the tool contract.** Hermes's config keeps Telegram under the same gateway platform system as Slack/Discord/etc. (`/Users/copeharder/Programming/hermes-agent/hermes_cli/config.py:889`). The tool itself accepts generic `platform[:target]` addressing and only uses Telegram-specific parsing when needed. CopeNet should probably copy that architecture: start with Telegram as the only enabled backend, but keep the public tool contract generic enough to grow into `send_message`.
- **Hermes makes directory discovery part of messaging safety.** The `send_message` tool tells the model to call `send_message(action='list')` first when the user asks for a specific person/channel (`/Users/copeharder/Programming/hermes-agent/tools/send_message_tool.py:113`). That is a subtle but important harness lesson: tool descriptions can encode multistep operational etiquette, not just argument docs.
- **Approvals are a real subsystem, not just a boolean gate.** Hermes's approval layer is not “ask before shell.” It owns pattern detection, session-scoped state, gateway-safe context binding, manual/smart/off policy modes, cron behavior, permanent allowlists, and an unconditional hardline blocklist (`/Users/copeharder/Programming/hermes-agent/tools/approval.py:1`, `/Users/copeharder/Programming/hermes-agent/hermes_cli/config.py:904`). CopeNet’s current `ToolPolicy` is a static category allowlist with no conversation-aware pause/approve/reject flow (`/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/policy.py:10`).
- **The hardline blocklist idea is worth stealing even before broad approvals.** Hermes distinguishes “dangerous but user-approvable” from “never let the agent do this through the harness” (`/Users/copeharder/Programming/hermes-agent/tools/approval.py:76`). If CopeNet adds write/external-action tools later, we should likely adopt the same floor: some actions should be structurally impossible through the agent regardless of user mode.
- **`execute_code` is really a tool orchestrator, not just code execution.** Hermes frames it as the right tool when the task needs 3+ tool calls, filtering/reduction of large outputs, conditional branching, retries, or loops (`/Users/copeharder/Programming/hermes-agent/tools/code_execution_tool.py:1519`). That is exactly the missing abstraction when a weaker model keeps spending four chat turns doing what should have been one small scripted workflow.
- **Hermes dynamically scopes `execute_code` to the actually-enabled subtools.** The schema only documents the tools currently available to the sandbox script (`/Users/copeharder/Programming/hermes-agent/tools/code_execution_tool.py:1472`). That prevents the model from hallucinating helper capabilities it cannot call. If CopeNet eventually adds an orchestration tool, dynamic schema shaping is table stakes.
- **Hermes is careful about execution mode and working-directory semantics.** The `execute_code` schema explicitly explains whether scripts run in a temp dir or in the project working directory (`/Users/copeharder/Programming/hermes-agent/tools/code_execution_tool.py:1505`). That kind of clarity matters a lot; otherwise models will misuse relative paths and silently fail.
- **CopeNet already has one useful building block here: artifacts.** We do not have messaging/approvals/orchestration yet, but we do already persist artifacts and oversized tool results (`/Users/copeharder/Programming/CopeNet/tests/integration/test_tool_loop.py:733`, `/Users/copeharder/Programming/CopeNet/src/copenet/core/runtime/artifacts.py:1`). That gives us a natural place to persist outbound-message drafts, approval requests/responses, and orchestration run outputs later.

## Concrete Medium-Term Gaps In CopeNet

- **No outbound communication primitive.** There is no `send_message`/Telegram equivalent in CopeNet’s tool registry today; builtin tools remain local `context/files/git/shell` only (`/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/builtin_readonly.py:1`).
- **No conversational approval loop.** CopeNet can block a tool category, but it cannot pause a run, present a proposed action, and wait for the user to approve/deny/modify it. That makes “ask before stronger actions” impossible without external provider-specific behavior.
- **No programmatic orchestration primitive.** CopeNet’s model must still drive tool usage turn by turn through the chat loop. We do not yet have an `execute_code`-style way to compress `search -> read -> filter -> summarize` or `read -> transform -> write -> verify` into one bounded operation.
- **No generic target directory / address book abstraction.** Hermes can list messaging targets and resolve human names before sending. CopeNet currently has no concept of user-approved destinations, channels, or external endpoints.
- **No approval state persisted per session/run.** Hermes binds approvals to session identity and can remember permanent approvals/allowlist entries. CopeNet has traces and session state, but no approval ledger or action-review record yet.

## Medium-Term Design Direction For CopeNet

- **Communication:** start with a generic `send_message` tool contract, but only wire a Telegram adapter first. Keep the model-facing tool stable; let the backend decide which platforms are configured.
- **Approvals:** create a first-class approval subsystem, not just a tool-policy flag. It should be able to:
  - classify proposed actions
  - hard-block never-allowed actions
  - pause a run and emit an approval request artifact/event
  - resume the run with approve / reject / modify outcomes
- **Orchestration:** add an `execute_code`-style tool only after approvals and safety boundaries exist. The orchestrator should be for bounded programmatic tool use, not a disguised unrestricted shell.
- **Artifacts / observability:** approval requests, outbound sends, and orchestration runs should all show up as inspectable runtime artifacts and run events, not invisible side effects.
