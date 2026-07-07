import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import { MM, mono } from './marketUi';
import type { SymbolSearchResult } from './types';

/** Debounced ticker/company-name typeahead (market.symbols.search — live yfinance lookup, not
 * limited to the fixed dashboard UNIVERSE). Selecting a result navigates straight to the ticker
 * chart page via onSelect, same as clicking any symbol elsewhere on the dashboard. */
export function TickerSearch({ onSelect, fullWidth }: { onSelect: (symbol: string, name: string) => void; fullWidth?: boolean }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SymbolSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    debounceRef.current = setTimeout(() => {
      wsClient
        .marketSymbolsSearch(trimmed, 8)
        .then((next) => setResults(next))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  useEffect(() => {
    const onClickAway = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClickAway);
    return () => document.removeEventListener('mousedown', onClickAway);
  }, []);

  const pick = (result: SymbolSearchResult) => {
    onSelect(result.symbol, result.name);
    setQuery('');
    setResults([]);
    setOpen(false);
  };

  return (
    <div ref={containerRef} style={{ position: 'relative', width: fullWidth ? '100%' : 260 }}>
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && results.length) pick(results[0]);
          if (e.key === 'Escape') setOpen(false);
        }}
        placeholder="Look up a ticker or company…"
        style={{
          width: '100%',
          boxSizing: 'border-box',
          background: '#050506',
          border: `1px solid ${MM.border}`,
          borderRadius: 8,
          padding: '7px 11px',
          color: MM.text,
          font: '500 12px Inter',
          outline: 'none',
        }}
      />
      {open && (loading || results.length > 0) && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            background: MM.panel,
            border: `1px solid ${MM.border}`,
            borderRadius: 10,
            padding: 4,
            zIndex: 20,
            boxShadow: '0 12px 24px rgba(0,0,0,.4)',
          }}
        >
          {loading && <div style={{ padding: '8px 10px', fontSize: 11, color: MM.dim, fontStyle: 'italic' }}>Searching…</div>}
          {!loading &&
            results.map((r) => (
              <button
                key={r.symbol}
                onClick={() => pick(r)}
                style={{
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 10,
                  width: '100%',
                  border: 'none',
                  background: 'transparent',
                  borderRadius: 7,
                  padding: '7px 9px',
                  textAlign: 'left',
                }}
              >
                <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
                  <span style={{ fontFamily: mono, fontSize: 12.5, fontWeight: 600, color: MM.text }}>{r.symbol}</span>
                  <span style={{ fontSize: 11, color: MM.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</span>
                </span>
                <span style={{ fontSize: 9.5, color: MM.dim, flex: '0 0 auto' }}>{r.exchange}</span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
