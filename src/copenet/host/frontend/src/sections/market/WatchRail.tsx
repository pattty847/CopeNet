// The cockpit's left edge: the operator's watchlist as navigation, not as a card.
//
// Same rail grammar as the ticker workspace — every row is a doorway into an asset
// workspace — plus the management the watchlist store supports: switch/create/delete
// lists, import from Webull, add and remove symbols. Movers from the morning sweep that
// are not already watched appear in their own group, so "what moved" is reachable from
// the same column as "what I track".

import { useEffect, useRef, useState } from 'react';
import { ChevronDown, Download, PanelLeftClose, PanelLeftOpen, Plus, RefreshCw, X } from 'lucide-react';
import { toneColor } from './marketUi';
import { TickerSearch } from './TickerSearch';
import { Sparkline } from './workspaceViz';
import type { MarketWatchlistState } from './useMarketMonitorData';
import type { BriefMover, Tone } from './types';

interface CockpitRailEntry {
  group: string;
  symbol: string;
  name: string;
  change?: string;
  tone?: Tone;
  spark?: number[];
  watched: boolean;
}

/** Watchlist first (its own order), then unwatched movers. The flat symbol order is what
 *  j/k steps through, so it must match what the rail renders. */
export function buildCockpitRail(watchlist: MarketWatchlistState, movers: BriefMover[]): CockpitRailEntry[] {
  const entries: CockpitRailEntry[] = watchlist.items.map((item) => ({
    group: watchlist.active,
    symbol: item.symbol,
    name: item.name,
    change: item.change,
    tone: item.tone,
    spark: item.spark,
    watched: true,
  }));
  for (const mover of movers) {
    if (watchlist.symbols.has(mover.symbol)) continue;
    entries.push({
      group: 'Movers',
      symbol: mover.symbol,
      name: mover.name,
      change: `${mover.changePct > 0 ? '+' : ''}${mover.changePct.toFixed(1)}%`,
      tone: mover.tone,
      watched: false,
    });
  }
  return entries;
}

function ListMenu({ watchlist, onClose }: { watchlist: MarketWatchlistState; onClose: () => void }) {
  const [naming, setNaming] = useState(false);
  const [draft, setDraft] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const away = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) onClose();
    };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, [onClose]);

  const submit = () => {
    const name = draft.trim();
    setNaming(false);
    setDraft('');
    if (name) {
      void watchlist.createList(name);
      onClose();
    }
  };

  return (
    <div ref={menuRef} className="mc-listmenu" role="menu" aria-label="Watchlists">
      {watchlist.lists.map((name) => (
        <div key={name} className="mc-listmenu__row" data-active={name === watchlist.active}>
          <button type="button" onClick={() => { void watchlist.selectList(name); onClose(); }} title={name}>
            {name}
          </button>
          {watchlist.lists.length > 1 && (
            <button
              type="button"
              className="tw-iconbtn tw-iconbtn--xs"
              onClick={() => void watchlist.deleteList(name)}
              title={`Delete watchlist "${name}"`}
              aria-label={`Delete watchlist "${name}"`}
            >
              <X size={11} />
            </button>
          )}
        </div>
      ))}
      <div className="mc-listmenu__sep" />
      {naming ? (
        <input
          autoFocus
          className="mc-listmenu__input"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={submit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') submit();
            if (event.key === 'Escape') { setNaming(false); setDraft(''); }
          }}
          placeholder="List name…"
          aria-label="New watchlist name"
        />
      ) : (
        <button type="button" className="mc-listmenu__action" onClick={() => setNaming(true)}>
          <Plus size={11} /> New watchlist
        </button>
      )}
      <button
        type="button"
        className="mc-listmenu__action"
        disabled={watchlist.importing}
        onClick={() => { void watchlist.importFromWebull(); onClose(); }}
      >
        {watchlist.importing ? <RefreshCw size={11} className="tw-spin" /> : <Download size={11} />} Import from Webull
      </button>
    </div>
  );
}

export function WatchRail({
  watchlist,
  entries,
  cursor,
  collapsed,
  onToggle,
  onSelect,
}: {
  watchlist: MarketWatchlistState;
  entries: CockpitRailEntry[];
  cursor: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (symbol: string) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  let lastGroup = '';

  return (
    <nav className="tw-rail mc-rail" data-collapsed={collapsed} aria-label="Watchlist">
      <div className="tw-rail__head" style={{ position: 'relative' }}>
        {!collapsed && (
          <>
            <button
              type="button"
              className="tw-btn tw-btn--sm"
              style={{ border: 0, padding: '0 4px', letterSpacing: '.1em', textTransform: 'uppercase' }}
              onClick={() => setMenuOpen((open) => !open)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              title="Switch or manage watchlists"
            >
              {watchlist.active} <ChevronDown size={11} />
            </button>
            <span style={{ flex: 1 }} />
            <kbd style={{ border: '1px solid var(--mkt-seam)', borderRadius: 3, padding: '0 3px', color: 'var(--mkt-dimmer)', font: '600 9px "JetBrains Mono", monospace', letterSpacing: 0 }}>j k</kbd>
          </>
        )}
        <button
          type="button"
          className="tw-iconbtn"
          onClick={onToggle}
          title={collapsed ? 'Expand watch rail' : 'Collapse watch rail'}
          aria-label={collapsed ? 'Expand watch rail' : 'Collapse watch rail'}
        >
          {collapsed ? <PanelLeftOpen size={13} /> : <PanelLeftClose size={13} />}
        </button>
        {menuOpen && !collapsed && <ListMenu watchlist={watchlist} onClose={() => setMenuOpen(false)} />}
      </div>

      <div className="tw-rail__list">
        {entries.length === 0 && (
          <p className="tw-rail__empty">
            {watchlist.loading ? 'Loading watchlist…' : `"${watchlist.active}" is empty. Add a symbol below — every row opens its workspace.`}
          </p>
        )}
        {entries.map((entry) => {
          const header = !collapsed && entry.group !== lastGroup ? entry.group : null;
          lastGroup = entry.group;
          return (
            <div key={`${entry.group}-${entry.symbol}`}>
              {header && <div className="tw-rail__group">{header}</div>}
              <button
                type="button"
                className="tw-rail__row"
                data-cursor={cursor === entry.symbol}
                onClick={() => onSelect(entry.symbol)}
                title={entry.name ? `${entry.symbol} · ${entry.name}` : entry.symbol}
              >
                <span className="tw-rail__sym" style={collapsed ? { color: toneColor(entry.tone ?? 'flat') } : undefined}>
                  {collapsed ? entry.symbol.slice(0, 4) : entry.symbol}
                </span>
                {!collapsed && entry.spark && entry.spark.length > 1 && (
                  <span style={{ width: 34, flex: '0 0 auto' }}>
                    <Sparkline points={entry.spark} color={toneColor(entry.tone ?? 'flat')} height={13} />
                  </span>
                )}
                {!collapsed && entry.change && (
                  <span className="tw-rail__chg" style={{ color: toneColor(entry.tone ?? 'flat') }}>{entry.change}</span>
                )}
                {!collapsed && entry.watched && (
                  <span
                    role="button"
                    tabIndex={-1}
                    className="mc-rail__remove"
                    onClick={(event) => {
                      event.stopPropagation();
                      void watchlist.remove(entry.symbol);
                    }}
                    title={`Remove ${entry.symbol} from "${watchlist.active}"`}
                    aria-label={`Remove ${entry.symbol} from watchlist`}
                  >
                    ×
                  </span>
                )}
              </button>
            </div>
          );
        })}
      </div>

      {!collapsed && (
        <div className="mc-rail__add">
          <TickerSearch
            onSelect={(symbol, name) => void watchlist.add(symbol, name)}
            allowFormula={false}
            fullWidth
            placeholder={`＋ Add to "${watchlist.active}"…`}
          />
        </div>
      )}
    </nav>
  );
}
