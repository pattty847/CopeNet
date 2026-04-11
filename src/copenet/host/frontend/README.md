# CopeNet React Frontend

React + Vite frontend for the CopeNet WebSocket gateway.

## Local Development

Prerequisites:
- Node.js
- running CopeNet backend (`uv run cope`)

Setup:
1. `npm install`
2. optionally create `.env.local` from `.env.example`
3. `npm run dev`

Notes:
- set `VITE_COPNET_WS_URL` when running the frontend separately from the backend host
- when built and served by CopeNet, the frontend defaults to the same-origin `/ws`
- auth token resolution falls back to `window.COPNET_TOKEN`, `localStorage`, meta tag, or `dev-token`
