# CopeNet Apple Agents Prototype

A standalone SwiftUI exploration of CopeNet's Agents panel. It does not import
or modify the CopeNet backend or React frontend.

![Native CopeNet Agents overview](Screenshots/agents-overview.jpeg)

## Run

```sh
cd prototypes/CopeNetApple
swift run CopeNetApple
```

The package uses only Apple frameworks and mocked data behind
`AgentRepository`. The included build script creates a double-clickable macOS
app bundle in `.build/CopeNet Agents.app`.

```sh
./scripts/build-app.sh
open ".build/CopeNet Agents.app"
```

## Data boundary

`MockAgentRepository` is the only current data source. A live implementation can
replace it with a WebSocket repository that maps CopeNet's existing
`providers.list`, `sessions.list`, `sessions.history`, and run/activity RPC
responses into `AgentProfile` values. Starting a session would delegate to the
same session-create/chat-send flow already used by the web client.

## Prototype interaction

Selecting an agent updates the workspace and inspector. The enabled toggle is
live in memory, and **Start New Session** opens a native sheet with a responsive
message composer.

![Native new-session sheet](Screenshots/session-sheet.jpeg)
