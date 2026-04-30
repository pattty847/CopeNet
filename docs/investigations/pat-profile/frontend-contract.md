# Pat Profile v1 — Current Contract

**Status:** Shipped and wired end-to-end.  
**Frontend lane lead:** Claude  
**Backend / runtime owner:** Codex

This doc is now a compact reality check, not a speculative handoff.

## What exists today

Pat Profile v1 is live across three layers:

- **Backend identity substrate**
  - layered profile loading
  - conservative post-run maintenance
  - append-only changelog
  - return briefing generation
- **RPC / event layer**
  - bootstrap RPCs for profile, changelog, and briefing
  - push events for profile changes and ready briefings
- **Frontend shell**
  - Home profile card
  - Home return briefing shell
  - profile changelog surface
  - subtle Agents runtime indicator

## File map

| File | Role |
|---|---|
| `src/copenet/core/profile/service.py` | loader, merge logic, changelog append, return briefing builder |
| `src/copenet/core/profile/templates/` | generic repo-visible templates |
| `src/copenet/host/rpc_catalog.py` | `profile.get`, `profile.changelog`, `briefing.get` |
| `src/copenet/host/rpc_chat.py` | forwards side events alongside chat events |
| `src/copenet/host/ws_server.py` | advertises profile / briefing methods and events |
| `src/copenet/host/frontend/src/lib/wsClient.ts` | bootstrap + push-event wiring |
| `src/copenet/host/frontend/src/components/profile/` | operator-facing profile / briefing surfaces |

## Current wire contract

### RPCs

| Method | Payload |
|---|---|
| `profile.get` | `{ profile: PatProfile | null }` |
| `profile.changelog` | `{ changelog: ProfileChangelogItem[] }` |
| `briefing.get` | `{ briefing: ReturnBriefingPayload | null }` |

### Push events

| Event | Payload |
|---|---|
| `profile.changed` | `{ profile: PatProfile | null, change: ProfileChangelogItem }` |
| `briefing.ready` | `{ briefing: ReturnBriefingPayload }` |

## Product behavior

### Home

- shows a compact Pat Profile status card
- can render the return briefing above the hero area
- includes a **dev-only** preview trigger for the briefing shell until real briefing flows become the primary path

### Agents

- shows a subtle profile-active indicator in the runtime rail
- does **not** turn the runtime rail into a profile-management surface

### Empty states

Current empty states are intentional and useful:

- `No profile overlay yet`
- `No profile changes yet`
- no briefing shown unless one is present or the dev preview is enabled

## Privacy boundary

This is the important line:

- **safe to commit:** generic templates, example docs, UI shells, loader/service code
- **do not commit:** real local overlay data from `~/.copenet/profile/` or `COPNET_DATA_DIR/profile`

The public repo should explain the shape of the system, not contain the operator's real life data.

## Remaining debt

These are the still-real follow-ups, in plain English:

1. tighten the actual profile update heuristics beyond the first conservative rules
2. decide when the Home dev briefing trigger should be removed
3. add explicit dismissal / acknowledgement semantics for briefings if the product starts relying on them more heavily
4. keep frontend copy honest as the profile layer grows beyond v1

## Keep / remove guidance

Good to keep:

- this doc as a current contract snapshot
- the generic templates
- the privacy boundary note

Good to remove later:

- any temporary dev-preview notes once the briefing is fully normal-flow
- any comments that claim the backend is “not shipped”
