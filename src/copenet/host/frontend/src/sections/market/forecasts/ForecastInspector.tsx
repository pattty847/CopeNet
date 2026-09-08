import { ForecastSetupVisual } from './ForecastSetupVisual';
import { ForecastAttribution } from './ForecastAttribution';
import { ForecastAmendment } from './ForecastAmendment';
import { ForecastEventEvidence } from './ForecastEventEvidence';
import { useEffect, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import { useAppStore } from '../../../store/useAppStore';
import { ApprovalRequestCard } from '../../../components/ApprovalRequestCard';
import { MonitoringSheet } from '../monitoring/MonitoringSheet';
import { ChartEvidenceViewer } from '../chartAgent/ChartEvidenceViewer';
import { forecastSetup, type ForecastRecord, type ForecastChart } from './types';
import { forecastDate, forecastRisk, forecastStatus, forecastTracking, forecastThesis } from './model';
import type { Scan } from '../monitoring/types';
import '../monitoring/monitoring.css';
import './forecasts.css';

export function ForecastInspector({ forecastId, onClose, onOpen }: { forecastId: string; onClose: () => void; onOpen?: (symbol: string) => void }) {
  const [snapshot, setSnapshot] = useState<{ record: ForecastRecord; chart: ForecastChart | null } | null>(null);
  const record = snapshot?.record ?? null;
  const chart = snapshot?.chart ?? null;
  const setRecord = (next: ForecastRecord) => setSnapshot((previous) => ({ record: next, chart: previous?.chart ?? null }));
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [scans, setScans] = useState<Scan[]>([]);
  const approvals = useAppStore((state) => state.pendingApprovalsById);
  useEffect(() => {
    let alive = true; setSnapshot(null);
    const refresh = () => wsClient.marketForecast.get(forecastId).then(({ forecast, chart: nextChart }) => { if (alive) {
      setSnapshot((previous) => previous && previous.record.forecastId === forecast.forecastId && previous.record.revision > forecast.revision
        ? previous : { record: forecast, chart: nextChart }); setError(''); } })
      .catch((reason) => { if (alive) setError(String(reason)); });
    void refresh();
    const off = wsClient.marketForecast.subscribe(() => void refresh());
    const timer = window.setInterval(() => void refresh(), 2000);
    wsClient.marketMonitoring.scans().then((result) => { if (alive) setScans(result.scans); }).catch(() => undefined);
    return () => { alive = false; off(); window.clearInterval(timer); };
  }, [forecastId]);
  const change = async (action: () => Promise<{ forecast: ForecastRecord }>) => {
    setBusy(true); setError('');
    try { setRecord((await action()).forecast); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not update forecast.'); }
    finally { setBusy(false); }
  };
  const setup = record && forecastSetup(record);
  const evaluation = record?.evaluation;
  const eligible = scans.filter((scan) => scan.enabled && !scan.includeUniverse && !scan.watchlists.length && !scan.interpret && !scan.publishBrief
    && scan.sources.length === 1 && scan.sources[0] === 'prices' && scan.resolvedSymbols.includes(record?.instrument.symbol ?? ''));
  const members = record ? Object.values(record.members) : [];
  return <MonitoringSheet title={record ? `${record.instrument.symbol} · Forecast` : 'Forecast'} onClose={onClose}>
    <div className="mm-monitor-form cf-inspector">
      {error && <p role="alert" className="mm-monitor-error">{error}</p>}
      {!record ? <p role="status">Loading forecast…</p> : <>
        <div className="cf-summary"><strong>{forecastStatus(record)}</strong><span>{forecastRisk(record)} <small>planned-risk R</small></span></div>
        <p>{record.model} · {forecastDate(record.publishedAt ?? record.requestedAt)} · {record.paired ? 'Paired request' : 'Single model run'}</p>
        {!setup && <p>{forecastThesis(record)}</p>}
        {members.map((member) => Object.values(approvals).filter((approval) => approval.sessionKey === member.sessionKey && approval.status === 'pending').map((approval) => <ApprovalRequestCard key={approval.approvalId} approval={approval} />))}
        {(record.status === 'generating' || record.status === 'requested') && <button className="tw-btn" disabled={busy} onClick={() => void change(() => wsClient.marketForecast.cancel(forecastId))}>Cancel unfinished request</button>}
        {record.failureReason && <p role="alert" className="mm-monitor-error">{record.failureReason}</p>}
        {members.flatMap((member) => member.errors).map((message, index) => <p className="mm-monitor-error" key={index}>{message.reason}</p>)}
        {setup && <section><h3>Original setup · {setup.direction}</h3><ForecastSetupVisual setup={setup} chart={chart} /><details><summary>Model thesis</summary><p>{forecastThesis(record)}</p></details><p>Entry expiry: {record.entryExpirySessions} exchange sessions · deadline {forecastDate(record.deadlineAt)}</p>
          {setup.zones.map((zone, index) => <p key={index}>{zone.label} · {zone.lower}–{zone.upper}</p>)}
          <small>Original publication prices; later closes use the same split basis. Gross simulated returns exclude costs.</small>
        </section>}
        <section><h3>Tracking · {forecastTracking(record)}</h3><p>{(evaluation?.health ?? 'unevaluated').replaceAll('_', ' ')}{evaluation?.reason ? ` · ${evaluation.reason}` : ''}</p>
          <label>Price schedule<select className="tw-input" value={record.trackingScanId ?? ''} disabled={busy} onChange={(event) => void change(() => wsClient.marketForecast.tracking(forecastId, event.target.value || null))}>
            <option value="">Paused</option>
            {record.trackingScanId && !eligible.some((scan) => scan.id === record.trackingScanId) && <option value={record.trackingScanId}>Linked schedule unavailable</option>}
            {eligible.map((scan) => <option key={scan.id} value={scan.id}>{scan.name}</option>)}
          </select></label><p>Repair tracking by linking an enabled, focused price-only scan from Monitoring. No new prediction is generated.</p>
        </section>
        <section><h3>Direction at the horizon</h3>{['4w', '8w'].map((horizon) => {
          const score = evaluation?.horizons?.[horizon];
          return <p key={horizon}><strong>{horizon}</strong> · TA {score?.members.ta?.outcome ?? 'pending'}{record.paired ? ` · plain ${score?.members.directional?.outcome ?? 'pending'}` : ''}{score?.priceReturn != null ? ` · ${(score.priceReturn * 100).toFixed(2)}% price return` : ''}</p>;
        })}<small>Direction and trade outcomes are scored independently.</small></section>
        {record.members.directional?.result && <section><h3>Independent directional call</h3><p>{record.members.directional.result.kind === 'directional' ? record.members.directional.result.direction : ''}</p><p>{record.members.directional.result.thesis}</p></section>}
        <section><h3>Evaluation timeline</h3>{!evaluation?.events?.length ? <p>No simulated price events yet.</p> : <ol className="cf-timeline">{evaluation.events.map((event) => <li key={event.eventId}>
          <time>{event.date}</time><strong>{event.type.replaceAll('_', ' ')}</strong><span>{event.price == null ? '' : event.price}{event.fraction == null ? '' : ` · ${Math.round(event.fraction * 100)}%`}</span>{event.reason && <p>{event.reason}</p>}
        </li>)}</ol>}</section>
        <section><h3>Frozen evidence</h3><p>Observation {record.observationId}</p>
          {(setup?.evidence.length ? setup.evidence : [{ observationId: record.observationId, resourceKey: 'candles:D' }]).map((reference, index) =>
            <ChartEvidenceViewer key={index} reference={reference} sessionKey={null} documentId={record.documentId} includeAccountContext={false} />)}
          <details><summary>Evaluation evidence and provenance</summary><pre className="mm-monitor-json">{JSON.stringify({ source: evaluation?.source, events: record.events, provenance: record.provenance }, null, 2)}</pre></details>
        </section>
        {record.events.filter((event) => typeof event.evidenceId === 'string').map((event, index) => <ForecastEventEvidence key={index} forecastId={forecastId} evidenceId={event.evidenceId as string} />)}
        <section><h3>Amendments</h3><p>Original levels and their attributed score remain fixed.</p>{record.amendments.length ? record.amendments.map((amendment, index) => <pre className="mm-monitor-json" key={index}>{JSON.stringify(amendment, null, 2)}</pre>) : <p>No amendments.</p>}<ForecastAmendment record={record} onSaved={setRecord} /></section>
        <ForecastAttribution record={record} />
        <details><summary>Saved and rendered status</summary><pre className="mm-monitor-json">{JSON.stringify(record.renderStatus, null, 2)}</pre></details>
        {onOpen && <button className="tw-btn" onClick={() => { onOpen(record.instrument.symbol); onClose(); }}>Open {record.instrument.symbol} chart</button>}
      </>}
    </div>
  </MonitoringSheet>;
}
