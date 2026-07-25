# Fleet Rooms

Fleet is CopeNet's durable multi-model collaboration surface. The manual-mode MVP pairs one `openai-codex` lane with one `claude-cli` lane inside a product-visible room.

## Product contract

- Only one Fleet room may be active at a time; the server enforces this.
- `@everyone` starts both provider turns from the same committed room snapshot.
- Neither lane receives the other lane's current answer. Both attempts finish before answers are committed to the room.
- `@chatgpt` and `@claude` address who responds, not who may eventually read the event.
- Peer text is attributed, delimited, and explicitly rendered as untrusted information rather than operator authority.
- Read-only tool use is shared as a bounded receipt (tool id, status, summary, preview). A peer may rerun the tool when it needs the full result.
- Operator prompts may be queued while a lane is working. Room execution is serialized per room while `@everyone` participants run concurrently inside one turn.

## Truth and persistence

The append-only room event store is product truth. Hidden `fleet_lane` sessions exist only to preserve each provider's native continuity and harness transcript.

- Room events: `<sessions root>/fleet/rooms.json`
- Lane sessions: ordinary `SessionStore` entries with `session_type="fleet_lane"`, `parent_session_key=<room id>`, and `participant_id`.
- Normal session listing, search, Pulse, briefing, and external session APIs do not receive Fleet lanes because `SessionStore.list_sessions()` excludes them by default.
- Archiving a room cascades to its lanes. Lanes cannot be archived directly through the public session facade.
- Failed setup lanes are archived, never deleted, preserving append-only session semantics.

The UI always renders Fleet from room events, never from lane transcripts.

## Context renderer and delivery cursor

`FleetCoordinator._render_updates()` is the reveal-barrier enforcement point. A lane receives only committed room events after its delivery cursor, excluding its own authored room events. The renderer identifies every event's author and kind and places content inside the Fleet update envelope.

The cursor advances only in `FleetRoomStore.commit_lane_turn()`, in the same atomic write that appends the successful assistant answer. A failed provider turn appends an error event and leaves its cursor unchanged, so evidence is not silently dropped.

The two concrete runtime paths are deliberately tested separately:

- OpenAI Codex: CopeNet-native API harness and tool loop.
- Claude CLI: resumable CLI provider with Fleet updates injected into the next lane turn.

## Shipped MVP

- Durable room create/list/get/send/archive RPCs and `fleet.event` broadcasts.
- Independent-first `@everyone` barrier plus targeted follow-up turns.
- Background execution and reconnect-safe room bootstrap.
- Attributed Markdown room UI, participant queue state, tool receipts, and Fleet-specific inspector.
- `market.evidence`, a bounded SEC/fundamentals evidence tool available to any normal or Fleet lane.
- Per-session frontend run, approval, tool, composer, and attachment state so background sessions cannot overwrite one another.

## Deferred coordinator work

Roundtable automation is intentionally deferred until the manual room is dogfooded. The next layer can add a two-round state machine and a real `fleet.signal` tool with `continue | yield | ask_operator | blocked`. Missing signals should default to `yield`. A restart during an automated round must mark the attempt failed and offer an explicit retry; it must never silently rerun and spend twice.

Configurable rounds, synthesis modes, evidence dereferencing, Market-to-Fleet handoff, cost totals, and multiple simultaneous rooms remain later work.

## Verification

Automated coverage asserts:

- server-side one-active-room enforcement;
- hidden lane sessions and archive cascade;
- same-snapshot `@everyone` execution with no current-round peer leakage;
- attributed peer delivery on a later targeted turn;
- no cursor advance after provider failure;
- event deduplication and per-participant queued-work counts;
- Fleet RPC discovery and end-to-end WebSocket event delivery.

Live dogfood on 2026-07-17 used ChatGPT and Claude to independently analyze AAPL with `market.ticker` and `market.evidence`. Both called the tools, both receipts appeared after reveal, and a later `@claude` turn quoted and challenged ChatGPT's committed claim through Claude CLI continuity without rerunning evidence.
