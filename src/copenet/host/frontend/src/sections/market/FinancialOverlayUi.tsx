import type { FinancialFrequency, FinancialMetricInfo, ValuationSeriesPayload } from './types';
import { isValuationPayload } from './types';
import type { FinancialSeriesState } from './useFinancialSeries';
import { formatFinancialDate, formatFinancialValue } from './financialOverlay';
import { MM, mono } from './marketUi';
import { FinancialMetricPicker } from './FinancialMetricPicker';

export type OverlayMetric = string;

// The two flagship series keep one-click buttons; everything else the registry
// serves lives in the dropdown so new backend metrics appear with zero UI edits.
const FLAGSHIP_METRICS: OverlayMetric[] = ['revenue', 'trailing_pe'];

const FREQUENCIES: Array<{ value: FinancialFrequency; label: string }> = [
  { value: 'quarterly', label: 'Quarter' },
  { value: 'ttm', label: 'TTM' },
  { value: 'annual', label: 'Annual' },
];

const SHORT_LABELS: Record<string, string> = {
  trailing_pe: 'P/E',
  trailing_ps: 'P/S',
  trailing_pfcf: 'P/FCF',
  trailing_pb: 'P/B',
  fcf_yield: 'FCF yield',
  ev_s: 'EV/S',
  ev_ebitda: 'EV/EBITDA',
  roic: 'ROIC',
};

function shortLabel(metric: FinancialMetricInfo): string {
  return SHORT_LABELS[metric.id] ?? metric.label;
}

export function FinancialOverlayControls({
  metrics,
  metric,
  frequency,
  loading,
  onMetric,
  onFrequency,
}: {
  metrics: FinancialMetricInfo[];
  metric: OverlayMetric | null;
  frequency: FinancialFrequency;
  loading: boolean;
  onMetric: (metric: OverlayMetric | null) => void;
  onFrequency: (frequency: FinancialFrequency) => void;
}) {
  const byId = new Map(metrics.map((entry) => [entry.id, entry]));
  const flagship = FLAGSHIP_METRICS.map((id) => byId.get(id)).filter(
    (entry): entry is FinancialMetricInfo => entry != null,
  );
  const rest = metrics.filter((entry) => !FLAGSHIP_METRICS.includes(entry.id));
  const selected = metric ? byId.get(metric) ?? null : null;
  const valuationSelected = selected?.factType === 'valuation';

  const button = (entry: FinancialMetricInfo) => {
    const active = metric === entry.id;
    return (
      <button
        key={entry.id}
        onClick={() => onMetric(active ? null : entry.id)}
        aria-pressed={active}
        title={
          entry.id === 'revenue'
            ? 'Plot canonical SEC revenue from the date each filing became public'
            : entry.id === 'trailing_pe'
              ? 'Plot split-adjusted price divided by then-known TTM diluted EPS'
              : entry.label
        }
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
        {loading && active ? '◍ ' : entry.id === 'revenue' ? '∿ ' : ''}{shortLabel(entry)}
      </button>
    );
  };

  const restActive = metric != null && !FLAGSHIP_METRICS.includes(metric);
  return (
    <div className="market-financial-controls" style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <div
        className="market-financial-controls__metrics"
        aria-label="Financial chart overlay"
        style={{ display: 'flex', gap: 3, alignItems: 'center', background: '#050506', border: `1px solid ${MM.border}`, borderRadius: 9, padding: 3 }}
      >
        {flagship.map(button)}
        {rest.length > 0 && (
          <FinancialMetricPicker
            metrics={rest}
            selectedMetric={restActive ? metric : null}
            selectedLabel={restActive && selected ? shortLabel(selected) : null}
            loading={loading}
            onMetric={onMetric}
          />
        )}
      </div>
      {metric != null && !valuationSelected && (
        <div className="market-financial-controls__frequency" style={{ display: 'flex', gap: 2, background: '#050506', border: `1px solid ${MM.border}`, borderRadius: 7, padding: 2 }}>
          {FREQUENCIES.filter(
            (option) => !selected?.frequencies || selected.frequencies.includes(option.value),
          ).map((option) => (
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
  metrics,
  metric,
  state,
}: {
  metrics: FinancialMetricInfo[];
  metric: OverlayMetric | null;
  state: FinancialSeriesState;
}) {
  if (!metric) return null;
  const info = metrics.find((entry) => entry.id === metric) ?? null;
  const valuation = info?.factType === 'valuation';
  const label = info ? shortLabel(info) : metric;
  if (state.loading) {
    return <div style={{ fontSize: 11, color: MM.dim, marginTop: 6 }}>Loading {valuation ? 'point-in-time valuation' : 'normalized SEC history'}…</div>;
  }
  if (state.error) {
    return <div role="alert" style={{ fontSize: 11, color: MM.down, marginTop: 6 }}>{label} series failed: {state.error}</div>;
  }
  const observations = state.data?.observations ?? [];
  const plotted = observations.filter((observation) => observation.value != null);
  if (state.loaded && !plotted.length) {
    return (
      <div style={{ fontSize: 11, color: MM.dim, marginTop: 6 }}>
        {valuation
          ? `No positive point-in-time trailing fundamentals are available to draw ${label} for this issuer.`
          : `No canonical SEC ${label.toLowerCase()} series is available for this issuer.`}
      </div>
    );
  }
  if (state.data && isValuationPayload(state.data)) {
    const payload = state.data as ValuationSeriesPayload;
    const latest = [...(payload.observations ?? [])].reverse().find((row) => row.value != null);
    if (!latest || latest.value == null) return null;
    const source = latest.sources?.[0];
    const multiple = payload.inverted
      ? `${(latest.value * 100).toFixed(1)}%`
      : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(latest.value)}×`;
    const detail = latest.epsAvailableAt != null || latest.epsTtm != null
      ? (
        <>
          {' · '}TTM diluted EPS {formatFinancialValue(latest.epsTtmAdjusted ?? latest.epsTtm ?? 0, 'USD/shares')}
          {latest.epsAvailableAt ? ` · known ${formatFinancialDate(latest.epsAvailableAt)}` : ''}
        </>
      )
      : (
        <>
          {latest.denominatorTtm != null
            ? <>{' · '}TTM {payload.denominatorMetric ?? 'denominator'} {formatFinancialValue(latest.denominatorTtm, 'USD')}</>
            : null}
          {latest.sharesOutstanding != null
            ? <>{' · '}{formatFinancialValue(latest.sharesOutstanding, 'shares')}</>
            : null}
          {latest.denominatorAvailableAt ? ` · known ${formatFinancialDate(latest.denominatorAvailableAt)}` : ''}
        </>
      );
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 7 }}>
        <div style={{ fontSize: 11, color: '#8fb8e8' }}>
          {label} {multiple}
          {' · '}price {formatFinancialValue(latest.price, 'USD/shares')}
          {detail}
        </div>
        <OverlayMetadata
          count={plotted.length}
          source={source}
          warnings={payload.warnings ?? []}
        />
      </div>
    );
  }

  const payload = state.data && !isValuationPayload(state.data) ? state.data : null;
  const latest = payload?.observations[payload.observations.length - 1];
  if (!payload || !latest) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 7 }}>
      <div style={{ fontSize: 11, color: '#8fb8e8' }}>
        ∿ {payload.frequency.toUpperCase()} {payload.label.toLowerCase()} · {formatFinancialValue(latest.value, latest.unit)}
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
  gross_profit_derived_from_cost_of_revenue:
    'The issuer does not tag gross profit directly, so it was derived as revenue minus the '
    + 'tagged cost of revenue.',
  ttm_unavailable_for_weighted_average_component:
    'Per-share components are weighted averages that cannot be summed across quarters, so no '
    + 'TTM view exists for this metric yet.',
  derived_from_ytd:
    'Cash-flow statements report Q2/Q3 only as cumulative year-to-date figures, so this '
    + 'standalone quarter was derived by subtracting the preceding cumulative window.',
  implausible_ytd_residual:
    'Differencing the cumulative windows produced a negative quarter against positive '
    + 'cumulatives — treat with suspicion.',
  stale_fundamentals:
    'At least one required SEC input behind this multiple is over 180 days old, so no ratio is drawn.',
  non_positive_ttm_denominator:
    'Trailing revenue or cash flow was zero or negative, so this multiple has no meaning here.',
  no_point_in_time_ttm_denominator:
    'No trailing-twelve-month figure had been filed yet at this date.',
  no_point_in_time_share_count: 'No share count had been filed yet at this date.',
  no_point_in_time_adjustment:
    'No balance-sheet adjustment (net debt) had been filed yet at this date, so no '
    + 'enterprise value can be built.',
  non_positive_enterprise_value:
    'Net cash exceeds the market cap, making enterprise value non-positive — the ratio has '
    + 'no meaning here.',
  point_in_time_shares_outstanding:
    'Share count taken from the filing cover page — an actual point-in-time count, not a '
    + 'weighted average.',
  debt_concepts_missing_assumed_zero:
    'No standard debt tags were found on this balance sheet. That usually means a debt-free '
    + 'issuer, but nonstandard tagging looks identical — net debt here is minus cash.',
  ttm_not_applicable_for_instant_metric:
    'Balance-sheet values are measured at one date; a trailing-twelve-month view of one '
    + 'does not exist.',
  single_period_invested_capital:
    'No beginning-of-window balance existed, so invested capital is the ending balance '
    + 'alone instead of the usual beginning/ending average.',
  effective_tax_rate_clamped:
    'The implied effective tax rate fell outside 0–100% (a large tax benefit or one-time '
    + 'item) and was clamped for the NOPAT calculation.',
  roic_windows_skipped_non_positive_pretax:
    'Windows with zero or negative pre-tax income were skipped — an effective tax rate '
    + 'has no meaning there.',
  roic_available_only_as_ttm: 'ROIC is defined here on trailing-twelve-month flows only.',
  non_positive_invested_capital:
    'Invested capital was zero or negative (heavy buybacks can do this), so the ratio '
    + 'is not drawn.',
  cost_of_services_may_not_equal_total_cost_of_revenue:
    'Only the issuer’s cost-of-services tag was available. A business that also sells goods may have additional costs not captured here.',
  depreciation_only_may_understate_dep_amort:
    'Only depreciation was tagged; intangible amortization may be omitted, which can understate EBITDA.',
  net_interest_used_for_interest_expense:
    'Net interest income/expense was used because gross interest expense was unavailable. Interest coverage may therefore be overstated.',
  equity_includes_noncontrolling_interest:
    'The available equity tag includes noncontrolling interests, so P/B and invested capital are not strictly parent-common measures.',
  cash_includes_restricted_cash:
    'The available cash tag includes restricted cash, which may understate net debt relative to freely available cash.',
  payables_include_accrued_liabilities:
    'The available fallback combines accounts payable with accrued liabilities and is broader than payables alone.',
  non_positive_share_count: 'The selected share count was zero or negative, so no valuation can be calculated.',
};

const FLAG_TONE: Record<string, string> = {
  ttm_eps_discontinuity: '#d96d5f',
  implausible_annual_residual: '#d96d5f',
  split_history_unverified: '#d96d5f',
  derived_q4: MM.dim,
  multiple_concepts_available: MM.dim,
  eps_split_adjusted: MM.dim,
  gross_profit_derived_from_cost_of_revenue: MM.dim,
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
