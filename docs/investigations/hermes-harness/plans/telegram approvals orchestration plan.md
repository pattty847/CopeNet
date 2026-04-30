# CopeNet Telegram / Approvals / Orchestration Plan V1

## Summary
Design the first medium-term operator features for CopeNet by introducing:

- a generic outbound communication tool contract with a **Telegram-first** backend
- a CopeNet-native **approval subsystem** that can pause and resume runs around higher-risk actions
- a future **bounded orchestration tool** inspired by Hermes's `execute_code`, but deferred until approvals exist

This wave is a **design and sequencing plan**, not an instruction to build everything at once. The goal is to make CopeNet feel more like a trustworthy operator system without losing its current strengths: session integrity, provider-agnostic harnessing, and inspectable runtime state.

Chosen defaults:
- Start with a **generic `send_message` tool contract**, but only implement Telegram first
- Treat approvals as **first-class run state**, not a static tool-policy toggle
- Defer programmatic orchestration until approvals and hard safety boundaries exist
- Persist messaging, approval, and orchestration events as **artifacts + trace events**, not invisible side effects
- Keep the harness/provider split clean: communication and approvals belong in shared CopeNet layers, not in one provider adapter

## Why This Order

Hermes suggests a clear sequencing lesson:

1. useful external action surface
2. trust boundary / approval system
3. workflow-compression / orchestration

That order matters.

If CopeNet adds orchestration before approvals, the model gains a stronger action multiplier before the product has a good way to stop, inspect, or approve risky behavior. If CopeNet adds communication first, but does it behind an explicit approvalable action model, we get useful operator behavior early without jumping straight to an overpowered agent.

## 1. Generic Messaging Contract, Telegram Backend First

### Goal
Give CopeNet one stable model-facing communication primitive that can eventually support multiple platforms, while only implementing Telegram in v1.

### Public Tool Shape
Add a new tool descriptor conceptually like:

- `send_message`

Suggested parameters:
- `action`
  - `list`
  - `send`
- `target`
  - generic string target, e.g. `telegram`, `telegram:<chat_id>`, `telegram:<chat_id>:<thread_id>`
- `message`
  - message text
- optional future media support
  - do not block the initial design on this

Important behavior guidance in the tool description:
- when the user asked for a specific destination but the exact target is ambiguous, list available targets first
- when the user clearly asked for a known configured destination, send directly
- do not claim a message was sent unless the tool confirms it

This mirrors the strongest Hermes lesson from `/Users/copeharder/Programming/hermes-agent/tools/send_message_tool.py:111`:
- the tool description itself should teach the model the right operational etiquette

### Backend Shape
Do **not** make Telegram a prompt hack.

Add a small backend abstraction behind the tool, for example:
- `MessagePlatformAdapter`
- `TelegramAdapter`

Responsibilities:
- list available targets
- resolve configured home/default target
- send a message to a concrete target
- return structured result payloads

The model-facing tool remains generic even if the only enabled backend is Telegram.

### CopeNet Placement
Probable homes:
- tool descriptor/handler registration under `/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/`
- transport/config wiring outside `core/`, likely via host/config/runtime setup
- artifacts and run records in existing runtime stores

This keeps with CopeNet’s principle of thin providers and shared harness behavior.

### Configuration Direction
Telegram-first config should likely include:
- bot token
- default chat id or home destination
- optional allowed chat/topic directory
- optional friendly target names

Keep destination configuration explicit and operator-visible.

### Runtime / Trace Expectations
A successful outbound send should create:
- a trace event like `tool_executed` with send metadata
- an artifact representing the outbound action summary
- run-record linkage so the operator can inspect what was sent and where

Suggested artifact types:
- `outbound_message`
- `approval_request`
- later: `orchestration_run`

### UI Implications
CopeNet should expose outbound actions honestly in the existing runtime surfaces:
- right-panel runtime activity
- artifacts inspector
- run log / observability

The operator should be able to answer:
- what message did the agent try to send?
- where did it send it?
- was it approved first?
- did it succeed or fail?

## 2. Approval Subsystem As Pause/Resume Run State

### Goal
Move from static blocking to conversational human oversight.

Current CopeNet policy in `/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/policy.py:10` can allow or block tool categories, but it cannot:
- pause a run
- present a proposed action
- wait for human approval
- resume from that decision

That is the core missing product primitive.

### Design Principle
Approvals should be modeled as **run state**, not just preflight validation.

The system should be able to say:
- the agent proposes action X
- action X requires approval
- the run is now paused on approval Y
- the user approved / rejected / modified it
- the run resumed from that outcome

### Approval Outcomes
Support at least:
- `approve`
- `reject`
- `modify`

`modify` matters because some of the best human oversight is not “yes/no” but:
- send this to a different target
- run this command in a different directory
- shorten the message
- don’t do the write, just draft it

### Action Classes
CopeNet should eventually classify actions into buckets:
- `safe_read`
- `external_communication`
- `filesystem_write`
- `process_execution`
- `network_side_effect`
- `credential_or_sensitive_target`

That classification can drive approval policy.

### Hardline vs Approveable
Hermes’s strongest safety idea here is the **hardline blocklist** in `/Users/copeharder/Programming/hermes-agent/tools/approval.py:76`.

CopeNet should likely adopt the same distinction:
- some actions may be user-approvable
- some actions should never be allowed through the agent at all

That keeps approval from becoming a magical override for obviously catastrophic behavior.

### Proposed CopeNet Flow
1. model or harness proposes a tool action
2. tool policy / approval classifier evaluates it
3. if approval is required:
   - emit approval artifact/event
   - mark run paused
   - return control to UI/client
4. user approves / rejects / modifies
5. orchestrator resumes the run with the approval outcome as structured input

### State / Persistence
Approval state should live with session/run state, not in provider adapters.

Likely needed concepts:
- pending approval id
- approval status
- requested action payload
- human response payload
- resumed run linkage

This should be inspectable in:
- traces
- run records
- artifacts
- possibly session state if we need fast resume behavior

### RPC / UI Implications
CopeNet will likely need explicit RPC support for:
- listing pending approvals
- approving one
- rejecting one
- modifying one

UI implications:
- visible paused-run state
- actionable approval card or panel
- clear summary of proposed action and expected side effect
- direct linkage into artifacts / traces

## 3. Bounded Orchestration Tool, After Approvals

### Goal
Add a workflow-compression primitive for cases where turn-by-turn tool use is too inefficient or too fragile.

Hermes’s `execute_code` in `/Users/copeharder/Programming/hermes-agent/tools/code_execution_tool.py:1519` is a good model because it is framed as:
- use when you need 3+ tool calls
- use when you need branching or loops
- use when you need to filter large outputs before they hit prompt context

That is exactly the kind of thing weaker local models struggle to do through repeated conversational turns.

### Important Constraint
Do **not** add this before approvals.

Otherwise CopeNet would be giving the model a stronger way to act before it can properly pause around risky behavior.

### CopeNet Framing
When CopeNet eventually adds it, it should be clearly framed as:
- bounded programmatic tool orchestration
- not a generic unrestricted shell
- not a provider-specific hack

### Suggested Behavior
The orchestration tool should:
- expose only a restricted helper set
- run in a clearly documented environment
- have explicit time/output/tool-call limits
- produce a clear final result plus structured metadata
- emit artifacts and traces for the orchestration run

### Suggested Initial Use Cases
- search many files, extract matches, summarize patterns
- process a list of artifacts/results before summarizing
- retry a structured fetch/search/read workflow programmatically
- generate a draft output from multiple tool results

### Non-Goals For V1
- background daemons
- unrestricted package installation
- arbitrary persistent environment mutation
- hidden side effects

## Proposed Sequencing

### Phase A: Harness Quality First
Do the already-captured harness shortlist first:
- stronger repo tool semantics
- anti-repeat saturation pressure
- stop overcounting `context.prepare`
- stronger recovery from shallow reconnaissance

### Phase B: Telegram-First Messaging
Then add:
- `send_message` tool contract
- Telegram adapter/backend
- outbound message artifacts and traces
- honest operator-facing UI visibility

### Phase C: Approval Subsystem
Then add:
- approval classification
- pause/resume run model
- approval artifacts/events
- UI + RPC actions for approve/reject/modify
- hardline blocked action floor

### Phase D: Orchestration Tool
Only after approvals exist:
- add bounded `execute_code`-style orchestration
- integrate with approval classes where needed
- keep everything inspectable in artifacts/traces

## Concrete Feature Gaps To Fill

### Messaging
Missing today:
- no outbound communication primitive
- no target directory/address book concept
- no external delivery artifacts

### Approvals
Missing today:
- no pending-approval run state
- no resume-after-approval mechanism
- no approval UI/RPC surface
- no hardline blocklist model

### Orchestration
Missing today:
- no bounded programmatic tool orchestration
- no helper-runtime contract for tool scripting
- no orchestration artifacts or dedicated traces

## Test Strategy Direction

### Messaging
- unit-test target parsing and adapter behavior
- integration-test successful Telegram send against a fake adapter boundary
- verify run records and artifacts capture outbound metadata

### Approvals
- unit-test action classification and hardline handling
- integration-test pause/resume flow through orchestrator
- UI/RPC test pending approval listing and action submission

### Orchestration
- unit-test helper-tool exposure and limits
- integration-test one bounded multi-tool script run
- verify artifact/trace output is inspectable and complete

## Recommended Next Plan
After the harness patch shortlist is implemented or at least staged, the next best concrete plan to write is:

1. `send_message` Telegram-first technical design
2. approval lifecycle technical design
3. orchestration deferred-design note with safety gates

That will let us move from investigation into actual system design without trying to swallow the whole Jarvis dream in one patch.
