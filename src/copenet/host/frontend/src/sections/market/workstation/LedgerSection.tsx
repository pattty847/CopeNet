import { useState } from 'react';
import { ForwardLedger } from '../ForwardLedger';
import { SectionHeader } from './SectionGrid';
import type { LedgerReport } from '../types';
import { useForecasts } from '../forecasts/useForecasts';
import { ForecastList } from '../forecasts/ForecastList';
import { ForecastInspector } from '../forecasts/ForecastInspector';
import { ForecastComparison } from '../forecasts/ForecastComparison';
import '../forecasts/forecasts.css';

export function LedgerSection({ report, loading, onOpen }: { report: LedgerReport | null; loading: boolean; onOpen: (symbol: string) => void }) {
  const [tab, setTab] = useState<'calls' | 'forecasts' | 'comparison'>('calls');
  const [selected, setSelected] = useState<string | null>(null);
  const forecasts = useForecasts();
  const meta = report ? `${report.totalClaims} claims · ${report.pendingHorizons} horizons pending · rules ${report.rulesVersion}` : loading ? 'loading…' : 'no claims yet';
  return <>
    <SectionHeader label="Ledger" meta={meta} />
    <div className="cf-tabs" role="tablist" aria-label="Ledger views">
      {([['calls', 'Calls'], ['forecasts', 'Chart forecasts'], ['comparison', 'Comparison']] as const).map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>)}
    </div>
    <div role="tabpanel">
      {tab === 'calls' ? <ForwardLedger report={report} loading={loading} onOpen={onOpen} /> : tab === 'comparison' ? <ForecastComparison records={forecasts.records} report={report?.forecasts} historical={report} /> : <>
        {forecasts.error && <p role="alert" className="cf-empty">{forecasts.error} <button className="tw-btn" onClick={() => void forecasts.refresh()}>Retry</button></p>}
        {forecasts.loading ? <p role="status" className="cf-empty">Loading forecasts…</p> : <ForecastList records={forecasts.records} onSelect={setSelected} />}
        {forecasts.nextOffset != null && <button className="tw-btn" onClick={forecasts.loadMore}>Load more forecasts</button>}
      </>}
    </div>
    {selected && <ForecastInspector forecastId={selected} onClose={() => setSelected(null)} onOpen={onOpen} />}
  </>;
}
