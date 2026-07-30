import type { FinancialFrequency } from './types';
import type { FinancialSeriesState } from './useFinancialSeries';
import { formatFinancialDate, formatFinancialValue } from './financialOverlay';
import { MM, mono } from './marketUi';

const FREQUENCIES: Array<{ value: FinancialFrequency; label: string }> = [
  { value: 'quarterly', label: 'Quarter' },
  { value: 'ttm', label: 'TTM' },
  { value: 'annual', label: 'Annual' },
];

export function FinancialOverlayControls({
  visible,
  frequency,
  loading,
  onToggle,
  onFrequency,
}: {
  visible: boolean;
  frequency: FinancialFrequency;
  loading: boolean;
  onToggle: () => void;
  onFrequency: (frequency: FinancialFrequency) => void;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <button
        onClick={onToggle}
        aria-pressed={visible}
        title="Plot SEC revenue from the date each filing became public"
        style={{
          cursor: 'pointer',
          border: `1px solid ${visible ? 'rgba(90,143,199,.45)' : MM.border}`,
          background: visible ? 'rgba(90,143,199,.12)' : 'transparent',
          color: visible ? '#8fb8e8' : MM.muted,
          borderRadius: 8,
          padding: '5px 10px',
          font: '600 9.5px Inter',
          letterSpacing: '.06em',
          textTransform: 'uppercase',
          whiteSpace: 'nowrap',
        }}
      >
        {loading ? '◍ Revenue' : '∿ Revenue'}
      </button>
      {visible && (
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
  visible,
  state,
}: {
  visible: boolean;
  state: FinancialSeriesState;
}) {
  if (!visible) return null;
  if (state.loading) {
    return <div style={{ fontSize: 11, color: MM.dim, marginTop: 6 }}>Loading normalized SEC history…</div>;
  }
  if (state.error) {
    return <div role="alert" style={{ fontSize: 11, color: MM.down, marginTop: 6 }}>Revenue series failed: {state.error}</div>;
  }
  const observations = state.data?.observations ?? [];
  if (state.loaded && !observations.length) {
    return <div style={{ fontSize: 11, color: MM.dim, marginTop: 6 }}>No canonical SEC revenue series is available for this issuer.</div>;
  }
  const latest = observations[observations.length - 1];
  if (!latest) return null;
  const source = latest.sources?.[0];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 7 }}>
      <div style={{ fontSize: 11, color: '#8fb8e8' }}>
        ∿ {state.data?.frequency.toUpperCase()} revenue · {formatFinancialValue(latest.value, latest.unit)}
        {' · '}period ended {formatFinancialDate(latest.periodEnd)}
        {' · '}known {formatFinancialDate(latest.availableAt)}
        {latest.derived ? ' · derived' : ' · reported'}
      </div>
      <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', alignItems: 'center', color: MM.dimmer, font: `9.5px ${mono}` }}>
        <span>{observations.length} observations</span>
        <span>{Math.round(latest.confidence * 100)}% confidence</span>
        {source?.sourceUrl && (
          <a href={source.sourceUrl} target="_blank" rel="noreferrer" style={{ color: MM.muted }}>
            {source.form} · {source.accessionNumber}
          </a>
        )}
        {(state.data?.warnings ?? []).map((warning) => (
          <span key={warning} title="Series quality flag" style={{ color: warning === 'derived_q4' ? MM.dim : '#d9ad67' }}>
            {warning.replaceAll('_', ' ')}
          </span>
        ))}
      </div>
    </div>
  );
}
