# Comparison

## Tool Loop

### Reference Harness

- Hermes runs one centralized iterative loop in `/Users/copeharder/Programming/hermes-agent/run_agent.py:9585`.
- Native tool calls are the default mental model. Provider transports normalize into a shared OpenAI-style shape before the loop sees them.
- Tool execution is first-class inside the loop, with sequential and concurrent paths.

### CopeNet

- CopeNet splits more responsibility across planning, provider path selection, native/prompted tool-loop helpers, and `FinalGate`.
- Native LM Studio tool calls are now supported, but the loop is still relatively light compared with Hermes’s recovery machinery.

### Gap

- Hermes has a thicker operational loop; CopeNet currently has a thinner legality loop.
- CopeNet is better factored, but Hermes currently appears more resilient to weak model behavior.

## Continuation / Early Stop Prevention

### Reference Harness

- Hermes uses prompt-level “act, don’t just say” enforcement plus multiple concrete recovery paths:
  - invalid tool-call retries
  - invalid JSON retries
  - post-tool empty-response nudges
  - thinking-only continuation prefills
  - fallback-provider retry on persistent empties
  - max-iteration summary request
- The loop treats many bad outputs as intermediate states, not terminal failures.

### CopeNet

- CopeNet mainly prevents weak completion via task contracts + evidence ledger + `FinalGate` rejection.
- We now observe `rejected_final_then_recovered`, which is good, but that only catches one class of weak behavior.

### Gap

- Hermes has more continuation / self-repair behaviors when the model stalls or emits junk.
- CopeNet currently blocks bad finals better than it repairs weak intermediate behavior.

## Evidence / Grounding

### Reference Harness

- Hermes does not appear to expose an explicit evidence ledger abstraction in the first-pass files we read.
- Instead, grounding is supported indirectly through:
  - forcing tool action
  - keeping tool results in canonical history
  - continuing after bad empty outputs
  - richer skills / tool affordances

### CopeNet

- CopeNet has a clearer explicit grounding model: contracts, evidence ledger, and final gating.
- But `/Users/copeharder/Programming/CopeNet/src/copenet/core/runtime/turn_state.py:111` currently treats `context.prepare` as grounding.
- Our live Gemma failures show that a legal evidence threshold is not enough when the model keeps choosing cheap tools.

### Gap

- CopeNet is stronger on explicit final-answer validation.
- Hermes seems stronger on keeping the model in motion until it actually uses the work it just did.
- CopeNet may also be overcounting shallow context-pack steps as grounding, which weakens its own validation signal.

## Tool Choice Policy

### Reference Harness

- Hermes curates the tool surface aggressively in `/Users/copeharder/Programming/hermes-agent/model_tools.py:203`.
- It dynamically rewrites schemas/descriptions based on actual availability so the model is not tempted to call missing or misleading companion tools.
- Its tool descriptions themselves are more directive: `/Users/copeharder/Programming/hermes-agent/tools/terminal_tool.py:736` explicitly says not to use `ls`, `cat`, or `grep` when dedicated tools exist.
- `/Users/copeharder/Programming/hermes-agent/tools/file_tools.py:600` warns on the 3rd identical read and blocks on the 4th; `/Users/copeharder/Programming/hermes-agent/tools/file_tools.py:950` does the same for identical searches.
- It also gives the model skills as procedural scaffolding, not just raw tool buttons.

### CopeNet

- CopeNet currently exposes a smaller, cleaner tool surface, but tool-choice pressure is weak.
- `/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/handlers/files.py:11` gives only short descriptions for `files.list`, `files.read`, and `files.search`.
- `context.prepare` in `/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/handlers/context.py:11` is broad enough that weak models may treat it like stronger evidence than it really is.
- Gemma can legally spam `files.list` and still reach ungrounded answers in some probes.

### Gap

- Hermes appears to invest more in shaping the action space before inference.
- CopeNet currently invests more after inference, via final gating.
- Hermes also pushes back at the tool layer when the model repeats itself, while CopeNet mostly waits for the harness to notice.
- Our likely missing layer is better pre-action shaping, narrower semantics for `context.prepare`, and better mid-loop escalation away from reconnaissance saturation.

## State / Memory / Session Continuity

### Reference Harness

- Hermes keeps a cached system prompt, persistent memory/session-search guidance, optional external memory providers, and context compression.
- Same-session continuity is a major product feature, and the main loop is designed around long-lived message history.

### CopeNet

- CopeNet keeps persisted sessions/transcripts/run records and now tracks tool protocol/execution mode in probes.
- Same-session behavior improved after moving Gemma to native LM Studio tools, but repo-seed/tool-choice quality is still weak.

### Gap

- Hermes has much more mature long-session recovery and continuity machinery.
- CopeNet’s immediate harness problem is still earlier in the stack: tool-choice quality inside a single turn.

## First Precise Gaps

- Gap 1: CopeNet lacks Hermes-style recovery paths for weak intermediate behavior. We reject weak finals, but we do not yet strongly recover from cheap/repetitive tool use.
- Gap 2: CopeNet does less tool-surface shaping than Hermes. We likely need stronger schema wording / dynamic constraints / saturation pressure, not only better final gating.
- Gap 3: CopeNet currently has less procedural scaffolding than Hermes’s skills system. We may need a lighter-weight equivalent for repo-analysis workflows without hardcoding domain-specific contracts for everything.

## Broader Agent-OS Features

### Reference Harness

- Hermes layers in larger agent-system primitives that support a more autonomous life-assistant shape: memory orchestration, cross-session search, context compression, subagent delegation, broad toolsets, background process handling, large-result persistence, and platform/gateway continuity.

### CopeNet

- CopeNet already has strong session semantics, traces, run records, and a growing harness, but it does not yet have Hermes-level memory, delegation, or toolset breadth.
- The current builtin tools are still mostly `context/files/git/shell` via `/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/builtin_readonly.py:1`.

### Gap

- For the near term, we should steal harness-quality lessons first.
- For the longer-term Jarvis vision, Hermes is a useful proof that an 'agent OS' feel comes from multiple systems working together: harness, memory, delegation, tooling, and continuity — not just the chat loop.

## Additional Features To Consider

### Reference Harness

- Hermes already includes several 'operator OS' features beyond the raw harness: `execute_code` for programmatic tool orchestration, `send_message` for cross-platform outbound communication, Telegram/gateway integration, background process tracking, and a serious approval system for risky commands.

### CopeNet

- CopeNet currently focuses on local session execution, traces, repo tools, and provider normalization. It does not yet expose equivalent cross-platform communication, code-as-tool-orchestrator, or mature approval semantics.

### Gap

- Near term: better harness quality and better repo-tool behavior.
- Medium term: Telegram + approvals + programmatic tool orchestration look like very credible 'table stakes' additions for the broader Jarvis direction.
- Longer term: memory/session recall + delegation + background task ergonomics are the systems that start making it feel like a real operator OS instead of a local chat harness.

## Communication / Approvals / Orchestration

### Reference Harness

- Hermes exposes one generic `send_message` tool that handles `list` and `send`, teaches the model when to list targets first, and resolves friendly names to concrete destination IDs (`/Users/copeharder/Programming/hermes-agent/tools/send_message_tool.py:111`).
- Hermes keeps Telegram under a broader gateway platform model rather than baking Telegram-specific assumptions into the public tool schema (`/Users/copeharder/Programming/hermes-agent/hermes_cli/config.py:889`).
- Hermes approvals are a true subsystem with:
  - manual / smart / off modes
  - cron-specific behavior
  - session-scoped state
  - permanent allowlists
  - an unconditional hardline blocklist for actions the agent should never perform
  (`/Users/copeharder/Programming/hermes-agent/tools/approval.py:1`, `/Users/copeharder/Programming/hermes-agent/hermes_cli/config.py:904`)
- Hermes `execute_code` is framed as a bounded orchestration tool for 3+ tool calls, branching, looping, retry logic, and result filtering, not as generic arbitrary execution (`/Users/copeharder/Programming/hermes-agent/tools/code_execution_tool.py:1519`).

### CopeNet

- CopeNet currently has no outbound communication tool in the registry. The builtin surface is still `context/files/git/shell` (`/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/builtin_readonly.py:1`).
- CopeNet’s current `ToolPolicy` is a static allowlist of tool categories and shell commands (`/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/policy.py:10`), not a pause-and-approve execution model.
- CopeNet has no `execute_code`-style orchestration primitive; all multi-tool work still happens turn by turn inside the chat harness.
- CopeNet does already have artifacts and run records, which is a strong base for later approval requests, outbound-message logs, and orchestration outputs.

### Gap

- Hermes already has the control-plane pieces needed for “ask before stronger actions” and “communicate outward on the user’s behalf.”
- CopeNet currently lacks all three medium-term primitives:
  - communication surface
  - approval subsystem
  - programmatic tool orchestration
- The good news is that CopeNet’s existing session/run/artifact model gives us a clean place to add them without needing to copy Hermes’s whole gateway architecture.

## What To Steal First In The Medium Term

### 1. Generic Messaging Contract, Telegram Backend First

- Steal the *shape*, not the whole gateway:
  - one `send_message` tool
  - `action=list|send`
  - generic `target`
  - backend-specific adapters behind the scenes
- Start with Telegram as the only configured backend, but keep the tool contract generic so we do not paint ourselves into a corner.
- Important Hermes lesson: the tool description should teach the model when to list targets before sending.

### 2. Real Approval State, Not Just Tool Blocking

- Steal the idea that approvals are session-scoped execution state.
- CopeNet should eventually support:
  - proposed action → approval artifact/event
  - user approves / rejects / modifies
  - run resumes from that decision
- Also steal the hardline concept:
  - some actions are never agent-allowed, even with approval

### 3. Bounded Tool Orchestration

- Steal the framing of `execute_code` as a workflow compressor for repetitive tool logic.
- Do **not** steal it before approvals exist.
- When we add it, it should:
  - expose only approved helper tools
  - clearly state cwd/runtime semantics
  - emit artifacts/traces for what happened
  - stay bounded and inspectable

## Sequenced Roadmap

### Now

- Strengthen repo-tool semantics in CopeNet: better `files.*` descriptions, explicit anti-loop warnings/blocks, and narrower grounding credit for `context.prepare`.
- Add stronger mid-loop recovery for weak local models, especially around repeated shallow reconnaissance.
- Re-run probe matrix after each isolated harness intervention.

### Soon

- Add Telegram/outbound messaging support as the first real communication surface.
- Design a conversational approval layer so the agent can ask before doing stronger actions or building tooling.
- Add a programmatic orchestration tool (`execute_code`-style) once approvals and safety boundaries are clear.

### Later

- Add memory/session recall beyond the current transcript window.
- Add delegation/subagents when the base harness is already trustworthy.
- Add background-task ergonomics and richer operator workflows once the core loop stops wasting turns on shallow tool use.
