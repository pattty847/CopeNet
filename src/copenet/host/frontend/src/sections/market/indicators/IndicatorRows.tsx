// Active-indicator rows for the Plots menu.
//
// THE SPLIT: the chart is where you tune what you can SEE; this list is where you manage the
// SET. Settings and remove live on the chart itself — on a price overlay's legend row and on
// each pane's head — so they are not duplicated into an inline panel here. Two things have no
// chart affordance and so live only here: unhiding (a hidden indicator has no chart presence
// at all, which makes this the only way back) and pane order.
//
// The gear on a row opens the same popover the chart's own gears open. One settings surface,
// three doors onto it.

import { ChevronDown, ChevronUp, Eye, EyeOff } from 'lucide-react';
import { IndicatorControls } from './IndicatorControls';
import { legendColor, legendOutputs, type ComputedIndicator } from './compute';
import type { IndicatorConfig } from './types';
import type { IndicatorInstance, IndicatorStyle } from './state';

export interface IndicatorRowActions {
  onConfigure: (instanceId: string, patch: IndicatorConfig) => void;
  onStyle: (instanceId: string, outputKey: string, style: IndicatorStyle) => void;
  onVisibility: (instanceId: string, visible: boolean) => void;
  onDuplicate: (instanceId: string) => void;
  onReset: (instanceId: string) => void;
  onRemove: (instanceId: string) => void;
  onMove: (instanceId: string, delta: number) => void;
}

export function IndicatorRows({
  instances,
  computed,
  actions,
}: {
  instances: IndicatorInstance[];
  computed: ComputedIndicator[];
  actions: IndicatorRowActions;
}) {
  if (!instances.length) return null;
  const byId = new Map(computed.map((indicator) => [indicator.instanceId, indicator]));

  return (
    <div className="tw-ind-rows">
      {instances.map((instance, index) => {
        const indicator = byId.get(instance.instanceId);
        if (!indicator) return null;
        // One reading per row. A three-output indicator printing all three turns a compact
        // list into a table, and the chart already carries the full set.
        const reading = legendOutputs(indicator).find((output) => output.latest != null)?.latest;

        return (
          <div key={instance.instanceId} className="tw-ind-row">
            <div className="tw-ind-row__head">
              <span className="tw-ind-row__swatch" style={{ background: legendColor(indicator) }} aria-hidden="true" />
              <span className="tw-ind-row__label" title={indicator.definition.name}>{indicator.label}</span>
              <span className="tw-ind-row__value">
                {indicator.insufficientHistory ? 'needs history' : reading ?? '—'}
              </span>
              <span className="tw-ind-row__actions">
                {/* Order only means something below the price pane. */}
                {indicator.placement === 'pane' && (
                  <>
                    <button
                      type="button"
                      className="tw-iconbtn tw-iconbtn--xs"
                      onClick={() => actions.onMove(instance.instanceId, -1)}
                      disabled={index === 0}
                      aria-label={`Move ${indicator.label} up`}
                      title="Move up"
                    >
                      <ChevronUp size={11} />
                    </button>
                    <button
                      type="button"
                      className="tw-iconbtn tw-iconbtn--xs"
                      onClick={() => actions.onMove(instance.instanceId, 1)}
                      disabled={index === instances.length - 1}
                      aria-label={`Move ${indicator.label} down`}
                      title="Move down"
                    >
                      <ChevronDown size={11} />
                    </button>
                  </>
                )}
                <button
                  type="button"
                  className="tw-iconbtn tw-iconbtn--xs"
                  onClick={() => actions.onVisibility(instance.instanceId, !instance.visible)}
                  aria-pressed={!instance.visible}
                  aria-label={`${instance.visible ? 'Hide' : 'Show'} ${indicator.label}`}
                  title={instance.visible ? 'Hide' : 'Show — the only way back once hidden'}
                >
                  {instance.visible ? <Eye size={12} /> : <EyeOff size={12} />}
                </button>
                <IndicatorControls indicator={indicator} actions={actions} />
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
