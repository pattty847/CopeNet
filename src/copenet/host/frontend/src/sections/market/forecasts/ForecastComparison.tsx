import { useEffect, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import type { LedgerReport } from '../types';
import type { ForecastRecord, ForecastReport } from './types';

const percent = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toFixed(1)}%`;
export function ForecastComparison({ report: initial, historical, records }: { report?: ForecastReport; historical: LedgerReport | null; records: ForecastRecord[] }) {
  const [provider, setProvider] = useState('');
  const [model, setModel] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [filtered, setFiltered] = useState<ForecastReport | undefined>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const hasFilters = Boolean(provider || model || from || to);
  const revision = records.map((record) => `${record.forecastId}:${record.revision}`).join('|');
  useEffect(() => {
    let alive = true; setLoading(true); setError(''); setFiltered(undefined);
    wsClient.marketForecast.report({ forecastProvider: provider || undefined, forecastModel: model || undefined,
      forecastFrom: from || undefined, forecastTo: to || undefined }).then((result) => { if (alive) setFiltered(result.forecasts); })
      .catch((reason) => { if (alive) setError(String(reason)); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [provider, model, from, to, revision]);
  const report = hasFilters ? filtered : filtered ?? initial;
  const providers = initial?.cohorts?.providers ?? [...new Set(records.map((record) => record.provider))];
  const models = initial?.cohorts?.models ?? [...new Set(records.filter((record) => !provider || record.provider === provider).map((record) => record.model))];
  const filters = <div className="cf-filters">
    <label>Provider<select className="tw-input" value={provider} onChange={(event) => { setProvider(event.target.value); setModel(''); }}><option value="">All providers</option>{providers.map((value) => <option key={value}>{value}</option>)}</select></label>
    <label>Model<select className="tw-input" value={model} onChange={(event) => setModel(event.target.value)}><option value="">All models</option>{models.map((value) => <option key={value}>{value}</option>)}</select></label>
    <label>From<input className="tw-input" type="date" value={from} onChange={(event) => setFrom(event.target.value)} /></label>
    <label>Through<input className="tw-input" type="date" value={to} min={from} onChange={(event) => setTo(event.target.value)} /></label>
  </div>;

  if (!report) return <div className="cf-comparison">{filters}{error ? <p role="alert">{error}</p> : <p role="status">{loading ? 'Loading comparison…' : 'Forecast comparisons will appear after a manual request is registered.'}</p>}</div>;
  return <div className="cf-comparison">{filters}
    {error && <p role="alert">{error} · showing the last available comparison</p>}
    {loading && <p role="status">Updating comparison…</p>}
    <p>{report.attemptCount} attempts · {report.setupCount} setups · policy {report.policyVersion}</p>
    <h3>Direction · historical context</h3>
    <table><thead><tr><th>Horizon</th><th>Chart TA</th><th>Existing ticker calls</th></tr></thead><tbody>{['4w', '8w'].map((horizon) => {
      const direction = report.direction[horizon]; const old = historical?.stats.lean[horizon];
      return <tr key={horizon}><th>{horizon}</th><td>{percent(direction.accuracy)} · n={direction.scoredCount}</td><td>{old?.accuracyPct == null ? '—' : `${old.accuracyPct.toFixed(1)}%`} · n={old ? old.correct + old.incorrect : 0}</td></tr>;
    })}</tbody></table>
    <p>Chart filters apply only to the chart cohort; existing ticker calls retain their full historical cohort. Different tickers, dates, evidence and scoring rules. This historical comparison cannot establish that TA improved forecasting.</p>
    <h3>Paired calls · same captured evidence</h3>
    <table><thead><tr><th>Outcome</th><th>4w</th><th>8w</th></tr></thead><tbody>
      {([['bothCorrect', 'Both correct'], ['taOnlyCorrect', 'TA only correct'], ['plainOnlyCorrect', 'Plain only correct'], ['bothIncorrect', 'Both incorrect'], ['excluded', 'Unresolved / excluded']] as const).map(([key, label]) => <tr key={key}><th>{label}</th><td>{report.paired['4w'].counts[key] ?? 0}</td><td>{report.paired['8w'].counts[key] ?? 0}</td></tr>)}
      <tr><th>TA accuracy difference</th>{['4w', '8w'].map((horizon) => <td key={horizon}>{report.paired[horizon].correctnessDelta == null ? '—' : `${(report.paired[horizon].correctnessDelta! * 100).toFixed(1)} pp`}</td>)}</tr>
    </tbody></table>
    {['4w', '8w'].map((horizon) => <p key={horizon}>{horizon}: {report.paired[horizon].pairedCount} eligible pairs · {report.paired[horizon].distinctTickers} tickers · {report.paired[horizon].distinctPublicationDates} publication dates</p>)}
    <p>Repeated calls on a ticker can be correlated. Abstentions, neutral calls, incomplete pairs and pending outcomes remain outside scored pairs.</p>
    <h3>Trade planning</h3>
    <p>Entry activation {percent(report.trade.activationRate)} · {report.trade.activatedCount} activated</p>
    <p>Mean planned-risk R {report.trade.meanPlannedRiskR == null ? '—' : `${report.trade.meanPlannedRiskR.toFixed(2)}R`} · {report.trade.scoredCount} scored trades</p>
    <p>{Object.entries(report.states).map(([state, count]) => `${state.replaceAll('_', ' ')} ${count}`).join(' · ')}</p>
    <p>{report.methodology}</p>
  </div>;
}
