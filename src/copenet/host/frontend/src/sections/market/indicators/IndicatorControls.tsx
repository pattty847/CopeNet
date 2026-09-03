// Per-indicator controls: settings and remove, wherever the indicator is shown.
//
// The same pair appears on a price overlay's legend row and at the top-right of a pane, so
// they are one component. The gear opens the SAME `IndicatorSettings` form the Plots menu
// uses — two entry points onto one surface, not two surfaces.

import { useRef, useState } from 'react';
import { Settings2, X } from 'lucide-react';
import { MarketFloatingPopover } from '../MarketFloatingPopover';
import { IndicatorSettings } from './IndicatorSettings';
import type { ComputedIndicator } from './compute';
import type { IndicatorRowActions } from './IndicatorRows';
import { IndicatorAlertButton } from '../monitoring/TickerAlertContext';

export function IndicatorControls({
  indicator,
  actions,
}: {
  indicator: ComputedIndicator;
  actions: IndicatorRowActions;
}) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);
  const { instanceId } = indicator;

  return (
    <span className="tw-ind-controls">
      <IndicatorAlertButton indicator={indicator} />
      <button
        ref={anchor}
        type="button"
        className="tw-iconbtn tw-iconbtn--xs"
        data-active={open}
        aria-expanded={open}
        aria-label={`Settings for ${indicator.label}`}
        title={`${indicator.definition.name} settings`}
        onClick={() => setOpen((value) => !value)}
      >
        <Settings2 size={11} />
      </button>
      <button
        type="button"
        className="tw-iconbtn tw-iconbtn--xs"
        aria-label={`Remove ${indicator.label}`}
        title={`Remove ${indicator.definition.name}`}
        onClick={() => actions.onRemove(instanceId)}
      >
        <X size={11} />
      </button>

      <MarketFloatingPopover anchorRef={anchor} open={open} onClose={() => setOpen(false)} width={280}>
        <div className="tw-pop">
          <div className="tw-pop__head">
            <div className="tw-pop__title">{indicator.label}</div>
            <button type="button" className="tw-iconbtn" onClick={() => setOpen(false)} aria-label="Close settings">
              <X size={13} />
            </button>
          </div>
          <div className="tw-pop__body">
            <IndicatorSettings
              definition={indicator.definition}
              instance={indicator.instance}
              onConfigure={(patch) => actions.onConfigure(instanceId, patch)}
              onStyle={(outputKey, style) => actions.onStyle(instanceId, outputKey, style)}
              onDuplicate={() => actions.onDuplicate(instanceId)}
              onReset={() => actions.onReset(instanceId)}
              onRemove={() => { setOpen(false); actions.onRemove(instanceId); }}
            />
          </div>
        </div>
      </MarketFloatingPopover>
    </span>
  );
}
