// One row per name, one line each. The left half is context; the right half is the rules
// themselves, each value drawn as a tick inside its rule window. Clicking a row focuses it
// for the setup dock; clicking the symbol opens the ticker workspace.
import { useState } from 'react';
import { compactMoney, METRIC_LABELS, metricValue, sortCandidates } from './model';
import { formatRuleValue, outsideWindow, ruleColumns, ruleValue, windowPosition } from './ruleWindows';
import type { Candidate, Preset } from './types';

const PAGE = 50;
const CONTEXT: { key: string; label: string }[] = [
  { key: 'price', label: 'Price' },
  { key: 'change', label: 'Day' },
  { key: 'marketCap', label: 'Cap' },
  { key: 'dollarVolume', label: 'Liq/day' },
  { key: 'relativeVolume', label: 'RVol' },
];

export function CandidateTable({
  rows,
  preset,
  selected,
  focus,
  newSymbols,
  onSelect,
  onFocus,
  onOpen,
}: {
  rows: Candidate[];
  preset: Preset;
  selected: Set<string>;
  focus: string | null;
  newSymbols: Set<string>;
  onSelect: (symbols: string[]) => void;
  onFocus: (symbol: string) => void;
  onOpen: (symbol: string) => void;
}) {
  const [sort, setSort] = useState({ key: preset.metric, ascending: preset.ascending });
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const filtered = sortCandidates(
    rows.filter((row) => `${row.symbol} ${row.name} ${row.sector}`.toLowerCase().includes(search.toLowerCase())),
    sort.key,
    sort.ascending,
  );
  const currentPage = Math.min(page, Math.max(0, Math.ceil(filtered.length / PAGE) - 1));
  const visible = filtered.slice(currentPage * PAGE, (currentPage + 1) * PAGE);
  const allVisible = visible.length > 0 && visible.every((row) => selected.has(row.symbol));
  const columns = ruleColumns(preset);
  const toggle = (symbols: string[], checked: boolean) => {
    const next = new Set(selected);
    for (const symbol of symbols) {
      if (checked) next.add(symbol);
      else next.delete(symbol);
    }
    onSelect([...next]);
  };
  const sortBy = (key: string) => {
    setSort({ key, ascending: key === sort.key ? !sort.ascending : key === preset.metric ? preset.ascending : false });
    setPage(0);
  };
  const heading = (key: string, label: string, className = '') => (
    <th key={key} className={className} aria-sort={sort.key === key ? (sort.ascending ? 'ascending' : 'descending') : 'none'} data-sorted={sort.key === key}>
      <button type="button" onClick={() => sortBy(key)}>
        {label}
        {sort.key === key ? (sort.ascending ? ' ↑' : ' ↓') : ''}
      </button>
    </th>
  );
  const sortLabel = (columns.find((rule) => rule.key === sort.key)?.label ?? CONTEXT.find((column) => column.key === sort.key)?.label ?? METRIC_LABELS[sort.key] ?? sort.key).toLowerCase();
  return (
    <>
      <div className="scr-table-tools">
        <label className="scr-search">
          <span className="scr-sr-only">Find in results</span>
          <span aria-hidden="true">⌕</span>
          <input
            type="search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(0);
            }}
            placeholder="Find in results"
          />
        </label>
        <span className="scr-table-tools__count">
          <b>{filtered.length}</b> of {rows.length} matches · ordered by {sortLabel}, {sort.ascending ? 'ascending' : 'descending'}
        </span>
        <span className="scr-table-tools__hint">Click a row to draw its setup · click the symbol to open the ticker</span>
      </div>
      <div className="scr-table-scroll">
        <table className="scr-table">
          <thead>
            <tr className="scr-table__groups">
              <th colSpan={3} />
              <th colSpan={CONTEXT.length}>Context</th>
              <th colSpan={Math.max(1, columns.length)} className="scr-table__rulegroup">
                Why it matched · tick = value inside the rule window
              </th>
            </tr>
            <tr>
              <th className="scr-table__check">
                <input
                  type="checkbox"
                  aria-label="Select this page"
                  checked={allVisible}
                  onChange={(event) =>
                    toggle(
                      visible.map((row) => row.symbol),
                      event.target.checked,
                    )
                  }
                />
              </th>
              <th className="scr-table__left">Symbol</th>
              <th className="scr-table__left">Sector</th>
              {CONTEXT.map((column) => heading(column.key, column.label))}
              {columns.length > 0
                ? columns.map((rule) => heading(rule.key, rule.label, rule.key === preset.metric ? 'scr-table__key' : ''))
                : heading(preset.metric, METRIC_LABELS[preset.metric] ?? preset.metric, 'scr-table__key')}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.id} data-selected={selected.has(row.symbol)} data-focus={focus === row.symbol} onClick={() => onFocus(row.symbol)}>
                <td className="scr-table__check">
                  <input
                    type="checkbox"
                    aria-label={`Select ${row.symbol}`}
                    checked={selected.has(row.symbol)}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => toggle([row.symbol], event.target.checked)}
                  />
                </td>
                <td className="scr-table__identity">
                  <button
                    type="button"
                    className="scr-symbol"
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpen(row.symbol);
                    }}
                  >
                    {row.symbol} <span>↗</span>
                  </button>
                  <span className="scr-company">{row.name || row.symbol}</span>
                  {newSymbols.has(row.symbol) && (
                    <span className="scr-new" title="Not in the previous observation">
                      NEW
                    </span>
                  )}
                </td>
                <td className="scr-table__sector">{row.sector || '—'}</td>
                <td>{row.price >= 1000 ? row.price.toLocaleString('en-US', { maximumFractionDigits: 0 }) : row.price.toFixed(2)}</td>
                <td data-direction={row.change == null ? '' : row.change >= 0 ? 'Bullish' : 'Bearish'}>
                  {row.change == null ? '—' : `${row.change > 0 ? '+' : ''}${row.change.toFixed(2)}%`}
                </td>
                <td>{compactMoney(row.marketCap)}</td>
                <td>{compactMoney(row.dollarVolume)}</td>
                <td data-hot={row.relativeVolume != null && row.relativeVolume >= 1.5}>{row.relativeVolume == null ? '—' : `${row.relativeVolume.toFixed(2)}×`}</td>
                {columns.length > 0 ? (
                  columns.map((rule) => {
                    const value = ruleValue(row, rule);
                    const position = windowPosition(rule, value);
                    return (
                      <td key={rule.key} className={`scr-table__rule ${rule.key === preset.metric ? 'scr-table__key' : ''}`} title={`${rule.label}: ${rule.condition}`}>
                        <span className="scr-rulevalue">
                          <span>{formatRuleValue(rule, value)}</span>
                          <span className="scr-window" aria-hidden="true">
                            {position != null && <i data-edge={outsideWindow(rule, value)} style={{ left: `${(position * 100).toFixed(1)}%` }} />}
                          </span>
                        </span>
                      </td>
                    );
                  })
                ) : (
                  <td className="scr-table__rule scr-table__key">{metricValue(row, preset.metric)?.toFixed(1) ?? '—'}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <div className="scr-empty">{search ? 'No results match this search.' : 'No companies match this setup in the saved universe. An empty screen is a valid result.'}</div>
      )}
      {filtered.length > PAGE && (
        <div className="scr-pagination">
          <button type="button" className="tw-btn tw-btn--sm" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>
            Previous
          </button>
          <span>
            Page {currentPage + 1} of {Math.ceil(filtered.length / PAGE)}
          </span>
          <button type="button" className="tw-btn tw-btn--sm" disabled={(currentPage + 1) * PAGE >= filtered.length} onClick={() => setPage(currentPage + 1)}>
            Next
          </button>
        </div>
      )}
    </>
  );
}
