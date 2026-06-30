import React from 'react';
import { Activity, Bot, CandlestickChart, FlaskConical, Home, Layers3, MoreHorizontal, Search, Wrench } from 'lucide-react';
import { getMobileSectionSummary } from '../../lib/mobileCopy';
import { useAppStore, type AppSection } from '../../store/useAppStore';
import { MobileSheet } from './MobileSheet';

const PRIMARY_ITEMS: Array<{ id: AppSection; label: string; icon: typeof Home }> = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'agents', label: 'Agents', icon: Bot },
  { id: 'market', label: 'Market', icon: CandlestickChart },
  { id: 'workflows', label: 'Workflows', icon: Layers3 },
];

const MORE_ITEMS: Array<{ id: AppSection; label: string; icon: typeof Activity }> = [
  { id: 'data-tools', label: 'Media', icon: Wrench },
  { id: 'observability', label: 'Observability', icon: Activity },
  { id: 'experiments', label: 'Experiments', icon: FlaskConical },
];

const SECTION_TITLES: Record<AppSection, string> = {
  home: 'Home',
  agents: 'Agents',
  market: 'Market',
  workflows: 'Workflows',
  'data-tools': 'Data & Tools',
  observability: 'Observability',
  experiments: 'Experiments',
};

export function MobileTopBar() {
  const currentSection = useAppStore((state) => state.currentSection);
  const wsStatus = useAppStore((state) => state.wsStatus);
  const setCommandPaletteOpen = useAppStore((state) => state.setCommandPaletteOpen);
  const setMobileOverflowOpen = useAppStore((state) => state.setMobileOverflowOpen);

  return (
    <div className="border-b border-shell-border/80 bg-shell-panel/95 px-4 pb-3 pt-[calc(env(safe-area-inset-top)+0.7rem)] backdrop-blur lg:hidden">
      <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-muted">CopeNet</div>
        <div className="flex items-center gap-2">
          <h1 className="truncate text-[17px] font-semibold text-shell-text">{SECTION_TITLES[currentSection]}</h1>
          <span className="inline-flex items-center gap-1 rounded-full bg-shell-panel-strong px-2 py-0.5 text-[10px] font-medium text-shell-muted">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                wsStatus === 'connected'
                  ? 'bg-shell-success'
                  : wsStatus === 'connecting'
                  ? 'bg-shell-accent'
                  : 'bg-shell-error'
              }`}
            />
            {wsStatus === 'connected' ? 'live' : wsStatus === 'connecting' ? 'linking' : 'retrying'}
          </span>
        </div>
        <div className="mt-1 text-[12px] leading-5 text-shell-muted">
          {getMobileSectionSummary(currentSection)}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setCommandPaletteOpen(true)}
          className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-shell-border bg-shell-panel px-3 text-[12px] font-medium text-shell-muted shadow-shell"
        >
          <span className="text-shell-text">Search</span>
          <span className="rounded-md border border-shell-border bg-shell-panel-strong px-1.5 py-0.5 text-[10px] text-shell-muted">⌘K</span>
        </button>
        <button
          type="button"
          onClick={() => setMobileOverflowOpen(true)}
          className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-shell-border bg-shell-panel text-shell-text shadow-shell"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
      </div>
    </div>
  );
}

export function MobileBottomNav() {
  const currentSection = useAppStore((state) => state.currentSection);
  const setCurrentSection = useAppStore((state) => state.setCurrentSection);
  const mobileOverflowOpen = useAppStore((state) => state.mobileOverflowOpen);
  const setMobileOverflowOpen = useAppStore((state) => state.setMobileOverflowOpen);
  const setCommandPaletteOpen = useAppStore((state) => state.setCommandPaletteOpen);

  return (
    <>
      <nav className="fixed inset-x-0 bottom-0 z-50 border-t border-shell-border bg-shell-panel/95 px-2 pb-[calc(env(safe-area-inset-bottom)+0.65rem)] pt-2 shadow-shell-xl backdrop-blur lg:hidden">
        <div className="grid grid-cols-5 gap-1">
          {PRIMARY_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = currentSection === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setCurrentSection(item.id)}
                aria-label={item.label}
                title={item.label}
                className={`flex min-h-[56px] flex-col items-center justify-center gap-1 rounded-2xl px-2 py-2 ${
                  active ? 'bg-shell-accent-soft text-shell-accent' : 'text-shell-muted'
                }`}
              >
                <Icon className="h-4 w-4" />
                <span className="text-[10px] font-semibold leading-none">{item.label}</span>
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => setMobileOverflowOpen(true)}
            aria-label="More"
            title="More"
            className={`flex min-h-[56px] flex-col items-center justify-center gap-1 rounded-2xl px-2 py-2 ${
              currentSection === 'observability' || currentSection === 'experiments' ? 'bg-shell-accent-soft text-shell-accent' : 'text-shell-muted'
            }`}
          >
            <MoreHorizontal className="h-4 w-4" />
            <span className="text-[10px] font-semibold leading-none">More</span>
          </button>
        </div>
      </nav>

      <MobileSheet open={mobileOverflowOpen} onClose={() => setMobileOverflowOpen(false)} title="More">
        <div className="space-y-2 px-3 py-3">
          <button
            type="button"
            onClick={() => {
              setCommandPaletteOpen(true);
              setMobileOverflowOpen(false);
            }}
            className="flex w-full items-center gap-3 rounded-2xl border border-shell-border bg-shell-panel px-4 py-3 text-left text-shell-text"
          >
            <Search className="h-4 w-4 text-shell-accent" />
            <div>
              <div className="text-[14px] font-medium">Search</div>
              <div className="text-[12px] text-shell-muted">Open the command palette from anywhere.</div>
            </div>
          </button>
          {MORE_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = currentSection === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setCurrentSection(item.id);
                  setMobileOverflowOpen(false);
                }}
                className={`flex w-full items-center gap-3 rounded-2xl border px-4 py-3 text-left ${
                  active ? 'border-shell-accent/40 bg-shell-accent-soft text-shell-text' : 'border-shell-border bg-shell-bg text-shell-text'
                }`}
              >
                <Icon className="h-4 w-4 text-shell-accent" />
                <div>
                  <div className="text-[14px] font-medium">{item.label}</div>
                  <div className="text-[12px] text-shell-muted">{getMobileSectionSummary(item.id)}</div>
                </div>
              </button>
            );
          })}
        </div>
      </MobileSheet>
    </>
  );
}
