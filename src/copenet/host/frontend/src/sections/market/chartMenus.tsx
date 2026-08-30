// Compact popover bodies for the chart toolbar.
//
// Plots lives in its own file: it grew a full indicator manager and this one was already at
// the size where a second responsibility stops being findable.

import { useEffect, useState, type FormEvent, type RefObject } from 'react';
import { X } from 'lucide-react';
import { ChartPopoverShell } from './chartPopoverShell';
import { wsClient } from '../../lib/wsClient';
import { normalizeComparisonExpression } from './chartComparison';
import { MM } from './marketUi';
import type { InsiderDisplayMode, InsiderLookback } from './chartRanges';
import type { SymbolSearchResult, TickerIntelligence } from './types';

// ---------------------------------------------------------------- compare

export function CompareMenu({
  anchor,
  open,
  onClose,
  expressions,
  onAdd,
  onRemove,
  onClear,
}: {
  anchor: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  expressions: string[];
  onAdd: (expression: string) => void;
  onRemove: (expression: string) => void;
  onClear: () => void;
}) {
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<SymbolSearchResult[]>([]);

  useEffect(() => {
    const token = input.match(/([A-Za-z0-9.^=_-]+)\s*$/)?.[1] ?? '';
    if (token.length < 2) {
      setSuggestions([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void wsClient.marketSymbolsSearch(input, 5, true).then(setSuggestions).catch(() => setSuggestions([]));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [input]);

  const addExpression = () => {
    const expression = normalizeComparisonExpression(input);
    if (!expression) return setError('Enter a ticker or formula, such as (XLK + QQQ) / 2.');
    if (expressions.includes(expression)) return setError('That comparison is already plotted.');
    if (expressions.length >= 5) return setError('Remove a series before adding another.');
    onAdd(expression);
    setInput('');
    setError(null);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    addExpression();
  };

  return (
    <ChartPopoverShell
      anchor={anchor}
      open={open}
      onClose={onClose}
      title="Compare"
      width={316}
    >
      <form onSubmit={submit}>
        <input
          value={input}
          onChange={(event) => { setInput(event.target.value); if (error) setError(null); }}
          placeholder="Compare: VOO or (XLK + QQQ) / 2"
          autoCapitalize="characters"
          spellCheck={false}
          autoComplete="off"
          aria-label="Comparison ticker or formula"
          className="tw-input tw-pop__compare-input"
          onKeyDown={(event) => {
            if (event.key !== 'Enter') return;
            event.preventDefault();
            addExpression();
          }}
        />
        {error && <div role="alert" style={{ marginTop: 6, color: '#d96d5f', fontSize: 10 }}>{error}</div>}
        {suggestions.length > 0 && (
          <div style={{ marginTop: 6, border: '1px solid rgba(254,252,244,.07)', borderRadius: 4, overflow: 'hidden' }}>
            {suggestions.map((result) => (
              <button
                key={`${result.type}:${result.symbol}`}
                type="button"
                className="tw-jump__hit"
                onClick={() => {
                  setInput(result.type === 'formula'
                    ? result.symbol
                    : input.replace(/([A-Za-z0-9.^=_-]+)\s*$/, result.symbol));
                  setSuggestions([]);
                }}
              >
                <b>{result.type === 'formula' ? `ƒ ${result.symbol}` : result.symbol}</b><span>{result.name}</span><small>{result.exchange}</small>
              </button>
            ))}
          </div>
        )}
      </form>

      {expressions.length > 0 && (
        <div className="tw-pop__section tw-pop__chips">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {expressions.map((expression) => (
              <span key={expression} className="tw-btn" style={{ gap: 5 }}>
                <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>{expression}</span>
                <button type="button" onClick={() => onRemove(expression)} aria-label={`Remove ${expression}`} style={{ display: 'inline-flex', border: 0, background: 'transparent', color: 'inherit', cursor: 'pointer', padding: 0 }}><X size={11} /></button>
              </span>
            ))}
          </div>
          <button type="button" className="tw-btn" onClick={onClear}>Clear all</button>
        </div>
      )}
    </ChartPopoverShell>
  );
}

// ----------------------------------------------------------------- events

export function EventsMenu({
  anchor,
  open,
  onClose,
  showInsider,
  onShowInsider,
  lookback,
  onLookback,
  displayMode,
  onDisplayMode,
  disabled,
}: {
  anchor: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  showInsider: boolean;
  onShowInsider: (value: boolean) => void;
  lookback: InsiderLookback;
  onLookback: (value: InsiderLookback) => void;
  displayMode: InsiderDisplayMode;
  onDisplayMode: (value: InsiderDisplayMode) => void;
  disabled: boolean;
}) {
  return (
    <ChartPopoverShell
      anchor={anchor}
      open={open}
      onClose={onClose}
      title="Filings & events"
      width={310}
    >
      <fieldset disabled={disabled} style={{ border: 0, margin: 0, padding: 0, opacity: disabled ? 0.45 : 1 }}>
        <label className="tw-switch">
          <span>Insider transactions</span>
          <input type="checkbox" checked={showInsider} onChange={(event) => onShowInsider(event.target.checked)} />
        </label>

        {showInsider && (
          <>
            <div className="tw-pop__section tw-pop__control-row">
              <div className="tw-pop__label">Lookback</div>
              <div className="tw-choices">
                {(['chart', '90D', '1Y', '3Y', '5Y', 'MAX'] as const).map((value) => (
                  <button key={value} type="button" aria-pressed={lookback === value} onClick={() => onLookback(value)}>
                    {value === 'chart' ? 'Chart' : value === 'MAX' ? 'All' : value}
                  </button>
                ))}
              </div>
            </div>

            <div className="tw-pop__section tw-pop__control-row">
              <div className="tw-pop__label">Markers</div>
              <div className="tw-choices">
                <button type="button" aria-pressed={displayMode === 'clusters'} onClick={() => onDisplayMode('clusters')}>Clusters</button>
                <button type="button" aria-pressed={displayMode === 'individual'} onClick={() => onDisplayMode('individual')}>Trades</button>
              </div>
            </div>
          </>
        )}
        {disabled && (
          <div className="tw-pop__note">Unavailable in Compare mode</div>
        )}
      </fieldset>
    </ChartPopoverShell>
  );
}

// --------------------------------------------------------------- settings

/** Chart settings doubles as the DATA INSPECTOR. Provenance — how much history exists, what
 *  the price basis is, which filing a plotted series came from — used to be printed under the
 *  chart as permanent grey wallpaper. It is real information and it belongs one click away
 *  from the thing it describes, not in front of everyone all the time. */
export function SettingsMenu({
  anchor,
  open,
  onClose,
  intelligence,
  priceBasis,
  barCount,
  plotSource,
}: {
  anchor: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  intelligence?: TickerIntelligence | null;
  priceBasis: string;
  barCount: number;
  plotSource?: { label: string; count: number; form?: string; accession?: string; url?: string | null; warnings: string[] } | null;
}) {
  const quality = intelligence?.dataQuality;
  return (
    <ChartPopoverShell anchor={anchor} open={open} onClose={onClose} title="Chart data" width={334}>
      <div className="tw-pop__section">
        <div className="tw-pop__label">Price series</div>
        <div className="tw-kv"><span className="tw-kv__k">Basis</span><span className="tw-kv__v">{priceBasis.replace('_', '-')}</span></div>
        <div className="tw-kv"><span className="tw-kv__k">Bars in view</span><span className="tw-kv__v">{barCount.toLocaleString()}</span></div>
        {quality && <div className="tw-kv"><span className="tw-kv__k">History</span><span className="tw-kv__v">{quality.historyWeeks.toLocaleString()} weeks</span></div>}
        {quality && <div className="tw-kv"><span className="tw-kv__k">Volume</span><span className="tw-kv__v">{quality.hasVolume ? 'Available' : 'Unavailable'}</span></div>}
      </div>

      {plotSource && (
        <div className="tw-pop__section">
          <div className="tw-pop__label">{plotSource.label} provenance</div>
          <div className="tw-kv"><span className="tw-kv__k">Observations</span><span className="tw-kv__v">{plotSource.count.toLocaleString()}</span></div>
          {plotSource.form && (
            <div className="tw-kv">
              <span className="tw-kv__k">Latest filing</span>
              <span className="tw-kv__v">
                {plotSource.url
                  ? <a href={plotSource.url} target="_blank" rel="noreferrer" style={{ color: MM.info }}>{plotSource.form}</a>
                  : plotSource.form}
              </span>
            </div>
          )}
          {plotSource.accession && <div className="tw-kv"><span className="tw-kv__k">Accession</span><span className="tw-kv__v" style={{ fontSize: 10 }}>{plotSource.accession}</span></div>}
          {plotSource.warnings.length > 0 && (
            <p className="tw-pop__note" style={{ color: MM.down }}>{plotSource.warnings.map((flag) => flag.replaceAll('_', ' ')).join(' · ')}</p>
          )}
        </div>
      )}
    </ChartPopoverShell>
  );
}
