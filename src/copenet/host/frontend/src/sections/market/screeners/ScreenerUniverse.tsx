import type { ScreenerConfig } from './types';
export function ScreenerUniverse({
  config,
  onChange,
  disabled,
}: {
  config: ScreenerConfig;
  onChange: (config: ScreenerConfig) => void;
  disabled: boolean;
}) {
  const fields = [
    { key: 'minCap', label: 'Min market cap ($B)', scale: 1e9, min: 1 },
    { key: 'maxCap', label: 'Max market cap ($B)', scale: 1e9, min: 1 },
    { key: 'minPrice', label: 'Min share price ($)', scale: 1, min: 5 },
    {
      key: 'minDollarVolume',
      label: 'Min daily liquidity ($M)',
      scale: 1e6,
      min: 5,
    },
  ] as const;
  return (
    <fieldset className="scr-universe" disabled={disabled}>
      <legend>Universe · US-listed common shares · NASDAQ / NYSE / AMEX</legend>
      {fields.map(({ key, label, scale, min }) => (
        <label key={key}>
          {label}
          <input
            type="number"
            min={min}
            step="any"
            required={key !== 'maxCap'}
            value={config[key] == null ? '' : config[key]! / scale}
            placeholder={key === 'maxCap' ? 'No ceiling' : undefined}
            onChange={(event) =>
              onChange({
                ...config,
                [key]: event.target.value === '' && key === 'maxCap' ? null : Number(event.target.value) * scale,
              })
            }
          />
        </label>
      ))}
      <small>
        Liquidity ≈ current price × 30-day average volume. Size and activity filters do not establish business quality.
      </small>
    </fieldset>
  );
}
