# Chat Anywhere Foundations

## Summary
This is the next practical lane after Pulse v0 and Personal History Substrate v1.

Goal: make CopeNet reachable from Telegram while preserving the desktop `Agents` surface as the source of truth.

This is **not** away-mode autonomy yet. It is the first real external channel loop.

## What CopeNet Already Has
- `Agents` as the core session substrate
- persisted sessions and append-only transcripts
- Pulse save flows that open normal sessions
- merge sessions and provenance strips
- session state / personal-history capture
- Inbox / Operator Action Center shell
- approval concepts and paused-run UI surfaces
- mock messaging settings UI and destination concepts

Relevant files already in the repo:
- `/Users/copeharder/Programming/CopeNet/src/copenet/host/frontend/src/components/MessagingSettingsPanel.tsx`
- `/Users/copeharder/Programming/CopeNet/src/copenet/host/frontend/src/runtime/mocks.ts`
- `/Users/copeharder/Programming/CopeNet/src/copenet/host/frontend/src/types/backend.ts`
- `/Users/copeharder/Programming/CopeNet/docs/investigations/hermes-harness/telegram-settings-ui-notes.md`

## Product Truth
Telegram should be a **quick-access channel**, not a separate CopeNet brain.

Desktop CopeNet remains the deep-work console for:
- runtime truth
- session inspection
- provenance
- Pulse
- merges
- approvals
- artifacts

Telegram should excel at:
- quick asks
- continuation while away
- saving an idea into a real session
- light follow-up
- receiving useful prompts/briefings later

## v1 Scope
### Must have
- one Telegram bot configuration
- one inbound webhook/polling path
- session routing between Telegram chat and CopeNet session
- messages visible in desktop transcript/history
- ability to keep talking to the same agent session from Telegram
- clear source-channel provenance on messages/runs

### Nice soon after
- choose default provider/model for Telegram in settings
- `/models` or equivalent quick switch in Telegram
- per-chat or per-destination session binding
- approval boundary for outbound agent sends

### Not in v1
- multi-platform support
- full away-mode automation
- rich media workflows
- autonomous background agents messaging you unprompted

## Suggested Build Order
### 1. Messaging substrate becomes real
Replace the current mock messaging config with a durable backend store and RPCs.

Need:
- persisted Telegram bot config
- persisted destinations
- approval policy persistence
- live config load into frontend

Likely RPCs:
- `messaging.config.get`
- `messaging.config.update`
- `messaging.destinations.list`
- `messaging.destinations.upsert`
- `messaging.destinations.delete`
- `messaging.test`

### 2. Telegram transport adapter
Add a backend adapter that can:
- receive Telegram messages
- normalize inbound payloads
- map them to CopeNet sessions
- send replies back out

Key rule:
- inbound Telegram conversation must map to a **normal CopeNet session key**
- do not create a second transcript system

### 3. Session routing model
Need one simple routing rule first.

Recommended v1:
- one Telegram chat/thread maps to one CopeNet session
- first message can create a session automatically
- later messages continue that session
- desktop can reopen and inspect that same session

Persist routing metadata such as:
- platform
- chat id
- thread id if present
- mapped session key
- provider/model override if configured

### 4. Source-channel provenance
Every Telegram-originated turn should remain honest in CopeNet.

Need visible markers for:
- inbound via Telegram
- outbound via Telegram
- destination used
- whether approval was required

This should show up in:
- transcript metadata
- runs when relevant
- Inbox when a send is pending or fails

### 5. Runtime choice and model control
The user specifically wants model choice from settings and ideally from Telegram.

Recommended order:
- desktop settings choose default Telegram provider/model/profile/task mode
- later add Telegram slash command support:
  - `/models`
  - `/use <model>`
  - `/new`
  - `/session`

Do not start with the slash commands first. Desktop config is the simpler truth surface.

## Easy Onboarding Lane
There is a second major need: make setup easy for normal people.

### Core onboarding truths
New users need to answer:
- what model can I use?
- do I need an API key?
- is local runtime okay?
- what provider is currently connected?
- what do I do first?

### Minimum onboarding work
- provider connection status becomes clearer and more guided
- first-run checklist in Home or Agents
- obvious path for:
  - OpenAI key / auth
  - LM Studio local runtime
  - Ollama local runtime
- one recommended default setup path

### Strong recommendation
Build a **Guided Runtime Setup** surface before trying to market broadly.
That probably matters almost as much as Telegram.

## Artifact / Inspector Debt
The user called out that some artifact/inspector areas still contain demo-ish content.

Recommendation:
- do not interrupt Telegram foundations for this immediately
- keep a cleanup lane for:
  - artifact panel mock remnants
  - stale demo labels
  - non-real inspector filler

That is a polish lane, not the next architecture lane.

## Proposed Parallel Lanes
### Codex
- messaging backend store + Telegram transport design
- session routing + provenance model
- approval integration points
- onboarding architecture and provider truth

### Claude
- frontend pass for real Messaging Settings
- onboarding/setup UX
- Telegram/session status surfaces in desktop UI
- artifact/inspector demo cleanup lane

### Gemini
- review session routing and approval model
- audit edge cases in cross-channel provenance
- sanity-check onboarding scope against likely user confusion

## Recommended Next Execution Plan
1. make messaging config real on the backend
2. wire Messaging Settings off mocks
3. define Telegram session-routing storage model
4. add inbound Telegram -> session path
5. only then add model selection UX and slash commands

## Why This Order
Because `chat anywhere` without:
- durable config
- session routing
- provenance

would feel flashy but brittle.

The right move is to make Telegram an extension of CopeNet, not a sidecar toy.
