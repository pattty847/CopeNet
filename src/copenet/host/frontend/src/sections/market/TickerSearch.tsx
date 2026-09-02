import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import { MM, mono } from './marketUi';
import type { SymbolSearchResult } from './types';

function hasFormulaIntent(value: string): boolean {
  return /[+*/()]|\s-\s/.test(value);
}

function replaceActiveOperand(value: string, symbol: string): string {
  return value.replace(/([A-Za-z0-9.^=_-]+)\s*$/, symbol);
}

/** Debounced ticker/company-name typeahead (market.symbols.search — live yfinance lookup, not
 * limited to the fixed dashboard UNIVERSE). Selecting a result navigates straight to the ticker
 * chart page via onSelect, same as clicking any symbol elsewhere on the dashboard. */
export function TickerSearch({
  onSelect,
  fullWidth,
  allowFormula = true,
  placeholder = 'Look up a ticker or company…',
}: {
  onSelect: (symbol: string, name: string, type: SymbolSearchResult['type']) => void;
  fullWidth?: boolean;
  allowFormula?: boolean;
  placeholder?: string;
}) {
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
        .marketSymbolsSearch(trimmed, 8, allowFormula)
        .then((next) => setResults(next))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [allowFormula, query]);

  useEffect(() => {
    const onClickAway = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClickAway);
    return () => document.removeEventListener('mousedown', onClickAway);
  }, []);

  const pick = (result: SymbolSearchResult) => {
    onSelect(result.symbol, result.name, result.type);
    setQuery('');
    setResults([]);
    setOpen(false);
  };

  const choose = (result: SymbolSearchResult) => {
    if (allowFormula && result.type === 'symbol' && hasFormulaIntent(query)) {
      setQuery(replaceActiveOperand(query, result.symbol));
      setResults([]);
      setOpen(true);
      return;
    }
    pick(result);
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
          if (e.key === 'Enter' && results.length) choose(results[0]);
          if (e.key === 'Escape') setOpen(false);
        }}
        placeholder={allowFormula ? 'Ticker, company, or formula…' : placeholder}
        aria-label={allowFormula ? 'Search ticker, company, or formula' : 'Search ticker or company'}
        style={{
          width: '100%',
          boxSizing: 'border-box',
          background: '#050506',
          border: `1px solid ${MM.border}`,
          borderRadius: 8,
          padding: '7px 11px',
          color: MM.text,
          font: '500 12px var(--mkt-sans)',
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
                key={`${r.type}:${r.symbol}`}
                onClick={() => choose(r)}
                style={{
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 10,
                  width: '100%',
                  border: 'none',
                  background: r.type === 'formula' ? 'rgba(251,148,35,.07)' : 'transparent',
                  borderRadius: 7,
                  padding: '7px 9px',
                  textAlign: 'left',
                }}
              >
                <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
                  <span style={{ fontFamily: mono, fontSize: 12.5, fontWeight: 600, color: r.type === 'formula' ? MM.accent : MM.text }}>
                    {r.type === 'formula' ? 'ƒ ' : ''}{r.symbol}
                  </span>
                  <span style={{ fontSize: 11, color: MM.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</span>
                </span>
                <span style={{ fontSize: 9.5, color: r.type === 'formula' ? MM.accent : MM.dim, flex: '0 0 auto' }}>{r.exchange}</span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
