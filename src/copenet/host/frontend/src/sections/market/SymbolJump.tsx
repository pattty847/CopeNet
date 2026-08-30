// Type-to-switch.
//
// Pressing any letter anywhere on the workspace opens this pinned to the chart's corner.
// It is the reflex every terminal trains, and it replaces a round trip through the global
// command palette — which, done two hundred times in a session, is the interaction that
// makes a research tool tiring to use.

import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { SymbolSearchResult } from './types';

export function SymbolJump({ seed, onClose, onPick }: { seed: string; onClose: () => void; onPick: (symbol: string) => void }) {
  const [value, setValue] = useState(seed);
  const [hits, setHits] = useState<SymbolSearchResult[]>([]);
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.setSelectionRange(seed.length, seed.length);
  }, [seed]);

  useEffect(() => {
    const token = value.trim().toUpperCase();
    if (token.length < 1) {
      setHits([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void wsClient
        .marketSymbolsSearch(token, 7)
        .then((results) => { setHits(results); setCursor(0); })
        .catch(() => setHits([]));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [value]);

  const commit = (symbol?: string) => {
    const picked = (symbol ?? hits[cursor]?.symbol ?? value).trim().toUpperCase();
    if (picked) onPick(picked);
  };

  return (
    <div className="tw-jump" role="dialog" aria-label="Jump to symbol">
      <input
        ref={inputRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onBlur={onClose}
        spellCheck={false}
        autoComplete="off"
        aria-label="Symbol"
        placeholder="Symbol"
        onKeyDown={(event) => {
          if (event.key === 'Escape') { onClose(); return; }
          if (event.key === 'Enter') { commit(); return; }
          if (event.key === 'ArrowDown') { setCursor((index) => Math.min(index + 1, Math.max(hits.length - 1, 0))); event.preventDefault(); }
          if (event.key === 'ArrowUp') { setCursor((index) => Math.max(index - 1, 0)); event.preventDefault(); }
        }}
      />
      {hits.length > 0 && (
        <div className="tw-jump__hits">
          {hits.map((hit, index) => (
            <button
              key={hit.symbol}
              type="button"
              className="tw-jump__hit"
              data-cursor={index === cursor}
              onMouseDown={(event) => { event.preventDefault(); commit(hit.symbol); }}
            >
              <b>{hit.symbol}</b><span>{hit.name}</span><small>{hit.exchange}</small>
            </button>
          ))}
        </div>
      )}
      <div className="tw-jump__hint">Enter to open · Esc to cancel · j / k to step the rail</div>
    </div>
  );
}
