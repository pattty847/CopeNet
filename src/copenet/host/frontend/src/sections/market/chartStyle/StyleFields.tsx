// The only place style controls are written. Every settings surface composes these.
import { LINE_STYLES, LINE_WIDTHS, STYLE_COLORS, type AnchorField, type ChoiceField, type FillField, type LineStyle, type StrokeField, type ToggleField } from './types';

export function StrokeSample({ width, style, color = 'currentColor' }: { width: number; style: LineStyle; color?: string }) {
  return <svg width="22" height="10" aria-hidden="true"><line x1="1" y1="5" x2="21" y2="5" stroke={color} strokeWidth={width}
    strokeDasharray={style === 'dashed' ? '5 3' : style === 'dotted' ? '1.5 3' : undefined} /></svg>;
}

export function ColorField({ value, label, onChange }: { value: string; label: string; onChange: (color: string) => void }) {
  return <div className="cs-colors" role="radiogroup" aria-label={`${label} color`}>
    {STYLE_COLORS.map((color) => <button key={color} type="button" role="radio" aria-checked={value.toLowerCase() === color} aria-label={color}
      onClick={() => onChange(color)}><i style={{ background: color }} /></button>)}
    <label className="cs-colors__custom" title="Custom color"><input type="color" value={value} onChange={(event) => onChange(event.target.value)} aria-label={`${label} custom color`} /></label>
  </div>;
}

export function StrokeFields({ field }: { field: StrokeField }) {
  const off = field.visible?.value === false;
  return <fieldset className="cs-field" data-off={off}>
    <legend>
      {field.visible
        ? <label><input type="checkbox" checked={field.visible.value} onChange={(event) => field.visible!.onChange(event.target.checked)} /> {field.label}</label>
        : field.label}
    </legend>
    <ColorField value={field.value.color} label={field.label} onChange={(color) => field.onChange({ color })} />
    {!field.colorOnly && <div className="cs-row">
      <div className="cs-seg" role="radiogroup" aria-label={`${field.label} width`}>
        {LINE_WIDTHS.map((width) => <button key={width} type="button" role="radio" aria-checked={field.value.width === width} aria-label={`${width} pixels`}
          onClick={() => field.onChange({ width })}><StrokeSample width={width} style="solid" /></button>)}
      </div>
      <div className="cs-seg" role="radiogroup" aria-label={`${field.label} line style`}>
        {LINE_STYLES.map((style) => <button key={style} type="button" role="radio" aria-checked={field.value.style === style} aria-label={style}
          onClick={() => field.onChange({ style })}><StrokeSample width={2} style={style} /></button>)}
      </div>
    </div>}
  </fieldset>;
}

export function FillFields({ field }: { field: FillField }) {
  return <fieldset className="cs-field">
    <legend>{field.label}</legend>
    {!field.opacityOnly && <ColorField value={field.value.color} label={field.label} onChange={(color) => field.onChange({ color })} />}
    <label className="cs-slider">Opacity
      <input type="range" min={0} max={60} step={1} value={Math.round(field.value.opacity * 100)} onChange={(event) => field.onChange({ opacity: Number(event.target.value) / 100 })} />
      <output>{Math.round(field.value.opacity * 100)}%</output>
    </label>
  </fieldset>;
}

export function ChoiceFields({ field }: { field: ChoiceField }) {
  return <label className="cs-line">{field.label}
    <select value={field.value} onChange={(event) => field.onChange(event.target.value)}>
      {field.choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
    </select>
  </label>;
}

export function ToggleFields({ field }: { field: ToggleField }) {
  return <label className="cs-check"><input type="checkbox" checked={field.value} onChange={(event) => field.onChange(event.target.checked)} /> {field.label}</label>;
}

const isoDate = (time: number) => new Date(time * 1000).toISOString().slice(0, 10);

/** A date snaps to a real slot on this chart: an anchor can never sit between two candles. */
export function AnchorFields({ field, times }: { field: AnchorField; times: number[] }) {
  const snap = (date: string) => {
    const wanted = Date.parse(`${date}T00:00:00Z`) / 1000;
    if (!Number.isFinite(wanted) || !times.length) return;
    field.onChange({ time: times.reduce((best, time) => Math.abs(time - wanted) < Math.abs(best - wanted) ? time : best, times[0]) });
  };
  return <fieldset className="cs-field">
    <legend>{field.label}</legend>
    <div className="cs-row">
      <label className="cs-line">Date<input type="date" value={isoDate(field.time)} onChange={(event) => snap(event.target.value)} /></label>
      <label className="cs-line">Price<input type="number" step="any" min={0} value={field.price}
        onChange={(event) => { const price = Number(event.target.value); if (Number.isFinite(price) && price > 0) field.onChange({ price }); }} /></label>
    </div>
  </fieldset>;
}
