// The quick path: the bar over the chart for whatever is selected. It applies instantly and
// carries only the controls reached for constantly; the gear opens the full popup.
import { useEffect, useRef, useState } from 'react';
import { EyeOff, GripVertical, Lock, Settings2, Trash2, Type, Undo2, Unlock, X } from 'lucide-react';
import { ColorField, StrokeSample } from './StyleFields';
import { LINE_STYLES, LINE_WIDTHS, type FillField, type StrokeField } from './types';
import { useBarPosition } from './useBarPosition';

export interface SelectionBarModel {
  id: string;
  title: string;
  stroke?: StrokeField;
  fill?: FillField;
  text?: { value: string; onChange: (next: string) => void; openOnSelect?: boolean };
  lock?: { value: boolean; toggle: () => void };
  hide?: () => void;
  remove?: () => void;
  busy?: boolean;
  openSettings: () => void;
  deselect: () => void;
}
type Menu = 'color' | 'stroke' | 'fill' | 'text' | null;
const FILL_STEPS = [0, 0.1, 0.22, 0.35];

function LabelEditor({ value, onCommit }: { value: string; onCommit: (label: string) => void }) {
  const [draft, setDraft] = useState(value);
  return <form className="tw-drawbar__text" onSubmit={(event) => { event.preventDefault(); onCommit(draft.trim()); }}>
    <input autoFocus onFocus={(event) => event.target.select()} value={draft} maxLength={200} aria-label="Label" onChange={(event) => setDraft(event.target.value)} />
    <button type="submit">Save</button>
  </form>;
}

export function DeletedBar({ label, onUndo }: { label: string; onUndo: () => void }) {
  const barRef = useRef<HTMLDivElement | null>(null);
  const position = useBarPosition(barRef);
  return <div className="tw-drawbar" role="status" ref={barRef} style={position.style}>
    <span className="tw-drawbar__name">Deleted {label}</span>
    <button type="button" className="tw-drawbar__wide" onClick={onUndo}><Undo2 size={13} /> Undo</button>
  </div>;
}

export function SelectionBar({ model }: { model: SelectionBarModel }) {
  const [menu, setMenu] = useState<Menu>(null);
  const barRef = useRef<HTMLDivElement | null>(null);
  const position = useBarPosition(barRef);
  // A note is its text, so placing one leads straight into typing it.
  useEffect(() => { setMenu(model.text?.openOnSelect ? 'text' : null); }, [model.id, model.text?.openOnSelect]);
  useEffect(() => {
    if (!menu) return;
    const close = (event: PointerEvent) => { if (!barRef.current?.contains(event.target as Node)) setMenu(null); };
    document.addEventListener('pointerdown', close, true);
    return () => document.removeEventListener('pointerdown', close, true);
  }, [menu]);
  const toggle = (next: Menu) => setMenu((current) => current === next ? null : next);
  const { stroke, fill, busy } = model;
  const color = stroke?.value.color ?? fill?.value.color;
  const setColor = (next: string) => { if (stroke) stroke.onChange({ color: next }); else fill?.onChange({ color: next }); };

  return <div className="tw-drawbar" role="toolbar" aria-label={`Settings for ${model.title}`} ref={barRef} style={position.style}>
    <span className="tw-drawbar__grip" role="button" tabIndex={-1} aria-label="Drag to move this bar; double-click to put it back" title="Drag to move · double-click to reset"
      onPointerDown={position.onGripPointerDown} onDoubleClick={position.reset}><GripVertical size={14} /></span>
    <span className="tw-drawbar__name">{model.title}</span>
    {color && <button type="button" aria-label="Color" aria-expanded={menu === 'color'} onClick={() => toggle('color')}><i className="tw-drawbar__swatch" style={{ background: color }} /></button>}
    {stroke && !stroke.colorOnly && <button type="button" aria-label="Line width and style" aria-expanded={menu === 'stroke'} onClick={() => toggle('stroke')}>
      <StrokeSample width={stroke.value.width} style={stroke.value.style} /></button>}
    {fill && <button type="button" aria-label="Fill opacity" aria-expanded={menu === 'fill'} onClick={() => toggle('fill')}>
      <i className="tw-drawbar__fill" style={{ background: fill.value.color, opacity: Math.max(0.12, fill.value.opacity * 2) }} /></button>}
    {model.text && <button type="button" aria-label="Label text" aria-expanded={menu === 'text'} onClick={() => toggle('text')}><Type size={14} /></button>}
    <i className="tw-drawbar__sep" />
    {model.lock && <button type="button" aria-label={model.lock.value ? 'Unlock anchors' : 'Lock anchors'} aria-pressed={model.lock.value} disabled={busy} onClick={model.lock.toggle}>
      {model.lock.value ? <Lock size={14} /> : <Unlock size={14} />}</button>}
    {model.hide && <button type="button" aria-label={`Hide ${model.title}`} disabled={busy} onClick={model.hide}><EyeOff size={14} /></button>}
    {model.remove && <button type="button" aria-label={`Delete ${model.title}`} disabled={busy} onClick={model.remove}><Trash2 size={14} /></button>}
    <button type="button" aria-label="All settings" onClick={model.openSettings}><Settings2 size={14} /></button>
    <button type="button" aria-label="Deselect" onClick={model.deselect}><X size={14} /></button>

    {menu === 'color' && color && <div className="tw-drawbar__menu" role="menu" aria-label="Color">
      <ColorField value={color} label={model.title} onChange={(next) => { setColor(next); setMenu(null); }} /></div>}
    {menu === 'stroke' && stroke && <div className="tw-drawbar__menu tw-drawbar__menu--rows" role="menu" aria-label="Line width and style">
      <div>{LINE_WIDTHS.map((width) => <button key={width} type="button" role="menuitemradio" aria-checked={stroke.value.width === width} aria-label={`${width} pixels`}
        disabled={busy} onClick={() => stroke.onChange({ width })}><StrokeSample width={width} style="solid" /></button>)}</div>
      <div>{LINE_STYLES.map((style) => <button key={style} type="button" role="menuitemradio" aria-checked={stroke.value.style === style} aria-label={style}
        disabled={busy} onClick={() => stroke.onChange({ style })}><StrokeSample width={2} style={style} /></button>)}</div>
    </div>}
    {menu === 'fill' && fill && <div className="tw-drawbar__menu" role="menu" aria-label="Fill opacity">
      {FILL_STEPS.map((opacity) => <button key={opacity} type="button" role="menuitemradio" aria-checked={fill.value.opacity === opacity}
        disabled={busy} onClick={() => { fill.onChange({ opacity }); setMenu(null); }}>{Math.round(opacity * 100)}%</button>)}
    </div>}
    {menu === 'text' && model.text && <div className="tw-drawbar__menu"><LabelEditor key={model.id} value={model.text.value} onCommit={(label) => { model.text!.onChange(label); setMenu(null); }} /></div>}
  </div>;
}
