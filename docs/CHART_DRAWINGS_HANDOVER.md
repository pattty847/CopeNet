# Chart Drawings Handover

Date: 2026-09-18

## Current state

The chart drawing workspace supports manual plotting, future projection, model-created drawings, selection, deletion, and basic editing. The current working tree contains the drawing implementation and the latest interaction fixes. It has not been committed or merged.

Current branch:

```text
claude/chart-menus-mobile
```

The branch already contains Claude's committed chart-menu work:

- `c1f9a57` — keep one chart menu open at a time and close an open drawing menu when the chart is tapped.

The current uncommitted working tree contains the chart drawing changes listed below. Preserve unrelated edits when committing or moving this work to another branch.

## User-facing features

### Drawing tools

The toolbar provides:

- Price level
- Price zone
- Trendline
- Extended trendline
- Horizontal ray
- Ray
- Vertical line
- Measurement
- Long/short position setup
- Parallel channel
- Anchored VWAP
- Fibonacci retracement
- Label
- Callout

The toolbar groups tools into Lines, Measure, Studies, and Annotate. On phones, the toolbar remains compact and usable.

### Future plotting

The chart reserves future whitespace after the latest real candle. Drawing anchors may extend into that whitespace, so trendlines, rays, zones, and related tools can project beyond the current candle.

The backend still rejects arbitrary timestamps for evidence-bound data. Future timestamps are accepted only for operator-created drawings. Captured candle resources remain unchanged and do not contain invented candles.

### Mobile drawing interaction

Multi-anchor tools use a click/tap sequence:

1. Select a drawing tool.
2. Tap or click the first anchor.
3. Move the pointer or finger to preview the next point with a dotted crosshair.
4. Tap or click the next anchor.
5. Repeat for tools that need a third anchor.

Escape cancels the active drawing gesture and returns to Select.

### Selection and deletion

Clicking a drawing in Select mode marks it as selected and shows an on-chart action bar. The action bar provides:

- Edit — opens the existing Drawings settings panel.
- Delete — sends the canonical chart delete operation.
- Deselect — clears the current selection.

Creating a drawing no longer opens the Chart Agent or switches to the Drawings panel automatically. The panel remains available through the Agent button or the explicit Edit action.

### Anchored VWAP

AVWAP stores one start anchor. The renderer calculates the cumulative typical-price volume weighting from that candle forward. The stored anchor is not replaced with a precomputed cumulative value.

### Model and backend integration

Manual and model-created drawings share the same chart workspace contract:

- `market.chart.apply` creates, updates, and deletes drawings.
- Backend validation uses one canonical `ChartObject` model.
- Owner metadata distinguishes agent drawings from operator drawings.
- Agent evidence and operator edits remain represented in the persisted document.

Anchor counts are enforced at the backend boundary:

| Drawing type | Anchors |
| --- | ---: |
| Level, label, horizontal ray, vertical line, AVWAP, callout | 1 |
| Zone, trendline, extended trendline, ray, measurement, Fibonacci | 2 |
| Position setup, parallel channel | 3 |

## Other related fixes

- Monitor sheets now use a fixed mobile-safe position, an explicit close button, Escape cancellation, and backdrop dismissal.
- The stale backend schema problem was identified and the running CopeNet backend processes were restarted so new drawing kinds loaded into the process.
- A regression test now validates every toolbar drawing kind at the `ApplyRequest` boundary.
- The existing future-anchor test verifies that operator drawings can extend beyond the latest captured candle.

## Important implementation areas

Backend:

- `src/copenet/core/market/chart_workspace/models.py` — chart object kinds and anchor-count validation.
- `src/copenet/core/market/chart_workspace/documents.py` — document validation, evidence binding, and future operator anchors.

Frontend:

- `src/copenet/host/frontend/src/sections/market/chartAgent/ChartWorkspaceToolbar.tsx` — drawing tool selection and help text.
- `src/copenet/host/frontend/src/sections/market/chartAgent/useChartWorkspace.ts` — document state, apply/delete/edit actions, model bridge, and selection state.
- `src/copenet/host/frontend/src/sections/market/drawings/useChartWorkspace.ts` — pointer gestures, anchor sequencing, crosshair, Escape cancellation, and drag updates.
- `src/copenet/host/frontend/src/sections/market/drawings/geometry.ts` — projection and hit testing.
- `src/copenet/host/frontend/src/sections/market/drawings/primitive.ts` — canvas rendering and derived AVWAP/measurement/setup geometry.
- `src/copenet/host/frontend/src/sections/market/CandleChart.tsx` — on-chart selection action bar.
- `src/copenet/host/frontend/src/sections/market/chartAgent/ChartDrawingsPanel.tsx` — existing settings editor, visibility controls, and batch undo.
- `src/copenet/host/frontend/src/sections/market/monitoring/MonitoringSheet.tsx` — monitor overlay close behavior.

## Verification completed

- Backend chart workspace tests: `23 passed`.
- Frontend TypeScript check: passed.
- Frontend test suite: `631 passed`.
- Frontend production build and alerts bundle: passed.
- `git diff --check`: passed.

## Deliberately deferred

### Magnet mode

Magnet mode is not implemented yet. It should be designed as one shared snap policy for both manual and model-created drawings, rather than as a frontend-only pointer adjustment.

Recommended model:

- Off — preserve the exact pointer price and time.
- Low — snap to the nearest relevant candle high, low, open, or close.
- High — snap to the selected series or indicator value with an explicit source field.

The snap result should remain visible in the UI and should preserve the original pointer location when useful for auditability. The backend should validate any declared snap source in the same way it validates evidence fields.

### Expanded drawing settings

The current Edit action opens the existing Drawings panel. A later pass can move common settings into an on-chart popover or double-click editor. Keep the operation model canonical so both the UI and models use the same update path.

### Selection architecture

The current action bar is intentionally small. A larger TradingView-style selection system can later add anchor handles, style controls, lock/hide state, duplicate, and undo without changing the core `ChartObject` and `ChartOperation` contracts.

## Tailscale note

Tailscale was not restarted during this work. The current local status check reports the Mac online and the Tailscale CLI at version `1.102.2`. Restart it separately only when the operator wants a network service restart.

## Suggested next step

Before merging, review the combined working tree, test the selection action bar on phone and desktop, then design the magnet contract and model-facing snap semantics as a separate change.
