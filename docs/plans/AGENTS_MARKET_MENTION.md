# Agents Composer: @mention for market symbols

Status: implemented 2026-07-03 (frontend only, no backend changes).

## Context

`market.dashboard` and `market.ticker` tools already exist
(`src/copenet/core/tools/handlers/market.py`), registered in the `context` policy
category so they're available in every task mode. Live-verified: a chat session asked
to summarize the regime called `market.dashboard` on its own. The open gap was purely
UI — no way to reference a ticker from the Agents composer.

## Decision

**@mention is an insertion helper, not a context-injection mechanism.** Selecting a
symbol from the popup inserts plain `@XLK` text into the message; nothing is injected
or rewritten before send. This matches the harness philosophy (`AGENTS.md` /
`project_harness_philosophy` memory): no keyword classifiers, no hidden coercion layer.
The model already has the tools and their descriptions tell it to prefer live lookups
over guessing — a mention is just a fast, correct way to type a symbol, with the model
free to call `market.ticker`/`market.dashboard` as it already does.

If plain `@XLK` text turns out to be an unreliable trigger for tool use in practice,
the next iteration is a **visible** composer-side hint appended to the sent text (e.g.
`[Mentioned: XLK, SPY]`), never a hidden system-only injection — "UI stays honest."
Not built yet; revisit only if live probing shows the model ignoring mentions.

## What shipped

- `AgentComposer.tsx`: typing `@` followed by 1+ word characters opens a floating
  popup, positioned above the composer (same pattern as `RuntimeMenu`).
- Candidates come from `wsClient.marketUniverse()` (existing RPC, backs the Market
  page), fetched once and cached locally in component state — no store slice added.
- Filtering: case-insensitive prefix/substring match against symbol and name, capped
  to 8 results.
- Keyboard: ArrowUp/ArrowDown to move selection, Enter/Tab to accept, Escape to close.
  These are intercepted ahead of the existing send-on-Enter handler only while the
  popup is open.
- Mouse: click a candidate to insert.
- Insertion replaces the in-progress `@query` at the cursor with `@SYMBOL ` (trailing
  space, cursor lands after it).
- No matches (or universe fetch failure) closes the popup silently — typing an
  arbitrary `@word` never blocks the composer.

## Explicitly out of scope (unchanged from handoff)

- No context-blob injection into the prompt.
- No restriction/auto-suggestion of browsing sources by mention — `web.fetch`
  allowlist (`COPNET_WEB_FETCH_ALLOWLIST`) remains the only source control, opt-in.
- No mention support outside the Agents composer (e.g. no mention chips in rendered
  transcript messages).
