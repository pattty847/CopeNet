// One settings popup for anything painted on the chart. It renders the compartments a
// `Styleable` declares as tabs and knows nothing about what the thing is. It floats beside
// the chart rather than covering it, because every control previews live on the chart.
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { AnchorFields, ChoiceFields, FillFields, StrokeFields, ToggleFields } from './StyleFields';
import type { Styleable } from './types';
import './chartStyle.css';

type Tab = 'inputs' | 'style' | 'text' | 'coordinates' | 'visibility';
const TAB_LABELS: Record<Tab, string> = { inputs: 'Inputs', style: 'Style', text: 'Text', coordinates: 'Coordinates', visibility: 'Visibility' };

function tabsOf(target: Styleable): Tab[] {
  const tabs: Tab[] = [];
  if (target.own) tabs.push('inputs');
  if (target.strokes.length || target.fills.length || target.choices?.length || target.toggles?.length) tabs.push('style');
  if (target.text) tabs.push('text');
  if (target.anchors?.fields.length) tabs.push('coordinates');
  if (target.visibility?.length) tabs.push('visibility');
  return tabs;
}

export function ChartObjectSettings({ target, onClose }: { target: Styleable; onClose: () => void }) {
  const tabs = tabsOf(target);
  const [tab, setTab] = useState<Tab>(tabs.includes('style') && (!target.own || target.ownLabel) ? 'style' : tabs[0]);
  const active = tabs.includes(tab) ? tab : tabs[0];
  const cancel = () => { target.cancel(); onClose(); };
  const ok = () => { target.commit(); onClose(); };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      event.preventDefault();
      target.cancel();
      onClose();
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [target, onClose]);

  return createPortal(<section className="cs-popup" role="dialog" aria-label={`${target.title} settings`}>
    <header>
      <h2>{target.title}</h2>
      <button type="button" className="cs-icon" onClick={cancel} aria-label="Close without saving"><X size={15} /></button>
    </header>
    {tabs.length > 1 && <div className="cs-tabs" role="tablist">
      {tabs.map((name) => <button key={name} type="button" role="tab" aria-selected={active === name} onClick={() => setTab(name)}>{name === 'inputs' && target.ownLabel ? target.ownLabel : TAB_LABELS[name]}</button>)}
    </div>}
    <div className="cs-body" role="tabpanel">
      {active === 'inputs' && target.own}
      {active === 'style' && <>
        {target.strokes.map((field) => <StrokeFields key={field.key} field={field} />)}
        {target.fills.map((field) => <FillFields key={field.key} field={field} />)}
        {target.choices?.map((field) => <ChoiceFields key={field.key} field={field} />)}
        {target.toggles?.map((field) => <ToggleFields key={field.key} field={field} />)}
      </>}
      {active === 'text' && target.text && <label className="cs-line cs-line--stack">Label
        <textarea rows={3} maxLength={200} value={target.text.value} onChange={(event) => target.text!.onChange(event.target.value)} /></label>}
      {active === 'coordinates' && target.anchors?.fields.map((field) => <AnchorFields key={field.key} field={field} times={target.anchors!.times} />)}
      {active === 'visibility' && <>
        <p className="cs-note">Show this on</p>
        {target.visibility?.map((field) => <ToggleFields key={field.key} field={field} />)}
      </>}
    </div>
    <footer>
      {(target.actions.saveAsDefault || target.actions.resetToDefault) && <select className="cs-defaults" value="" aria-label="Defaults"
        onChange={(event) => { if (event.target.value === 'save') target.actions.saveAsDefault?.(); if (event.target.value === 'reset') target.actions.resetToDefault?.(); }}>
        <option value="" disabled>Defaults</option>
        {target.actions.resetToDefault && <option value="reset">Reset to default</option>}
        {target.actions.saveAsDefault && <option value="save">Save as default</option>}
      </select>}
      <span />
      <button type="button" className="cs-btn" onClick={cancel}>Cancel</button>
      <button type="button" className="cs-btn cs-btn--primary" onClick={ok}>Ok</button>
    </footer>
  </section>, document.body);
}
