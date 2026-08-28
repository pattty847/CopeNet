import { formatFinancialDate, formatFinancialValue } from './financialOverlay';
import type { FinancialSeriesPayload } from './types';
import { useFinancialSeries, type FinancialSeriesState } from './useFinancialSeries';

export function TickerFundamentalsPanel({ symbol, active }: { symbol: string; active: boolean }) {
  const revenue = useFinancialSeries(symbol, 'revenue', 'quarterly', active);
  const dilutedEps = useFinancialSeries(symbol, 'diluted_eps', 'quarterly', active);

  return (
    <section className="ticker-fundamentals-panel" aria-label="Point-in-time fundamentals">
      <header className="ticker-embedded-panel-header">
        <div><h3>Point-in-time fundamentals</h3><p>Canonical SEC series appear when they became public, never at the earlier period end.</p></div>
      </header>
      <div className="ticker-fundamentals-grid">
        <FinancialSeriesTable title="Quarterly revenue" state={revenue} />
        <FinancialSeriesTable title="Quarterly diluted EPS" state={dilutedEps} />
      </div>
    </section>
  );
}

function FinancialSeriesTable({ title, state }: { title: string; state: FinancialSeriesState }) {
  if (state.loading) return <section className="ticker-fundamental-series"><h3>{title}</h3><p className="ticker-panel-note">Loading canonical SEC history…</p></section>;
  if (state.error) return <section className="ticker-fundamental-series"><h3>{title}</h3><p className="ticker-panel-error" role="alert">{state.error}</p></section>;
  const payload = state.data?.kind === 'financial' ? state.data as FinancialSeriesPayload : null;
  const rows = payload?.observations.slice(-6).reverse() ?? [];
  if (state.loaded && !rows.length) return <section className="ticker-fundamental-series"><h3>{title}</h3><p className="ticker-panel-note">No canonical SEC series is available for this issuer.</p></section>;
  if (!payload) return <section className="ticker-fundamental-series"><h3>{title}</h3><p className="ticker-panel-note">Open this view to load the filing history.</p></section>;

  return (
    <section className="ticker-fundamental-series">
      <h3>{title}</h3>
      <div className="ticker-fundamental-table" role="table" aria-label={title}>
        {rows.map((row) => {
          const source = row.sources[0];
          return (
            <div key={`${row.availableAt}:${row.periodEnd}`} className="ticker-fundamental-row" role="row">
              <span role="cell"><strong>{formatFinancialValue(row.value, row.unit)}</strong><small>{row.fiscalPeriod ?? formatFinancialDate(row.periodEnd)}{row.derived ? ' · derived' : ' · reported'}</small></span>
              <span role="cell"><small>Known</small><strong>{formatFinancialDate(row.availableAt)}</strong></span>
              <span role="cell"><small>Source</small>{source?.sourceUrl ? <a href={source.sourceUrl} target="_blank" rel="noopener noreferrer">{source.form}</a> : <strong>{source?.form ?? 'SEC fact'}</strong>}</span>
            </div>
          );
        })}
      </div>
      <p className="ticker-fundamental-provenance">{payload.observations.length.toLocaleString()} observations · availability-aligned · {payload.basis} basis</p>
      {payload.warnings.map((warning) => <p key={warning} className="ticker-panel-warning">{warning}</p>)}
    </section>
  );
}
