// Active-indicator rows for the Plots menu.
//
// One row per configured indicator: colour, label, current reading, and three affordances —
// show/hide, settings, remove. Settings expand IN PLACE below the row rather than opening a
// second surface, because the whole popover exists to answer "what is on my chart" and a
// nested dialog would put the answer behind another click.
//
// Deliberately no descriptions here. Discovery belongs in the picker; this list is for an
// operator who already knows what they added and wants to change one number.

import { ChevronDown, ChevronUp, Eye, EyeOff, Settings2, X } from 'lucide-react';
import { IndicatorSettings } from './IndicatorSettings';
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
  expanded,
  onToggleExpanded,
  actions,
}: {
  instances: IndicatorInstance[];
  computed: ComputedIndicator[];
  expanded: string | null;
  onToggleExpanded: (instanceId: string | null) => void;
  actions: IndicatorRowActions;
}) {
  if (!instances.length) return null;
  const byId = new Map(computed.map((indicator) => [indicator.instanceId, indicator]));

  return (
    <div className="tw-ind-rows">
      {instances.map((instance, index) => {
        const indicator = byId.get(instance.instanceId);
        if (!indicator) return null;
        const open = expanded === instance.instanceId;
        // One reading per row. A three-output indicator printing all three turns a compact
        // list into a table; the primary series is what the row is identified by.
        const reading = legendOutputs(indicator).find((output) => output.latest != null)?.latest;

        return (
          <div key={instance.instanceId} className="tw-ind-row" data-open={open}>
            <div className="tw-ind-row__head">
              <span
                className="tw-ind-row__swatch"
                style={{ background: legendColor(indicator) }}
                aria-hidden="true"
              />
              <span className="tw-ind-row__label" title={indicator.definition.name}>{indicator.label}</span>
              <span className="tw-ind-row__value">
                {indicator.insufficientHistory ? 'needs history' : reading ?? '—'}
              </span>
              <span className="tw-ind-row__actions">
                {/* Order matters only below the price pane, so the controls appear only there. */}
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
                  title={instance.visible ? 'Hide' : 'Show'}
                >
                  {instance.visible ? <Eye size={12} /> : <EyeOff size={12} />}
                </button>
                <button
                  type="button"
                  className="tw-iconbtn tw-iconbtn--xs"
                  data-active={open}
                  onClick={() => onToggleExpanded(open ? null : instance.instanceId)}
                  aria-expanded={open}
                  aria-label={`Settings for ${indicator.label}`}
                  title="Settings"
                >
                  <Settings2 size={12} />
                </button>
                <button
                  type="button"
                  className="tw-iconbtn tw-iconbtn--xs"
                  onClick={() => actions.onRemove(instance.instanceId)}
                  aria-label={`Remove ${indicator.label}`}
                  title="Remove"
                >
                  <X size={12} />
                </button>
              </span>
            </div>

            {open && (
              <IndicatorSettings
                definition={indicator.definition}
                instance={instance}
                onConfigure={(patch) => actions.onConfigure(instance.instanceId, patch)}
                onStyle={(outputKey, style) => actions.onStyle(instance.instanceId, outputKey, style)}
                onDuplicate={() => actions.onDuplicate(instance.instanceId)}
                onReset={() => actions.onReset(instance.instanceId)}
                onRemove={() => actions.onRemove(instance.instanceId)}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
