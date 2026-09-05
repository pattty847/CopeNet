import type { ForecastRecord } from './types';

export function ForecastAttribution({ record }: { record: ForecastRecord }) {
  return <section><h3>Model runs</h3>{Object.entries(record.members).map(([lane, member]) => {
    const attribution = member.attribution;
    return <div key={lane} className="cf-attribution">
      <strong>{lane === 'ta' ? 'TA setup' : 'Independent direction'}</strong>
      <p>{attribution.provider ?? record.provider} · {attribution.model ?? record.model}
        {attribution.modelSource === 'run_record' ? ' · run record' : ' · requested model'}</p>
      <p>{attribution.runStatus ?? member.status} · {attribution.readCallCount ?? '—'} chart reads</p>
      {attribution.reportedUsage == null ? <p>Provider token usage unavailable</p> : <pre className="mm-monitor-json">{JSON.stringify(attribution.reportedUsage, null, 2)}</pre>}
      {attribution.messageInputTokenEstimate != null && <p>Message input estimate: {attribution.messageInputTokenEstimate.toLocaleString()} tokens · excludes tool schemas and other request overhead</p>}
      <details><summary>Prompt, evidence and run details</summary><pre className="mm-monitor-json">{JSON.stringify({ sessionKey: member.sessionKey, runId: member.runId, observationId: member.observationId, ...attribution }, null, 2)}</pre></details>
    </div>;
  })}</section>;
}
