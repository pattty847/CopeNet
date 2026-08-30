// Type-to-switch.
//
// Pressing any letter anywhere on the workspace opens this pinned to the chart's corner.
// It is the reflex every terminal trains, and it replaces a round trip through the global
// command palette — which, done two hundred times in a session, is the interaction that
// makes a research tool tiring to use.

import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { SymbolSearchResult } from './types';

function hasFormulaIntent(value: string): boolean {
  return /[+*/()]|\s-\s/.test(value);
}

function replaceActiveOperand(value: string, symbol: string): string {
  return value.replace(/([A-Za-z0-9.^=_-]+)\s*$/, symbol);
}

export function SymbolJump({
  seed,
  onClose,
  onPick,
}: {
  seed: string;
  onClose: () => void;
  onPick: (value: string, type: SymbolSearchResult['type']) => void;
}) {
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

  const commit = (result?: SymbolSearchResult) => {
    const selected = result ?? hits[cursor];
    const picked = (selected?.symbol ?? value).trim().toUpperCase();
    if (picked) onPick(picked, selected?.type ?? (hasFormulaIntent(picked) ? 'formula' : 'symbol'));
  };

  const choose = (hit: SymbolSearchResult) => {
    if (hit.type === 'symbol' && hasFormulaIntent(value)) {
      setValue(replaceActiveOperand(value, hit.symbol));
      setHits([]);
      return;
    }
    commit(hit);
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
              key={`${hit.type}:${hit.symbol}`}
              type="button"
              className="tw-jump__hit"
              data-cursor={index === cursor}
              onMouseDown={(event) => { event.preventDefault(); choose(hit); }}
            >
              <b>{hit.type === 'formula' ? `ƒ ${hit.symbol}` : hit.symbol}</b><span>{hit.name}</span><small>{hit.exchange}</small>
            </button>
          ))}
        </div>
      )}
      <div className="tw-jump__hint">Enter to plot · + − × ÷ and parentheses supported · Esc to cancel</div>
    </div>
  );
}
