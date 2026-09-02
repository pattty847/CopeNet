// Section layout: the constrained customization model.
//
// A section is a list of panels. The operator can reorder them, hide them, and choose half
// or full width where a panel supports it — nothing more. Free positioning and free height
// were the old grid's failure mode (shared row heights, ragged voids, the operator doing the
// designer's job), so they are not offered. Preferences are per device and per section;
// unknown panel ids drop and new panels append, so a saved layout never strands anyone.
// Mobile renders the default order in one column and ignores the preference entirely.

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowUp, Eye, EyeOff, RotateCcw, SlidersHorizontal } from 'lucide-react';
import type { MarketSection } from '../../../lib/appSectionRouting';
import {
  loadSectionLayout,
  movePanel,
  resolveSectionLayout,
  saveSectionLayout,
  setPanelWidth,
  togglePanelHidden,
  type ResolvedPanel,
  type SectionLayoutPref,
  type SectionPanelSpec,
} from '../marketWorkstationState';

export interface SectionPanel extends SectionPanelSpec {
  node: ReactNode;
}

export interface SectionLayout {
  panels: ResolvedPanel<SectionPanel>[];
  customized: boolean;
  move: (id: string, delta: -1 | 1) => void;
  toggleHidden: (id: string) => void;
  setWidth: (id: string, width: 'half' | 'full') => void;
  reset: () => void;
}

export function useSectionLayout(section: MarketSection, panels: SectionPanel[]): SectionLayout {
  const [pref, setPref] = useState<SectionLayoutPref>(() => loadSectionLayout(section));

  useEffect(() => {
    setPref(loadSectionLayout(section));
  }, [section]);

  const persist = useCallback(
    (next: SectionLayoutPref) => {
      setPref(next);
      saveSectionLayout(section, next);
    },
    [section],
  );

  const ids = useMemo(() => panels.map((panel) => panel.id), [panels]);
  const resolved = useMemo(() => resolveSectionLayout(panels, pref), [panels, pref]);

  return {
    panels: resolved,
    customized: pref.order.length > 0 || pref.hidden.length > 0 || Object.keys(pref.width).length > 0,
    move: (id, delta) => persist(movePanel(pref, ids, id, delta)),
    toggleHidden: (id) => persist(togglePanelHidden(pref, id)),
    setWidth: (id, width) => persist(setPanelWidth(pref, id, width)),
    reset: () => {
      setPref({ order: [], hidden: [], width: {} });
      saveSectionLayout(section, null);
    },
  };
}

export function SectionGrid({ layout, isMobile }: { layout: SectionLayout; isMobile: boolean }) {
  const visible = layout.panels.filter((panel) => !panel.hidden);
  if (visible.length === 0) {
    return <div className="mw-empty">Every panel in this section is hidden. Use Arrange to bring one back.</div>;
  }
  return (
    <div className="mw-grid">
      {visible.map((panel) => (
        <div key={panel.spec.id} data-width={isMobile ? 'full' : panel.width}>
          {panel.spec.node}
        </div>
      ))}
    </div>
  );
}

/** The Arrange affordance: a popover listing the section's panels with order, visibility and
 *  width controls. Rendered only where there is more than one panel to arrange. */
export function ArrangeMenu({ layout }: { layout: SectionLayout }) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (anchorRef.current && !anchorRef.current.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);

  if (layout.panels.length < 2) return null;
  const last = layout.panels.length - 1;

  return (
    <div ref={anchorRef} className="mw-arrange__anchor">
      <button
        type="button"
        className="tw-btn tw-btn--sm"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="dialog"
        aria-expanded={open}
        data-active={layout.customized || undefined}
        title="Reorder, hide, or resize this section's panels"
      >
        <SlidersHorizontal size={11} /> Arrange
      </button>
      {open && (
        <div className="mw-arrange" role="dialog" aria-label="Arrange panels">
          {layout.panels.map((panel, index) => (
            <div key={panel.spec.id} className="mw-arrange__row" data-hidden={panel.hidden}>
              <span className="mw-arrange__title">{panel.spec.title}</span>
              <button type="button" className="tw-iconbtn" style={{ width: 22, height: 22 }} disabled={index === 0} onClick={() => layout.move(panel.spec.id, -1)} title="Move up" aria-label={`Move ${panel.spec.title} up`}>
                <ArrowUp size={11} />
              </button>
              <button type="button" className="tw-iconbtn" style={{ width: 22, height: 22 }} disabled={index === last} onClick={() => layout.move(panel.spec.id, 1)} title="Move down" aria-label={`Move ${panel.spec.title} down`}>
                <ArrowDown size={11} />
              </button>
              <button
                type="button"
                className="tw-btn tw-btn--sm"
                style={{ minWidth: 34 }}
                disabled={!panel.spec.canHalf}
                aria-pressed={panel.width === 'half'}
                onClick={() => layout.setWidth(panel.spec.id, panel.width === 'half' ? 'full' : 'half')}
                title={panel.spec.canHalf ? (panel.width === 'half' ? 'Half width — click for full' : 'Full width — click for half') : 'This panel only reads at full width'}
              >
                {panel.width === 'half' ? '½' : 'full'}
              </button>
              <button type="button" className="tw-iconbtn" style={{ width: 22, height: 22 }} onClick={() => layout.toggleHidden(panel.spec.id)} title={panel.hidden ? 'Show panel' : 'Hide panel'} aria-label={`${panel.hidden ? 'Show' : 'Hide'} ${panel.spec.title}`}>
                {panel.hidden ? <EyeOff size={11} /> : <Eye size={11} />}
              </button>
            </div>
          ))}
          <div className="mw-arrange__foot">
            <span>Saved on this device</span>
            <button type="button" className="tw-btn tw-btn--sm" onClick={layout.reset} disabled={!layout.customized}>
              <RotateCcw size={10} /> Reset
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Section header: label · meta · tools. Every section starts with one so the eye lands in
 *  the same place whichever tab is open. */
export function SectionHeader({ label, meta, children }: { label: string; meta?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mw-sect">
      <span className="mw-sect__label">{label}</span>
      {meta && <span className="mw-sect__meta">{meta}</span>}
      <span className="mw-sect__spacer" />
      {children}
    </div>
  );
}
