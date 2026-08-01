import type { FinancialFrequency, ValuationSeriesPayload } from './types';
import type { FinancialSeriesState } from './useFinancialSeries';
import { formatFinancialDate, formatFinancialValue } from './financialOverlay';
import { MM, mono } from './marketUi';

export type OverlayMetric = 'revenue' | 'trailing_pe';

const FREQUENCIES: Array<{ value: FinancialFrequency; label: string }> = [
  { value: 'quarterly', label: 'Quarter' },
  { value: 'ttm', label: 'TTM' },
  { value: 'annual', label: 'Annual' },
];

export function FinancialOverlayControls({
  metric,
  frequency,
  loading,
  onMetric,
  onFrequency,
}: {
  metric: OverlayMetric | null;
  frequency: FinancialFrequency;
  loading: boolean;
  onMetric: (metric: OverlayMetric | null) => void;
  onFrequency: (frequency: FinancialFrequency) => void;
}) {
  const button = (value: OverlayMetric, label: string, title: string) => {
    const active = metric === value;
    return (
      <button
        key={value}
        onClick={() => onMetric(active ? null : value)}
        aria-pressed={active}
        title={title}
        style={{
          cursor: 'pointer',
          border: `1px solid ${active ? 'rgba(90,143,199,.45)' : MM.border}`,
          background: active ? 'rgba(90,143,199,.12)' : 'transparent',
          color: active ? '#8fb8e8' : MM.muted,
          borderRadius: 7,
          padding: '5px 9px',
          font: '600 9.5px Inter',
          letterSpacing: '.06em',
          textTransform: 'uppercase',
          whiteSpace: 'nowrap',
        }}
      >
        {loading && active ? '◍ ' : value === 'revenue' ? '∿ ' : ''}{label}
      </button>
    );
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <div
        aria-label="Financial chart overlay"
        style={{ display: 'flex', gap: 3, background: '#050506', border: `1px solid ${MM.border}`, borderRadius: 9, padding: 3 }}
      >
        {button('revenue', 'Revenue', 'Plot canonical SEC revenue from the date each filing became public')}
        {button('trailing_pe', 'P/E', 'Plot split-adjusted price divided by then-known TTM diluted EPS')}
      </div>
      {metric === 'revenue' && (
        <div style={{ display: 'flex', gap: 2, background: '#050506', border: `1px solid ${MM.border}`, borderRadius: 7, padding: 2 }}>
          {FREQUENCIES.map((option) => (
            <button
              key={option.value}
              onClick={() => onFrequency(option.value)}
              aria-pressed={frequency === option.value}
              style={{
                cursor: 'pointer',
                border: 'none',
                borderRadius: 5,
                padding: '4px 7px',
                background: frequency === option.value ? 'rgba(90,143,199,.18)' : 'transparent',
                color: frequency === option.value ? '#8fb8e8' : MM.dim,
                font: '600 9px Inter',
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function FinancialOverlayStatus({
  metric,
  state,
}: {
  metric: OverlayMetric | null;
  state: FinancialSeriesState;
}) {
  if (!metric) return null;
  const label = metric === 'trailing_pe' ? 'P/E' : 'Revenue';
  if (state.loading) {
    return <div style={{ fontSize: 11, color: MM.dim, marginTop: 6 }}>Loading {label === 'P/E' ? 'point-in-time valuation' : 'normalized SEC history'}…</div>;
  }
  if (state.error) {
    return <div role="alert" style={{ fontSize: 11, color: MM.down, marginTop: 6 }}>{label} series failed: {state.error}</div>;
  }
  const observations = state.data?.observations ?? [];
  const plotted = observations.filter((observation) => observation.value != null);
  if (state.loaded && !plotted.length) {
    return (
      <div style={{ fontSize: 11, color: MM.dim, marginTop: 6 }}>
        {metric === 'trailing_pe'
          ? 'No positive point-in-time TTM diluted EPS is available for this issuer.'
          : 'No canonical SEC revenue series is available for this issuer.'}
      </div>
    );
  }
  if (metric === 'trailing_pe') {
    const payload = state.data as ValuationSeriesPayload | null;
    const latest = [...(payload?.observations ?? [])].reverse().find((row) => row.value != null);
    if (!latest || latest.value == null) return null;
    const source = latest.sources?.[0];
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 7 }}>
        <div style={{ fontSize: 11, color: '#8fb8e8' }}>
          P/E {new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(latest.value)}×
          {' · '}price {formatFinancialValue(latest.price, 'USD/shares')}
          {' · '}TTM diluted EPS {formatFinancialValue(latest.epsTtmAdjusted ?? latest.epsTtm ?? 0, 'USD/shares')}
          {latest.epsAvailableAt ? ` · known ${formatFinancialDate(latest.epsAvailableAt)}` : ''}
        </div>
        <OverlayMetadata
          count={plotted.length}
          source={source}
          warnings={payload?.warnings ?? []}
        />
      </div>
    );
  }

  const payload = state.data && !('epsMetric' in state.data) ? state.data : null;
  const latest = payload?.observations[payload.observations.length - 1];
  if (!latest) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 7 }}>
      <div style={{ fontSize: 11, color: '#8fb8e8' }}>
        ∿ {payload.frequency.toUpperCase()} revenue · {formatFinancialValue(latest.value, latest.unit)}
        {' · '}period ended {formatFinancialDate(latest.periodEnd)}
        {' · '}known {formatFinancialDate(latest.availableAt)}
        {latest.derived ? ' · derived' : ' · reported'}
      </div>
      <OverlayMetadata
        count={payload.observations.length}
        source={latest.sources?.[0]}
        warnings={payload.warnings}
        confidence={latest.confidence}
      />
    </div>
  );
}

// These flags are the series telling you what it is unsure about, so they are worth
// reading. Raw snake_case names say nothing to anyone who has not read the accounting
// code, and a flag nobody understands is a flag nobody acts on.
const FLAG_NOTES: Record<string, string> = {
  ttm_eps_discontinuity:
    'Trailing EPS moved more than 40% against the prior quarter — the top decile of moves. '
    + 'A P/E can fall because the price dropped OR because earnings jumped, and they look '
    + 'identical here. A one-time gain (a stake marked up, a tax settlement) inflates earnings '
    + 'for exactly four quarters and collapses the ratio without the stock getting any cheaper. '
    + 'Read the filing before treating this multiple as a valuation.',
  stale_eps:
    'The newest usable earnings figure is over 180 days old, so no ratio is drawn rather than '
    + 'dividing today’s price by earnings that may be a year out of date.',
  non_positive_ttm_eps: 'Trailing earnings were zero or negative, so a P/E has no meaning here.',
  eps_ttm_reconstructed:
    'Interim trailing EPS rebuilt as prior full year + this year to date − the same stretch last '
    + 'year. Per-share figures cannot simply be added, so the arithmetic is done in dollars and '
    + 'divided by the share count once at the end.',
  eps_split_adjusted: 'Earnings restated onto today’s share count so they match the price history.',
  diluted_shares_derived_from_net_income:
    'The issuer never tagged a consolidated diluted share count for this period, so it was '
    + 'recovered as net income ÷ diluted EPS. Agrees with the tagged figure to within 0.22% '
    + 'where both exist.',
  derived_q4: 'Fourth quarter derived as the full year minus the three reported quarters.',
  conflicting_filing_values: 'Filings disagreed on this value; the latest amendment was used.',
  multiple_concepts_available: 'More than one accounting tag covered this period.',
  amended_filing: 'Sourced from an amended filing.',
  implausible_annual_residual:
    'The derived fourth quarter came out negative against positive quarters — treat with suspicion.',
  split_history_unverified:
    'Split history could not be confirmed, so earnings and price may sit on different share bases.',
  no_point_in_time_ttm_eps: 'No earnings figure had been filed yet at this date.',
  source_refresh_failed_using_persisted_facts:
    'SEC refresh failed; showing the last successfully stored filings.',
};

const FLAG_TONE: Record<string, string> = {
  ttm_eps_discontinuity: '#d96d5f',
  implausible_annual_residual: '#d96d5f',
  split_history_unverified: '#d96d5f',
  derived_q4: MM.dim,
  multiple_concepts_available: MM.dim,
  eps_split_adjusted: MM.dim,
};

function OverlayMetadata({
  count,
  source,
  warnings,
  confidence,
}: {
  count: number;
  source?: { sourceUrl?: string | null; form: string; accessionNumber: string };
  warnings: string[];
  confidence?: number;
}) {
  return (
    <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', alignItems: 'center', color: MM.dimmer, font: `9.5px ${mono}` }}>
      <span>{new Intl.NumberFormat().format(count)} observations</span>
      {confidence != null && <span>{Math.round(confidence * 100)}% confidence</span>}
      {source?.sourceUrl && (
        <a href={source.sourceUrl} target="_blank" rel="noreferrer" style={{ color: MM.muted }}>
          {source.form} · {source.accessionNumber}
        </a>
      )}
      {warnings.map((warning) => (
        <span
          key={warning}
          title={FLAG_NOTES[warning] ?? 'Series quality flag'}
          style={{ color: FLAG_TONE[warning] ?? '#d9ad67', cursor: 'help' }}
        >
          {warning.replaceAll('_', ' ')}
        </span>
      ))}
    </div>
  );
}
