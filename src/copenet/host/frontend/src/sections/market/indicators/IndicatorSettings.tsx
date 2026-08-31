// The settings form for one configured indicator.
//
// Generated entirely from the registry's `inputs` and `outputs`. Adding an indicator with a
// new kind of setting means adding it to that indicator's `inputs` array — no component here
// changes, and no indicator gets bespoke UI.
//
// Progressive disclosure is by DECLARED IMPORTANCE, not by count: an input marked `advanced`
// sits behind the disclosure however few of them there are. Source selection and second-order
// smoothing lengths are advanced on every indicator that has them, because the length and the
// multiplier are what an analyst actually reaches for.

import { useId, useState } from 'react';
import { ChevronDown, Copy, RotateCcw, Trash2 } from 'lucide-react';
import { INDICATOR_SOURCES } from './types';
import type { IndicatorConfig, IndicatorDefinition, IndicatorInput } from './types';
import type { IndicatorInstance, IndicatorStyle } from './state';

export function IndicatorSettings({
  definition,
  instance,
  onConfigure,
  onStyle,
  onDuplicate,
  onReset,
  onRemove,
}: {
  definition: IndicatorDefinition;
  instance: IndicatorInstance;
  onConfigure: (patch: IndicatorConfig) => void;
  onStyle: (outputKey: string, style: IndicatorStyle) => void;
  onDuplicate: () => void;
  onReset: () => void;
  onRemove: () => void;
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const fieldIdPrefix = useId();
  const basic = definition.inputs.filter((input) => !input.advanced);
  const advanced = definition.inputs.filter((input) => input.advanced);

  return (
    <div className="tw-ind-settings">
      {definition.description && <p className="tw-ind-settings__note">{definition.description}</p>}

      {basic.map((input) => (
        <InputRow key={input.key} idPrefix={fieldIdPrefix} input={input} config={instance.config} onConfigure={onConfigure} />
      ))}

      <div className="tw-ind-settings__styles">
        {definition.outputs.map((output) => (
          <label key={output.key} className="tw-ind-swatch" title={`${output.label} colour`}>
            <input
              type="color"
              value={instance.styles?.[output.key]?.color ?? output.color}
              onChange={(event) => onStyle(output.key, { color: event.target.value })}
              aria-label={`${output.label} colour`}
            />
            <span>{output.label}</span>
          </label>
        ))}
      </div>

      {advanced.length > 0 && (
        <>
          <button
            type="button"
            className="tw-ind-more"
            aria-expanded={showAdvanced}
            onClick={() => setShowAdvanced((value) => !value)}
          >
            Advanced <ChevronDown size={11} data-open={showAdvanced} />
          </button>
          {showAdvanced && advanced.map((input) => (
            <InputRow key={input.key} idPrefix={fieldIdPrefix} input={input} config={instance.config} onConfigure={onConfigure} />
          ))}
        </>
      )}

      <div className="tw-ind-settings__actions">
        <button type="button" className="tw-btn tw-btn--sm" onClick={onDuplicate} title="Add a second copy of this indicator">
          <Copy size={11} /> Duplicate
        </button>
        <button type="button" className="tw-btn tw-btn--sm" onClick={onReset} title="Back to the default settings">
          <RotateCcw size={11} /> Reset
        </button>
        <button type="button" className="tw-btn tw-btn--sm" onClick={onRemove} title={`Remove ${definition.name}`}>
          <Trash2 size={11} /> Remove
        </button>
      </div>
    </div>
  );
}

function InputRow({
  idPrefix,
  input,
  config,
  onConfigure,
}: {
  idPrefix: string;
  input: IndicatorInput;
  config: IndicatorConfig;
  onConfigure: (patch: IndicatorConfig) => void;
}) {
  // Settings can be opened from the Plots list and the chart at the same time. React's
  // per-component prefix keeps every label bound to its own control across both portals.
  const id = `${idPrefix}-ind-${input.key}`;
  return (
    <div className="tw-ind-field">
      <label htmlFor={id}>{input.label}</label>
      {input.kind === 'number' && (
        <input
          id={id}
          type="number"
          className="tw-input tw-ind-number"
          value={String(config[input.key] ?? input.default)}
          min={input.min}
          max={input.max}
          step={input.step}
          // Committed on change rather than on blur so the chart tracks the stepper. The
          // value is normalised against the registry bounds on the way into state, so an
          // out-of-range keystroke can never reach a compute loop.
          onChange={(event) => {
            const next = Number(event.target.value);
            if (Number.isFinite(next)) onConfigure({ [input.key]: next });
          }}
        />
      )}
      {input.kind === 'source' && (
        <select
          id={id}
          className="tw-ind-select"
          value={String(config[input.key] ?? input.default)}
          onChange={(event) => onConfigure({ [input.key]: event.target.value })}
        >
          {INDICATOR_SOURCES.map((source) => (
            <option key={source.value} value={source.value}>{source.label}</option>
          ))}
        </select>
      )}
      {input.kind === 'enum' && (
        <select
          id={id}
          className="tw-ind-select"
          value={String(config[input.key] ?? input.default)}
          onChange={(event) => onConfigure({ [input.key]: event.target.value })}
        >
          {input.choices.map((choice) => (
            <option key={choice.value} value={choice.value}>{choice.label}</option>
          ))}
        </select>
      )}
      {input.kind === 'boolean' && (
        <input
          id={id}
          type="checkbox"
          checked={Boolean(config[input.key] ?? input.default)}
          onChange={(event) => onConfigure({ [input.key]: event.target.checked })}
        />
      )}
    </div>
  );
}
