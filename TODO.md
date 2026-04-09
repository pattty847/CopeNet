# CopeNet TODO

## Backend

- Decide final local auth behavior: explicit configured token, optional no-auth for local dev, or a cleaner hybrid.
- Tighten provider metadata into a sharper typed boundary instead of loose dict capability shapes.
- Review remaining implementation-heavy package `__init__.py` files and split further only when it clearly reduces indirection.

## Testing

- Add websocket/RPC end-to-end integration tests for `connect`, `chat.send`, `chat.history`, `sessions.*`, and `tools.list`.
- Add integration coverage for archive/restore behavior once archived sessions can be resurfaced.
- Add provider adapter tests for LM Studio and Ollama response mapping where practical.
- Add a scripted browser smoke workflow once the new frontend is in place.

## Frontend

- Build the new React + Vite SPA against the existing FastAPI/WebSocket backend.
- Add archived session resurfacing and restore from day one in the new UI.
- Port current runtime/model/profile/task controls into the new client state model.
- Keep tool-trace visibility in the new chat UI.

## Product / UX

- Add archived session filter/restore UX.
- Decide whether codex/local runtime availability and auth state should be more visible in the UI.
- Improve tool failure messaging so policy blocks and real execution failures are easier to distinguish.

## Deferred / Maybe

- Multi-tool-per-turn orchestration once the single-tool loop is stable and well-tested.
- Richer provider capability surfacing in the UI.
- Future feature work around tool mode/profile controls and bridge ideas after frontend migration.
