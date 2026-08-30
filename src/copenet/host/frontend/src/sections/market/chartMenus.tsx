// Popover bodies for the chart toolbar.
//
// Each one answers a single question and closes. Two rules they all follow: the popover
// manages STATE THAT IS ALREADY ON THE CHART and points elsewhere for browsing (a menu that
// also has to be a catalogue becomes a graveyard), and any control that cannot work right now
// is disabled WITH ITS REASON rather than hidden — a control that vanishes teaches nothing.

import { useEffect, useState, type FormEvent, type RefObject } from 'react';
import { ArrowRight, X } from 'lucide-react';
import { MarketFloatingPopover } from './MarketFloatingPopover';
import { wsClient } from '../../lib/wsClient';
import { normalizeComparisonExpression } from './chartComparison';
import { MM } from './marketUi';
import type { InsiderDisplayMode, InsiderLookback } from './chartRanges';
import type { FinancialFrequency, FinancialMetricInfo, SymbolSearchResult, TickerIntelligence } from './types';

function Shell({
  anchor,
  open,
  onClose,
  title,
  subtitle,
  width = 320,
  children,
}: {
  anchor: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  width?: number;
  children: React.ReactNode;
}) {
  return (
    <MarketFloatingPopover anchorRef={anchor} open={open} onClose={onClose} width={width}>
      <div className="tw-pop">
        <div className="tw-pop__head">
          <div>
            <div className="tw-pop__title">{title}</div>
            {subtitle && <div className="tw-pop__sub">{subtitle}</div>}
          </div>
          <button type="button" className="tw-iconbtn" onClick={onClose} aria-label={`Close ${title}`}><X size={13} /></button>
        </div>
        <div className="tw-pop__body">{children}</div>
      </div>
    </MarketFloatingPopover>
  );
}

// ------------------------------------------------------------------ plots

export function PlotsMenu({
  anchor,
  open,
  onClose,
  metrics,
  metric,
  frequency,
  onFrequency,
  onClearMetric,
  showVolume,
  onShowVolume,
  comparisonActive,
  onBrowse,
}: {
  anchor: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  metrics: FinancialMetricInfo[];
  metric: string | null;
  frequency: FinancialFrequency;
  onFrequency: (value: FinancialFrequency) => void;
  onClearMetric: () => void;
  showVolume: boolean;
  onShowVolume: (value: boolean) => void;
  comparisonActive: boolean;
  onBrowse: () => void;
}) {
  const info = metric ? metrics.find((entry) => entry.id === metric) ?? null : null;
  const valuation = info?.factType === 'valuation';
  const choices = info?.frequencies ?? (['quarterly', 'ttm', 'annual'] as FinancialFrequency[]);

  return (
    <Shell anchor={anchor} open={open} onClose={onClose} title="Plots" subtitle="What is drawn on the chart right now." width={318}>
      <div className="tw-pop__section">
        <div className="tw-pop__label">On the chart</div>
        <div className="tw-pop__row">
          <label className="tw-switch" style={{ flex: 1 }}>
            <span>Volume<small>Traded volume under the price</small></span>
            <input type="checkbox" checked={showVolume} onChange={(event) => onShowVolume(event.target.checked)} />
          </label>
        </div>
        {info ? (
          <div className="tw-pop__row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 7 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
              <span style={{ color: MM.info, font: '600 10px Inter' }}>{info.label}</span>
              <button type="button" className="tw-iconbtn" onClick={onClearMetric} aria-label={`Remove ${info.label} plot`} title="Remove plot"><X size={12} /></button>
            </div>
            {!valuation && (
              <div className="tw-choices">
                {choices.map((value) => (
                  <button key={value} type="button" aria-pressed={frequency === value} onClick={() => onFrequency(value)}>
                    {value === 'ttm' ? 'TTM' : value === 'annual' ? 'Annual' : 'Quarter'}
                  </button>
                ))}
              </div>
            )}
            {valuation && <p className="tw-pop__note">Valuation multiples are trailing-twelve-month by definition.</p>}
          </div>
        ) : (
          <p className="tw-pop__note">No fundamental series plotted.</p>
        )}
      </div>

      <div className="tw-pop__section">
        <button type="button" className="tw-plotrow" onClick={() => { onBrowse(); onClose(); }} disabled={comparisonActive}>
          Browse fundamentals
          <span className="tw-plotrow__val"><ArrowRight size={12} /></span>
        </button>
        <p className="tw-pop__note">
          {comparisonActive
            ? 'Fundamental plots are price-anchored and cannot be drawn while the chart is rebased for comparison.'
            : 'Every series in the Fundamentals tab plots to the chart from its own card, so you see the shape before you commit to it.'}
        </p>
      </div>
    </Shell>
  );
}

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
    const token = input.toUpperCase().replace(/\s+/g, '').split('/').at(-1) ?? '';
    if (token.length < 2) {
      setSuggestions([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void wsClient.marketSymbolsSearch(token, 5).then(setSuggestions).catch(() => setSuggestions([]));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [input]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const expression = normalizeComparisonExpression(input);
    if (!expression) return setError('Enter a ticker or one ratio, such as XLK/GLD.');
    if (expressions.includes(expression)) return setError('That comparison is already plotted.');
    if (expressions.length >= 5) return setError('Remove a series before adding another.');
    onAdd(expression);
    setInput('');
    setError(null);
  };

  return (
    <Shell
      anchor={anchor}
      open={open}
      onClose={onClose}
      title="Compare"
      subtitle="Rebases the price pane to indexed % from the start of the visible range. Price-anchored plots — alerts, fundamentals, filing markers — cannot be drawn while this is on."
      width={352}
    >
      <form onSubmit={submit}>
        <div className="tw-pop__label">Ticker or ratio</div>
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            value={input}
            onChange={(event) => { setInput(event.target.value); if (error) setError(null); }}
            placeholder="VOO or VOO/GLD"
            autoCapitalize="characters"
            spellCheck={false}
            autoComplete="off"
            aria-label="Comparison ticker or ratio"
            className="tw-input"
            style={{ flex: 1 }}
          />
          <button type="submit" className="tw-btn">Add</button>
        </div>
        {error && <div role="alert" style={{ marginTop: 6, color: '#d96d5f', fontSize: 10 }}>{error}</div>}
        {suggestions.length > 0 && (
          <div style={{ marginTop: 6, border: '1px solid rgba(254,252,244,.07)', borderRadius: 4, overflow: 'hidden' }}>
            {suggestions.map((result) => (
              <button
                key={result.symbol}
                type="button"
                className="tw-jump__hit"
                onClick={() => {
                  const parts = input.toUpperCase().replace(/\s+/g, '').split('/');
                  parts[parts.length - 1] = result.symbol;
                  setInput(parts.join('/'));
                  setSuggestions([]);
                }}
              >
                <b>{result.symbol}</b><span>{result.name}</span><small>{result.exchange}</small>
              </button>
            ))}
          </div>
        )}
      </form>

      <div className="tw-pop__section">
        <div className="tw-pop__label">Plotted</div>
        {expressions.length === 0 ? (
          <p className="tw-pop__note">Nothing yet. <b style={{ color: '#a29b90' }}>VOO</b> compares total return; <b style={{ color: '#a29b90' }}>VOO/GLD</b> plots the relative-strength ratio.</p>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {expressions.map((expression) => (
              <span key={expression} className="tw-btn" style={{ gap: 5 }}>
                <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>{expression}</span>
                <button type="button" onClick={() => onRemove(expression)} aria-label={`Remove ${expression}`} style={{ display: 'inline-flex', border: 0, background: 'transparent', color: 'inherit', cursor: 'pointer', padding: 0 }}><X size={11} /></button>
              </span>
            ))}
          </div>
        )}
        {expressions.length > 0 && <button type="button" className="tw-btn" style={{ marginTop: 8 }} onClick={onClear}>Clear all</button>}
      </div>
    </Shell>
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
    <Shell
      anchor={anchor}
      open={open}
      onClose={onClose}
      title="Filings & events"
      subtitle={disabled ? 'Filing markers are price-anchored and are hidden while the chart is rebased for comparison.' : '8-K and Form 144 markers are always on. Form 4 transactions are optional because they are dense.'}
      width={330}
    >
      <fieldset disabled={disabled} style={{ border: 0, margin: 0, padding: 0, opacity: disabled ? 0.45 : 1 }}>
        <label className="tw-switch">
          <span>Plot Form 4 transactions<small>Executed insider trades</small></span>
          <input type="checkbox" checked={showInsider} onChange={(event) => onShowInsider(event.target.checked)} />
        </label>

        <div className="tw-pop__section" style={{ opacity: showInsider ? 1 : 0.45 }}>
          <div className="tw-pop__label">Form 4 lookback</div>
          <div className="tw-choices">
            {(['chart', '90D', '1Y', '3Y', '5Y', 'MAX'] as const).map((value) => (
              <button key={value} type="button" disabled={!showInsider} aria-pressed={lookback === value} onClick={() => onLookback(value)}>
                {value === 'chart' ? 'Chart range' : value === 'MAX' ? 'All' : value}
              </button>
            ))}
          </div>
        </div>

        <div className="tw-pop__section" style={{ opacity: showInsider ? 1 : 0.45 }}>
          <div className="tw-pop__label">Display</div>
          <div className="tw-choices">
            <button type="button" disabled={!showInsider} aria-pressed={displayMode === 'clusters'} onClick={() => onDisplayMode('clusters')}>Cluster boxes</button>
            <button type="button" disabled={!showInsider} aria-pressed={displayMode === 'individual'} onClick={() => onDisplayMode('individual')}>Individual trades</button>
          </div>
          <p className="tw-pop__note">Clusters summarise net flow by date range. Individual mode is for inspecting single executed trades.</p>
        </div>
      </fieldset>
    </Shell>
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
  logScale,
  onLogScale,
  intelligence,
  priceBasis,
  barCount,
  plotSource,
}: {
  anchor: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  logScale: boolean;
  onLogScale: (value: boolean) => void;
  intelligence?: TickerIntelligence | null;
  priceBasis: string;
  barCount: number;
  plotSource?: { label: string; count: number; form?: string; accession?: string; url?: string | null; warnings: string[] } | null;
}) {
  const quality = intelligence?.dataQuality;
  return (
    <Shell anchor={anchor} open={open} onClose={onClose} title="Chart settings & data" width={334}>
      <div className="tw-pop__section">
        <div className="tw-pop__label">Price axis</div>
        <div className="tw-choices">
          <button type="button" aria-pressed={!logScale} onClick={() => onLogScale(false)}>Linear</button>
          <button type="button" aria-pressed={logScale} onClick={() => onLogScale(true)}>Logarithmic</button>
        </div>
      </div>

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
    </Shell>
  );
}
