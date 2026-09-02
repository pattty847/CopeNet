import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import type { RailEntry } from './symbolRailModel';
import { toneColor } from './marketUi';
import { Sparkline } from './workspaceViz';

export function SymbolRail({
  entries,
  current,
  cursor,
  collapsed,
  onToggle,
  onSelect,
}: {
  entries: RailEntry[];
  current: string;
  cursor: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (symbol: string) => void;
}) {
  let lastGroup = '';
  return (
    <nav className="tw-rail" data-collapsed={collapsed} aria-label="Symbols">
      <div className="tw-rail__head">
        {!collapsed && (
          <span style={{ flex: 1, display: 'inline-flex', alignItems: 'baseline', gap: 6 }}>
            Symbols
            {/* The shortcut is only worth having if it is visible where the task lives. */}
            <kbd style={{ border: '1px solid var(--mkt-seam)', borderRadius: 3, padding: '0 3px', color: 'var(--mkt-dimmer)', font: '600 9px var(--mkt-mono)', letterSpacing: 0 }}>/</kbd>
          </span>
        )}
        <button
          type="button"
          className="tw-iconbtn"
          onClick={onToggle}
          title={collapsed ? 'Expand symbol rail' : 'Collapse symbol rail'}
          aria-label={collapsed ? 'Expand symbol rail' : 'Collapse symbol rail'}
        >
          {collapsed ? <PanelLeftOpen size={13} /> : <PanelLeftClose size={13} />}
        </button>
      </div>
      {!collapsed && (
        <div className="tw-rail__list">
          {entries.length === 0 && (
            <p className="tw-rail__empty">No watchlist yet. Symbols you open appear here for the session.</p>
          )}
          {entries.map((entry) => {
            const header = entry.group !== lastGroup ? entry.group : null;
            lastGroup = entry.group;
            const isCurrent = entry.symbol === current;
            return (
              <div key={`${entry.group}-${entry.symbol}`}>
                {header && <div className="tw-rail__group">{header}</div>}
                <button
                  type="button"
                  className="tw-rail__row"
                  data-current={isCurrent}
                  data-cursor={cursor === entry.symbol && !isCurrent}
                  onClick={() => onSelect(entry.symbol)}
                  title={entry.name ? `${entry.symbol} · ${entry.name}` : entry.symbol}
                >
                  <span className="tw-rail__sym">{entry.symbol}</span>
                  {entry.spark && entry.spark.length > 1 && (
                    <span style={{ width: 34, flex: '0 0 auto' }}>
                      <Sparkline points={entry.spark} color={toneColor(entry.tone ?? 'flat')} height={13} />
                    </span>
                  )}
                  {entry.change && (
                    <span className="tw-rail__chg" style={{ color: toneColor(entry.tone ?? 'flat') }}>{entry.change}</span>
                  )}
                </button>
              </div>
            );
          })}
        </div>
      )}
      {collapsed && (
        <div className="tw-rail__list">
          {/* Collapsing trades WIDTH, not information. A rail that hides every symbol makes
              collapsing pure loss, so the stubs stay and only the detail goes. */}
          {entries.map((entry) => (
            <button
              key={`${entry.group}-${entry.symbol}`}
              type="button"
              className="tw-rail__row"
              data-current={entry.symbol === current}
              data-cursor={cursor === entry.symbol && entry.symbol !== current}
              onClick={() => onSelect(entry.symbol)}
              title={entry.name ? `${entry.symbol} · ${entry.name}` : entry.symbol}
            >
              <span className="tw-rail__sym" style={{ color: toneColor(entry.tone ?? 'flat') }}>{entry.symbol.slice(0, 4)}</span>
            </button>
          ))}
        </div>
      )}
    </nav>
  );
}
