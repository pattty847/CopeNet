// A pane's own legend and controls, drawn over it.
//
// Anchored with `IPaneApi.getHTMLElement()` — a first-class accessor — so this needs no
// knowledge of Lightweight Charts' internal markup and no arithmetic over summed pane
// heights. An earlier note in CHART_INDICATORS.md claimed no such API existed and gave that
// as the reason every reading lived in one stack over the price pane; it does exist, and a
// pane indicator's reading now sits in the pane it describes.

import { IndicatorControls } from './IndicatorControls';
import { legendColor, legendOutputs, type ComputedIndicator } from './compute';
import type { IndicatorRowActions } from './IndicatorRows';
import type { IndicatorPaneRect } from './useChartIndicators';

export function IndicatorPaneControls({
  rects,
  indicators,
  actions,
}: {
  rects: IndicatorPaneRect[];
  indicators: ComputedIndicator[];
  actions?: IndicatorRowActions;
}) {
  if (!rects.length) return null;
  const byId = new Map(indicators.map((indicator) => [indicator.instanceId, indicator]));

  return (
    <>
      {rects.map((rect) => {
        const indicator = byId.get(rect.instanceId);
        if (!indicator) return null;
        return (
          <div
            key={rect.instanceId}
            className="tw-panehead"
            // The row spans the pane so its label sits left and its controls sit right.
            // pointerEvents stays off on the strip itself — a transparent band across the
            // top of every pane would otherwise swallow crosshair and drag interactions.
            style={{ top: rect.top + 3, width: rect.width }}
          >
            <span className="tw-panehead__legend">
              <span className="tw-legend__swatch" style={{ background: legendColor(indicator) }} />
              <span className="tw-panehead__label">{indicator.label}</span>
              {indicator.insufficientHistory ? (
                <span className="tw-panehead__value" style={{ opacity: 0.6 }}>needs history</span>
              ) : (
                legendOutputs(indicator)
                  .filter((output) => output.latest != null)
                  .map((output) => (
                    <span key={output.key} className="tw-panehead__value" title={output.label} style={{ color: output.color }}>
                      {output.latest}
                    </span>
                  ))
              )}
            </span>
            {actions && <IndicatorControls indicator={indicator} actions={actions} />}
          </div>
        );
      })}
    </>
  );
}
