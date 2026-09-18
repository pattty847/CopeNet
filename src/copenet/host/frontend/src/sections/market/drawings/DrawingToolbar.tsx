import { useEffect, useRef, useState } from 'react';
import { EyeOff, Lock, MoreHorizontal, Trash2, Type, Undo2, Unlock, X } from 'lucide-react';
import type { ChartObject, DrawingPatch } from '../chartAgent/types';
import type { ChartWorkspaceBridge } from './types';
import { DRAWING_COLORS, DRAWING_KINDS, FILL_OPACITIES, LINE_STYLES, LINE_WIDTHS, fillOpacityOf, strokeOf, type LineStyle } from './kinds';

type Menu = 'color' | 'stroke' | 'fill' | 'text' | null;

function StrokeSample({ width, style }: { width: number; style: LineStyle }) {
  return <svg width="22" height="10" aria-hidden="true"><line x1="1" y1="5" x2="21" y2="5" stroke="currentColor" strokeWidth={width}
    strokeDasharray={style === 'dashed' ? '5 3' : style === 'dotted' ? '1.5 3' : undefined} /></svg>;
}

function LabelEditor({ object, onCommit }: { object: ChartObject; onCommit: (label: string) => void }) {
  const [value, setValue] = useState(object.label);
  return <form className="tw-drawbar__text" onSubmit={(event) => { event.preventDefault(); onCommit(value.trim()); }}>
    <input autoFocus onFocus={(event) => event.target.select()} value={value} maxLength={200} aria-label="Drawing label" onChange={(event) => setValue(event.target.value)} />
    <button type="submit">Save</button>
  </form>;
}

/** The on-chart settings bar for the selected drawing. Which compartments appear comes
 *  from the kind registry; every control is one canonical `update` patch. */
export function DrawingToolbar({ workspace }: { workspace: ChartWorkspaceBridge }) {
  const selected = workspace.objects.find((object) => object.id === workspace.selectedObjectId) ?? null;
  const [menu, setMenu] = useState<Menu>(null);
  const barRef = useRef<HTMLDivElement | null>(null);
  // A note is its text, so placing one leads straight into typing it.
  useEffect(() => { setMenu(selected && selected.id === workspace.labelRequestId ? 'text' : null); }, [selected?.id, workspace.labelRequestId]);
  useEffect(() => {
    if (!menu) return;
    const close = (event: PointerEvent) => { if (!barRef.current?.contains(event.target as Node)) setMenu(null); };
    document.addEventListener('pointerdown', close, true);
    return () => document.removeEventListener('pointerdown', close, true);
  }, [menu]);

  if (!selected) {
    if (!workspace.deleted) return null;
    return <div className="tw-drawbar" role="status">
      <span className="tw-drawbar__name">Deleted {workspace.deleted.label}</span>
      <button type="button" className="tw-drawbar__wide" onClick={() => workspace.onUndoDelete?.()}><Undo2 size={13} /> Undo</button>
    </div>;
  }

  const spec = DRAWING_KINDS[selected.kind];
  const stroke = strokeOf(selected);
  const busy = workspace.interactionEnabled === false;
  const patch = (next: DrawingPatch) => workspace.onUpdate({ id: selected.id, patch: next });
  const toggle = (next: Menu) => setMenu((current) => current === next ? null : next);
  const name = selected.label || spec.label;

  return <div className="tw-drawbar" role="toolbar" aria-label={`Settings for ${name}`} ref={barRef}>
    <span className="tw-drawbar__name">{name}</span>
    <button type="button" aria-label="Colour" aria-expanded={menu === 'color'} onClick={() => toggle('color')}>
      <i className="tw-drawbar__swatch" style={{ background: selected.color }} />
    </button>
    {spec.stroke && <button type="button" aria-label="Line width and style" aria-expanded={menu === 'stroke'} onClick={() => toggle('stroke')}>
      <StrokeSample width={stroke.width} style={stroke.style} />
    </button>}
    {spec.fill && <button type="button" aria-label="Fill opacity" aria-expanded={menu === 'fill'} onClick={() => toggle('fill')}>
      <i className="tw-drawbar__fill" style={{ background: selected.color, opacity: Math.max(0.12, fillOpacityOf(selected) * 2) }} />
    </button>}
    <button type="button" aria-label="Label text" aria-expanded={menu === 'text'} onClick={() => toggle('text')}><Type size={14} /></button>
    <i className="tw-drawbar__sep" />
    <button type="button" aria-label={selected.locked ? 'Unlock anchors' : 'Lock anchors'} aria-pressed={selected.locked === true} disabled={busy}
      onClick={() => patch({ locked: !selected.locked })}>{selected.locked ? <Lock size={14} /> : <Unlock size={14} />}</button>
    <button type="button" aria-label={`Hide ${name}`} disabled={busy} onClick={() => { patch({ visible: false }); workspace.onSelectObject(null); }}><EyeOff size={14} /></button>
    <button type="button" aria-label={`Delete ${name}`} disabled={busy} onClick={() => workspace.onDeleteObject(selected.id)}><Trash2 size={14} /></button>
    {workspace.onOpenDrawingSettings && <button type="button" aria-label="All drawing settings" onClick={() => workspace.onOpenDrawingSettings?.(selected.id)}><MoreHorizontal size={14} /></button>}
    <button type="button" aria-label="Deselect drawing" onClick={() => workspace.onSelectObject(null)}><X size={14} /></button>

    {menu === 'color' && <div className="tw-drawbar__menu" role="menu" aria-label="Colour">
      {DRAWING_COLORS.map((color) => <button key={color} type="button" role="menuitemradio" aria-checked={selected.color.toLowerCase() === color} aria-label={color}
        disabled={busy} onClick={() => { patch({ color }); setMenu(null); }}><i className="tw-drawbar__swatch" style={{ background: color }} /></button>)}
    </div>}
    {menu === 'stroke' && <div className="tw-drawbar__menu tw-drawbar__menu--rows" role="menu" aria-label="Line width and style">
      <div>{LINE_WIDTHS.map((width) => <button key={width} type="button" role="menuitemradio" aria-checked={stroke.width === width} aria-label={`${width} pixels`}
        disabled={busy} onClick={() => patch({ lineWidth: width })}><StrokeSample width={width} style="solid" /></button>)}</div>
      <div>{LINE_STYLES.map((style) => <button key={style} type="button" role="menuitemradio" aria-checked={stroke.style === style} aria-label={style}
        disabled={busy} onClick={() => patch({ lineStyle: style })}><StrokeSample width={2} style={style} /></button>)}</div>
    </div>}
    {menu === 'fill' && <div className="tw-drawbar__menu" role="menu" aria-label="Fill opacity">
      {FILL_OPACITIES.map((opacity) => <button key={opacity} type="button" role="menuitemradio" aria-checked={fillOpacityOf(selected) === opacity}
        disabled={busy} onClick={() => { patch({ fillOpacity: opacity }); setMenu(null); }}>{Math.round(opacity * 100)}%</button>)}
    </div>}
    {menu === 'text' && <div className="tw-drawbar__menu"><LabelEditor key={selected.id} object={selected} onCommit={(label) => { patch({ label }); setMenu(null); }} /></div>}
  </div>;
}
