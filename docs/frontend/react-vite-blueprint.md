# CopeNet React + Vite Frontend Blueprint

This blueprint is the handoff spec for generating the new frontend with Gemini or another codegen assistant. The backend remains FastAPI + WebSocket RPC. The frontend is a React + Vite SPA that replaces the current vanilla browser app.

## Product Intent

Build a local-first agent console that feels deliberate, fast, and operator-grade rather than like a generic chat clone.

The UI should make these things obvious:

- what runtime/provider is active
- what model/profile/task mode is active
- whether the current session is a draft or a locked conversation
- what tool activity happened during a turn
- how to find archived sessions again

## App Shape

- React + Vite SPA
- TypeScript preferred
- No SSR requirement
- FastAPI remains the backend
- WebSocket RPC remains the primary live transport
- The React app can be served separately during development and later mounted or proxied into the existing backend setup

## Screens And Layout

### Primary layout

- Left rail:
  - session list
  - session search/filter
  - archived toggle
  - new chat action
- Main panel:
  - active session header
  - runtime/model/profile/task badges
  - lock/draft status
  - scrollable message timeline
  - tool trace blocks inline or attached to assistant turns
- Composer area:
  - prompt input
  - send/stop actions
  - draft configuration controls before first send

### Required views/states

- empty state for no sessions
- draft session state before first send
- locked session state after first send
- archived sessions list/filter state
- disconnected/auth failed state
- provider unavailable state

## Component Architecture

Recommended top-level structure:

- `AppShell`
- `SessionSidebar`
- `SessionList`
- `SessionRow`
- `ChatWorkspace`
- `ChatHeader`
- `SessionBadges`
- `MessageTimeline`
- `MessageBubble`
- `ToolTracePanel`
- `Composer`
- `DraftConfigPanel`
- `ConnectionBanner`
- `ArchiveFilterToggle`

Recommended supporting layers:

- websocket/RPC client service
- app state store for session catalog, active session, draft state, provider/model catalogs, prompts, connection state, and in-flight runs
- typed transport models matching current RPC methods/events

## State Model

The client should explicitly track:

- connection status
- auth failure status
- provider catalog
- model catalog
- profile catalog
- task mode catalog
- session catalog
- archived session visibility filter
- current session key
- draft session config
- active run id
- message history for the selected session
- optimistic UI state for streaming assistant output

Prefer one central state layer over scattered component-local transport state. Zustand or React context + reducer are both acceptable; avoid over-engineered state abstraction.

## Backend Contract Usage

The frontend should use the existing backend contract as-is:

- `connect`
- `chat.send`
- `chat.abort`
- `chat.history`
- `providers.list`
- `models.list`
- `tools.list`
- `sessions.list`
- `sessions.create`
- `sessions.rename`
- `sessions.archive`
- `sessions.resolve`

Expected event stream:

- `connect.challenge`
- `chat`

Important behavior assumptions to preserve:

- sessions lock to provider/model/profile/task mode after first send
- archived sessions are hidden by default but must be recoverable in the new UI
- tool execution metadata remains attached to assistant turns
- the current backend still supports one-tool-per-turn behavior in the harness

## Archived Session Flow

This must exist in v1 of the React frontend.

Required behavior:

- sidebar has an archived filter or archived tab
- archived sessions can be listed without leaving the main app
- archived sessions can be restored
- restoring a session returns it to the active list
- archive status should be visually obvious in the session list and active header

If the backend needs a small extension for listing archived sessions or unarchiving conveniently, plan it explicitly rather than hiding archived state in the client.

## Visual Direction

Do not build a generic AI chat clone.

Design direction:

- local developer workstation feel
- intentional typography
- strong information hierarchy
- visible operational state
- restrained but meaningful motion
- surfaces that make tool execution and session state feel first-class

Avoid:

- generic centered chat layout
- soft default SaaS styling
- hiding system/runtime context

## Migration Strategy

Phase 1:

- build React app against the current backend
- keep the vanilla UI available while the React app is being validated

Phase 2:

- reach parity on session flow, chat flow, tool trace visibility, and archive handling

Phase 3:

- switch the default frontend to React
- retire the vanilla static UI once parity and smoke coverage are confirmed

## Acceptance Criteria

The React frontend blueprint is complete when:

- Gemini can generate a React + Vite app without needing backend contract decisions invented on the fly
- archived sessions are part of the design from the start
- component boundaries, state ownership, and transport usage are explicit
- the frontend can be built without changing current backend semantics first
