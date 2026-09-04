// The workstation's left edge: the operator's watchlist as navigation, not as a card.
//
// Same rail grammar as the ticker workspace — every row is a doorway into an asset
// workspace — plus the management the watchlist store supports: switch/create/delete lists,
// import from Webull, add and remove symbols. Holdings and the sweep's movers that are not
// already watched appear in their own groups, so "what I own" and "what moved" are reachable
// from the same column as "what I track". The rail is quiet by default (see the stylesheet):
// a sparkline appears only on the row under the pointer or the keyboard cursor.
//
// Removal is immediate and reversible — the row goes and an undo line offers it back.

import { useEffect, useRef, useState } from 'react';
import { ChevronDown, Download, PanelLeftClose, PanelLeftOpen, Plus, RefreshCw, X } from 'lucide-react';
import { toneColor } from '../marketUi';
import { TickerSearch } from '../TickerSearch';
import { Sparkline } from '../workspaceViz';
import type { RailEntry } from '../marketBriefModel';
import type { MarketWatchlistState } from '../useMarketMonitorData';
import { SkeletonLines } from '../loading/WorkspaceLoading';

const UNDO_WINDOW_MS = 8000;

function ListMenu({ watchlist, onClose }: { watchlist: MarketWatchlistState; onClose: () => void }) {
  const [naming, setNaming] = useState(false);
  const [draft, setDraft] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
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
    <div ref={menuRef} className="mw-listmenu" role="menu" aria-label="Watchlists">
      {watchlist.lists.map((name) => (
        <div key={name} className="mw-listmenu__row" data-active={name === watchlist.active}>
          <button type="button" onClick={() => { void watchlist.selectList(name); onClose(); }} title={name}>
            {name}
          </button>
          {watchlist.lists.length > 1 && (
            confirmDelete === name ? (
              <button
                type="button"
                className="tw-btn tw-btn--sm"
                style={{ color: 'var(--mkt-down)', borderColor: 'rgba(217,109,95,.4)' }}
                onClick={() => { void watchlist.deleteList(name); setConfirmDelete(null); onClose(); }}
                title={`Delete "${name}" and every symbol on it`}
              >
                Delete?
              </button>
            ) : (
              <button
                type="button"
                className="tw-iconbtn"
                style={{ width: 22, height: 22 }}
                onClick={() => setConfirmDelete(name)}
                title={`Delete watchlist "${name}"`}
                aria-label={`Delete watchlist "${name}"`}
              >
                <X size={11} />
              </button>
            )
          )}
        </div>
      ))}
      <div className="mw-listmenu__sep" />
      {naming ? (
        <input
          autoFocus
          className="mw-listmenu__input"
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
        <button type="button" className="mw-listmenu__action" onClick={() => setNaming(true)}>
          <Plus size={11} /> New watchlist
        </button>
      )}
      <button
        type="button"
        className="mw-listmenu__action"
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
  variant = 'rail',
}: {
  watchlist: MarketWatchlistState;
  entries: RailEntry[];
  cursor: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (symbol: string) => void;
  /** `sheet` renders the same list as a full-width section on screens too narrow for a rail. */
  variant?: 'rail' | 'sheet';
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [removed, setRemoved] = useState<{ symbol: string; name: string } | null>(null);
  const undoTimer = useRef<number | null>(null);
  const sheet = variant === 'sheet';
  const folded = collapsed && !sheet;

  useEffect(() => () => {
    if (undoTimer.current) window.clearTimeout(undoTimer.current);
  }, []);

  const remove = (entry: RailEntry) => {
    void watchlist.remove(entry.symbol);
    setRemoved({ symbol: entry.symbol, name: entry.name });
    if (undoTimer.current) window.clearTimeout(undoTimer.current);
    undoTimer.current = window.setTimeout(() => setRemoved(null), UNDO_WINDOW_MS);
  };

  const undo = () => {
    if (!removed) return;
    void watchlist.add(removed.symbol, removed.name);
    setRemoved(null);
    if (undoTimer.current) window.clearTimeout(undoTimer.current);
  };

  let lastGroup = '';

  return (
    <nav className={`tw-rail mw-rail${sheet ? ' mw-rail--sheet' : ''}`} data-collapsed={folded} aria-label="Watchlist">
      <div className="tw-rail__head" style={{ position: 'relative' }}>
        {!folded && (
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
            {!sheet && <kbd className="mw-kbd">j k</kbd>}
          </>
        )}
        {!sheet && (
          <button
            type="button"
            className="tw-iconbtn"
            onClick={onToggle}
            title={collapsed ? 'Expand watch rail' : 'Collapse watch rail'}
            aria-label={collapsed ? 'Expand watch rail' : 'Collapse watch rail'}
          >
            {collapsed ? <PanelLeftOpen size={13} /> : <PanelLeftClose size={13} />}
          </button>
        )}
        {menuOpen && !folded && <ListMenu watchlist={watchlist} onClose={() => setMenuOpen(false)} />}
      </div>

      <div className="tw-rail__list">
        {watchlist.loading && entries.length === 0 && <div className="workspace-loading workspace-loading__rail" aria-label="Loading watchlist" aria-busy="true"><SkeletonLines rows={9} /></div>}
        {!watchlist.loading && entries.length === 0 && (
          <p className="tw-rail__empty">
            {`"${watchlist.active}" is empty. Add a symbol below — every row opens its workspace.`}
          </p>
        )}
        {entries.map((entry) => {
          const header = !folded && entry.group !== lastGroup ? entry.group : null;
          lastGroup = entry.group;
          const tone = toneColor(entry.tone ?? 'flat');
          return (
            <div key={`${entry.group}-${entry.symbol}`}>
              {header && <div className="tw-rail__group">{header}</div>}
              <button
                type="button"
                className="tw-rail__row"
                data-cursor={cursor === entry.symbol}
                onClick={() => onSelect(entry.symbol)}
                title={entry.name && entry.name !== entry.symbol ? `${entry.symbol} · ${entry.name}` : entry.symbol}
                style={{ ['--tone' as string]: tone }}
              >
                <span className="tw-rail__sym" style={folded ? { color: tone } : undefined}>
                  {folded ? entry.symbol.slice(0, 4) : entry.symbol}
                </span>
                {!folded && entry.spark && entry.spark.length > 1 && (
                  <span className="mw-rail__spark">
                    <Sparkline points={entry.spark} color={tone} height={18} />
                  </span>
                )}
                {!folded && entry.change && <span className="tw-rail__chg">{entry.change}</span>}
                {!folded && entry.watched && (
                  <span
                    role="button"
                    tabIndex={-1}
                    className="mw-rail__remove"
                    onClick={(event) => {
                      event.stopPropagation();
                      remove(entry);
                    }}
                    title={`Remove ${entry.symbol} from "${watchlist.active}" (undo offered)`}
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

      {!folded && removed && (
        <div className="mw-rail__undo" role="status">
          Removed <b>{removed.symbol}</b>
          <button type="button" onClick={undo}>Undo</button>
        </div>
      )}

      {!folded && (
        <div className="mw-rail__add">
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
