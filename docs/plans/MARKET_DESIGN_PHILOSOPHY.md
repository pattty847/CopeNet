# CopeNet Market Design Philosophy

CopeNet Market is a dense, calm, evidence-first analytical workspace. It should feel composed for repeated professional use, not assembled from feature cards.

## Hierarchy

Every asset workspace follows one sequence:

**Asset → Chart → Context → Investigation → Model synthesis**

The chart is the visual anchor. Identity and quote orient the operator; a compact context strip follows the chart; deeper deterministic, fundamental, SEC, portfolio, and synthesis work lives in a lower research dock. Permanent space is earned by frequency, urgency, or active state.

## Spacing and density

- Use a compact spacing scale: `2, 4, 8, 12, 16, 24px`.
- Prefer alignment, proximity, and concise labels over extra containers.
- Desktop controls are normally `28–32px` high; touch layouts use at least `40–44px` targets.
- Dense analytical rows use `11–12px` text with tabular numerals. Interface metadata should not fall below `10.5px`; smaller type is reserved for chart axes.
- Containers hug their content. Never preserve large empty geometry merely to equalize cards.

## Borders, radii, and surfaces

- Borders separate true regions or interaction groups; they are not the default way to create hierarchy.
- Use one-pixel restrained borders with semantic strengths: subtle, default, emphasis.
- Use `0` radius inside segmented tool rails, `4px` for controls, `6px` for panels, and `8px` for raised popovers. Pills are reserved for genuine statuses or counts.
- Prefer plain layout and rules to mosaics of cards. Chart canvas, research dock, inspector, and popover are distinct surface types.

## Typography

- Asset symbols, quotes, prices, dates, and metrics use monospace with tabular numerals.
- Interface labels and analytical prose use the sans family.
- Use type roles rather than ad hoc sizes: asset title, quote, body, dense row, metadata, overline, chart axis.
- Serif display type does not belong in the compact Market workspace.
- Density must come from structure, never low contrast or eye-straining type.

## Control hierarchy

Chart controls are organized by analytical task:

1. interval and visible range;
2. price/comparison mode;
3. scale;
4. overlays and event-marker presentation;
5. durable actions such as alerts.

Mutually exclusive choices use segmented controls. Toggles expose selected state. Menu triggers use labels and disclosure indicators. Durable state remains visible in the trigger (`Alert · 2`, `Overlays · P/E`, `Events · 8-K, 144`). Essential actions stay outside overflow; horizontal scrolling is a narrow-layout fallback.

## Icons

- Lucide is the canonical interface icon set already used by CopeNet.
- Use icons when recognition is faster than text: search, back, alert, settings, close, expand.
- Keep text for obscure financial actions. Do not replace clear labels with decorative glyphs.
- Conventional market notation may remain when it communicates data rather than an interface action.

## Color and states

- Orange is the CopeNet brand/action/focus accent.
- Green and red are reserved for financial direction and positive/negative market evidence.
- Blue is analytical/informational, not a competing generic selected color.
- Every control defines default, hover, focus-visible, pressed/selected, disabled, loading, and error states where applicable.
- Selected state must be recognizable without reopening a menu. Focus is always visible.

## Progressive disclosure

- Popover: compact chart-control configuration.
- Research dock tabs: sibling analytical modes that benefit from chart context.
- Inspector/drawer: source detail or temporary context while preserving the page.
- Modal: blocking or consequential tasks only.
- Do not create permanent sidebars for occasional context. Do not bury primary evidence in nested scroll regions.

## Chart dominance

- The chart receives full workspace width by default.
- Chart height is viewport-aware so the lower dock's tab rail remains reachable on common laptop screens.
- Width changes are preferred over dynamic chart-height animation; the chart engine should not be recreated for decorative transitions.
- Chart presentation controls and source investigation are separate: event-marker visibility belongs in the toolbar; SEC filing depth, refresh, filtering, and provenance belong in the SEC tab.

## Navigation between assets

- A compact Switch control opens the shared ticker search plus Watchlist, Recent, and Holdings groupings; it never creates another permanent rail.
- Keyboard navigation is first-class: command shortcut, arrows, and Enter.
- Switching assets deliberately preserves reusable view state and serializes it into the URL. State must never remain visible while disappearing from the shareable route.
- Asset identity is resilient to duplicate or long company names.

## Context and investigation

- The post-chart context strip shows only current orientation or exceptions that matter across every research tab.
- High-signal evidence appears only when present and opens the matching SEC investigation.
- Position context appears only for held assets; full position detail lives in a conditional Overview section.
- Data status aggregates price, SEC, fundamentals, and contextual-source freshness. Normal provenance is disclosed; warnings are promoted.
- Overview distinguishes measured state, calibrated setups, benchmark context, and deterministic risk conditions.
- SEC and Fundamentals use full-width, inspectable rows with source and chart-focus affordances.

## Model synthesis

- Synthesis is a research-dock destination, not a detached card or a second toolbar action.
- The default workflow stays one click.
- The UI states exactly which fixed evidence frame the current backend uses and does not imply that ad hoc zoom, overlays, or chart settings are automatically included.
- Queued, running, failed, stale, completed, and re-run states remain legible. Model-authored thesis invalidation stays distinct from deterministic risk conditions.
- Configurable presets, horizons, benchmarks, evidence sources, and analytical emphasis require a deliberate backend contract and are not simulated in frontend-only UI.

## Ticker-page proving ground

The selected structure is a full-width chart with a compact post-chart context strip and a tabbed lower research dock. A collapsible right inspector remains useful for item-level detail; a resizable terminal split is a future power-user evolution, not the default first implementation.

This page establishes reusable principles for later Market cleanup. It does not authorize redesigning unrelated CopeNet surfaces.

## Market workstation

The Market landing page applies the same grammar at market level as a **sectioned
workstation**. Its hierarchy is:

**Market → What changed → Standing picture → Investigation → Model synthesis**

Fixed chrome around one scrolling body. The market bar orients (regime, data freshness, VIX,
breadth, density); the watch rail is the watchlist as navigation — every row opens an asset
workspace, `j`/`k`/Enter step and commit, list management lives in the rail head, removal
offers an undo, and the rail starts collapsed below 1366px; a flat row of section tabs
(Briefing, Structure, Signals, Portfolio, Evidence, Ledger, Backtest — keys `1`–`7`) is a
route (`/market?view=…`) and doubles as an inbox with "new since you opened it" counts.

Briefing is home: the sweep's sentence is the page headline; "what changed" (regime, a ranked
Matters table fed by the brief's flag-first composer and capped with an explicit
"6 of N · all →", movers, book, next 7d, ledger) and the model synthesis stack on the left;
the standing picture (regime scale, tape grid, rates stub, rotation quadrants, flagged
setups) runs down the right. Every other section takes the whole body: nothing on the market
page is split, because nothing here must stay visible while something else is read. The
ticker workspace keeps its research dock for exactly that reason.

Customization is constrained on purpose: per section, panels can be reordered, hidden, and set
half or full width where they support it; the shell remembers rail state and density. Free
positioning and free height are not offered. Phones get a preset one-column layout with the
watchlist as its own tab.
