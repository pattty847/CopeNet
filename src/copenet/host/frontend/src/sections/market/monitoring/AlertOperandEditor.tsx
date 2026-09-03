import { INDICATOR_SOURCES } from '../indicators/types';
import type { AlertOperand, IndicatorOption } from './types';

export function AlertOperandEditor({
  label,
  operand,
  catalogue,
  onChange,
}: {
  label: string;
  operand: AlertOperand;
  catalogue: IndicatorOption[];
  onChange: (operand: AlertOperand) => void;
}) {
  const indicator = catalogue.find((item) => item.id === operand.indicatorId);
  const choose = (value: string) => {
    if (value === 'price') onChange({ kind: 'price' });
    else if (value === 'constant') onChange({ kind: 'constant', value: 0 });
    else {
      const definition = catalogue.find((item) => item.id === value)!;
      onChange({ kind: 'indicator', indicatorId: value, config: definition.defaults, output: definition.outputs[0].key });
    }
  };
  return (
    <fieldset>
      <legend>{label}</legend>
      <label>
        Value
        <select
          className="tw-input"
          value={operand.kind === 'indicator' ? operand.indicatorId : operand.kind}
          onChange={(event) => choose(event.target.value)}
        >
          <option value="price">Price · close</option>
          <option value="constant">Number</option>
          {catalogue.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {operand.kind === 'constant' && (
        <label>
          Threshold
          <input
            className="tw-input"
            required
            type="number"
            step="any"
            value={operand.value ?? ''}
            onChange={(event) => onChange({ ...operand, value: event.target.valueAsNumber })}
          />
        </label>
      )}
      {operand.kind === 'indicator' && indicator && (
        <>
          <label>
            Output
            <select className="tw-input" value={operand.output} onChange={(event) => onChange({ ...operand, output: event.target.value })}>
              {indicator.outputs.map((output) => (
                <option key={output.key} value={output.key}>
                  {output.label}
                </option>
              ))}
            </select>
          </label>
          <div className="mm-monitor-fields">
            {indicator.inputs.map((input) => {
              const value = operand.config?.[input.key] ?? input.default;
              const set = (next: number | string | boolean) => onChange({ ...operand, config: { ...operand.config, [input.key]: next } });
              return (
                <label key={input.key}>
                  {input.label}
                  {input.kind === 'number' ? (
                    <input
                      className="tw-input"
                      required
                      type="number"
                      min={input.min}
                      max={input.max}
                      step={input.step}
                      value={Number(value)}
                      onChange={(event) => set(event.target.valueAsNumber)}
                    />
                  ) : input.kind === 'boolean' ? (
                    <input type="checkbox" checked={Boolean(value)} onChange={(event) => set(event.target.checked)} />
                  ) : (
                    <select className="tw-input" value={String(value)} onChange={(event) => set(event.target.value)}>
                      {(input.kind === 'source' ? INDICATOR_SOURCES : input.choices).map((choice) => (
                        <option key={choice.value} value={choice.value}>
                          {choice.label}
                        </option>
                      ))}
                    </select>
                  )}
                </label>
              );
            })}
          </div>
        </>
      )}
    </fieldset>
  );
}
