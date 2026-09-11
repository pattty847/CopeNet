import { useState } from 'react';
import { compactMoney, decimal, METRIC_LABELS, metricValue, sortCandidates } from './model';
import type { Candidate, Preset } from './types';

export function CandidateTable({
  rows,
  preset,
  selected,
  onSelect,
  onOpen,
}: {
  rows: Candidate[];
  preset: Preset;
  selected: Set<string>;
  onSelect: (symbols: string[]) => void;
  onOpen: (symbol: string) => void;
}) {
  const [sort, setSort] = useState({
    key: preset.metric,
    ascending: preset.ascending,
  });
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const filtered = sortCandidates(
    rows.filter((row) => `${row.symbol} ${row.name} ${row.sector}`.toLowerCase().includes(search.toLowerCase())),
    sort.key,
    sort.ascending,
  );
  const currentPage = Math.min(page, Math.max(0, Math.ceil(filtered.length / 50) - 1));
  const visible = filtered.slice(currentPage * 50, (currentPage + 1) * 50);
  const allVisible = visible.length > 0 && visible.every((row) => selected.has(row.symbol));
  const toggle = (symbols: string[], checked: boolean) => {
    const next = new Set(selected);
    for (const symbol of symbols) {
      if (checked) next.add(symbol);
      else next.delete(symbol);
    }
    onSelect([...next]);
  };
  const sortBy = (key: string) => {
    setSort({ key, ascending: key === sort.key ? !sort.ascending : false });
    setPage(0);
  };
  const heading = (key: string, label: string) => (
    <th aria-sort={sort.key === key ? (sort.ascending ? 'ascending' : 'descending') : 'none'}>
      <button onClick={() => sortBy(key)}>
        {label}
        {sort.key === key ? (sort.ascending ? ' ↑' : ' ↓') : ''}
      </button>
    </th>
  );
  return (
    <>
      <div className="scr-table-tools">
        <label>
          Find in results{' '}
          <input
            type="search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(0);
            }}
            placeholder="Symbol, company or sector"
          />
        </label>
        <span>
          {filtered.length} matches · sorted by {METRIC_LABELS[sort.key] ?? sort.key}
        </span>
      </div>
      <div className="scr-table-scroll">
        <table className="scr-table">
          <thead>
            <tr>
              <th>
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
              <th>Company / direction</th>
              {heading('price', 'Price')}
              {heading('change', 'Day %')}
              {heading('marketCap', 'Market cap')}
              {heading('dollarVolume', 'Liquidity ≈')}
              {heading(preset.metric, METRIC_LABELS[preset.metric])}
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.id} data-selected={selected.has(row.symbol)}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Select ${row.symbol}`}
                    checked={selected.has(row.symbol)}
                    onChange={(event) => toggle([row.symbol], event.target.checked)}
                  />
                </td>
                <td>
                  <button className="scr-symbol" onClick={() => onOpen(row.symbol)}>
                    {row.symbol} <span>↗</span>
                  </button>
                  <span className="scr-company">{row.name || row.symbol}</span>
                  <small>
                    {row.sector || 'Sector unavailable'} · <span data-direction={row.direction}>{row.direction}</span>
                  </small>
                </td>
                <td>
                  $
                  {row.price.toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </td>
                <td data-direction={row.change == null ? '' : row.change >= 0 ? 'Bullish' : 'Bearish'}>
                  {decimal(row.change, '%')}
                </td>
                <td>{compactMoney(row.marketCap)}</td>
                <td>{compactMoney(row.dollarVolume)}</td>
                <td className="scr-key-metric">
                  {decimal(
                    metricValue(row, preset.metric),
                    preset.metric === 'relativeVolume' ? '×' : preset.metric === 'rsi' ? '' : '%',
                  )}
                </td>
                <td>
                  <details>
                    <summary>Why it matched</summary>
                    <ul>
                      {preset.rules.map((rule) => (
                        <li key={rule}>{rule}</li>
                      ))}
                    </ul>
                    <p>
                      RSI {decimal(row.rsi)} · From annual high {decimal(row.drawdown, '%')}
                      <br />
                      SMA50 {decimal(row.sma50)} · SMA200 {decimal(row.sma200)}
                      <br />
                      Month {decimal(row.monthReturn, '%')} · Rel. volume {decimal(row.relativeVolume, '×')}
                    </p>
                    <p>
                      {row.exchange} · {row.updateMode.replaceAll('_', ' ')}
                    </p>
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <div className="scr-empty">
          {search
            ? 'No results match this search.'
            : 'No companies match this setup in the saved universe. An empty screen is a valid result.'}
        </div>
      )}
      {filtered.length > 50 && (
        <div className="scr-pagination">
          <button className="tw-btn" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>
            Previous
          </button>
          <span>
            Page {currentPage + 1} of {Math.ceil(filtered.length / 50)}
          </span>
          <button
            className="tw-btn"
            disabled={(currentPage + 1) * 50 >= filtered.length}
            onClick={() => setPage(currentPage + 1)}
          >
            Next
          </button>
        </div>
      )}
    </>
  );
}
