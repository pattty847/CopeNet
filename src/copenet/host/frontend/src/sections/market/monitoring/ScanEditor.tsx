import { useState, type FormEvent } from 'react';
import { wsClient } from '../../../lib/wsClient';
import { MonitoringSheet } from './MonitoringSheet';
import { symbolsFromText, timeLabel, toggleValue } from './model';
import type { ScanDefinition, ScanPreview, ScansState } from './types';

export function ScanEditor({
  initial,
  state,
  onClose,
  onSaved,
}: {
  initial: ScanDefinition;
  state: ScansState;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [scan, setScan] = useState(initial);
  const [symbols, setSymbols] = useState(initial.symbols.join(', '));
  const [exclusions, setExclusions] = useState(initial.excludeSymbols.join(', '));
  const [times, setTimes] = useState(initial.times.join(', '));
  const [preview, setPreview] = useState<ScanPreview | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const draft = (): ScanDefinition => ({
    ...scan,
    symbols: symbolsFromText(symbols),
    excludeSymbols: symbolsFromText(exclusions),
    times: times
      .split(',')
      .map((time) => time.trim())
      .filter(Boolean),
  });
  const update = (change: Partial<ScanDefinition>) => {
    setScan({ ...scan, ...change });
    setPreview(null);
  };
  const review = async () => {
    setBusy('preview');
    setError('');
    try {
      setPreview(await wsClient.marketMonitoring.previewScan(draft()));
    } catch (reason) {
      setError(String(reason instanceof Error ? reason.message : reason));
    } finally {
      setBusy('');
    }
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy('save');
    setError('');
    try {
      await wsClient.marketMonitoring.saveScan(draft());
      await onSaved();
      onClose();
    } catch (reason) {
      setError(String(reason instanceof Error ? reason.message : reason));
    } finally {
      setBusy('');
    }
  };
  return (
    <MonitoringSheet title={initial.id ? 'Edit scan' : 'New scan'} onClose={onClose}>
      <form className="mm-monitor-form" onSubmit={(event) => void save(event)}>
        <label>
          Name
          <input
            className="tw-input"
            required
            autoFocus
            value={scan.name}
            onChange={(event) => update({ name: event.target.value })}
            placeholder="e.g. Core holdings"
          />
        </label>
        <fieldset>
          <legend>Assets</legend>
          <label className="mm-check">
            <input type="checkbox" checked={scan.includeUniverse} onChange={(event) => update({ includeUniverse: event.target.checked })} />{' '}
            Include the Market universe
          </label>
          <div className="mm-monitor-choices">
            {state.watchlists.map((list) => (
              <label className="mm-check" key={list.name}>
                <input
                  type="checkbox"
                  checked={scan.watchlists.includes(list.name)}
                  onChange={() => update({ watchlists: toggleValue(scan.watchlists, list.name) })}
                />
                {list.name}
                <span>{list.symbols.length}</span>
              </label>
            ))}
          </div>
          <label>
            Add symbols
            <textarea
              className="tw-input"
              value={symbols}
              onChange={(event) => {
                setSymbols(event.target.value);
                setPreview(null);
              }}
              placeholder="AAPL, MSFT, SPY"
              rows={2}
            />
          </label>
          <label>
            Exclude symbols
            <input
              className="tw-input"
              value={exclusions}
              onChange={(event) => {
                setExclusions(event.target.value);
                setPreview(null);
              }}
              placeholder="Excluded from every selected list"
            />
          </label>
          <p>Watchlists stay linked. Exclusions win; shared symbols are fetched once.</p>
        </fieldset>
        <fieldset>
          <legend>Sources</legend>
          <div className="mm-monitor-choices">
            {state.sources.map((source) => (
              <label className="mm-check" key={source.id} title={source.scope}>
                <input
                  type="checkbox"
                  checked={scan.sources.includes(source.id)}
                  onChange={() => update({ sources: toggleValue(scan.sources, source.id) })}
                />
                {source.label}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend>Schedule</legend>
          <div className="mm-monitor-fields">
            <label>
              Times · 24-hour
              <input
                className="tw-input"
                required
                value={times}
                onChange={(event) => {
                  setTimes(event.target.value);
                  setPreview(null);
                }}
                placeholder="09:45, 16:30"
              />
            </label>
            <label>
              Timezone
              <input
                className="tw-input"
                required
                value={scan.timezone}
                onChange={(event) => update({ timezone: event.target.value })}
                list="market-timezones"
              />
              <datalist id="market-timezones">
                <option value="America/New_York" />
                <option value="America/Chicago" />
                <option value="America/Los_Angeles" />
                <option value="UTC" />
              </datalist>
            </label>
          </div>
          <div className="mm-monitor-days" role="group" aria-label="Run days">
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day, index) => (
              <button
                key={day}
                className="tw-btn"
                type="button"
                aria-pressed={scan.days.includes(index)}
                data-active={scan.days.includes(index)}
                onClick={() => update({ days: toggleValue(scan.days, index) })}
              >
                {day}
              </button>
            ))}
          </div>
          <label className="mm-check">
            <input type="checkbox" checked={scan.enabled} onChange={(event) => update({ enabled: event.target.checked })} /> Schedule
            enabled
          </label>
          <p>Missed times are skipped. Starting the server never catches up a scan.</p>
        </fieldset>
        {scan.id === 'morning' && (
          <fieldset>
            <legend>Output</legend>
            <label className="mm-check">
              <input type="checkbox" checked={scan.publishBrief} onChange={(event) => update({ publishBrief: event.target.checked })} />{' '}
              Publish the broad-market briefing
            </label>
            <label className="mm-check">
              <input type="checkbox" checked={scan.interpret} onChange={(event) => update({ interpret: event.target.checked })} /> Include a
              model read
            </label>
            <p>Scoped scans keep their own results and do not replace the Market dashboard.</p>
          </fieldset>
        )}
        <button type="button" className="tw-btn" onClick={() => void review()} disabled={!!busy}>
          {busy === 'preview' ? 'Resolving…' : 'Preview exact scope & cache work'}
        </button>
        {preview && <ScanScope preview={preview} />}
        {error && (
          <p role="alert" className="mm-monitor-error">
            {error}
          </p>
        )}
        <footer>
          {initial.id && initial.id !== 'morning' && (
            <button
              type="button"
              className="tw-btn"
              disabled={!!busy}
              onClick={() => {
                if (!window.confirm(`Archive ${initial.name}? Linked alerts will stop evaluating.`)) return;
                setBusy('archive');
                setError('');
                void wsClient.marketMonitoring
                  .archiveScan(initial.id)
                  .then(onSaved)
                  .then(onClose)
                  .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)))
                  .finally(() => setBusy(''));
              }}
            >
              Archive scan
            </button>
          )}
          <button type="button" className="tw-btn" onClick={onClose}>
            Cancel
          </button>
          <button className="tw-btn" data-active disabled={!!busy}>
            {busy === 'save' ? 'Saving…' : 'Save scan'}
          </button>
        </footer>
      </form>
    </MonitoringSheet>
  );
}

export function ScanScope({ preview }: { preview: ScanPreview }) {
  return (
    <div className="mm-monitor-scope">
      <div className="mm-monitor-metrics">
        <span>
          <b>{preview.resolvedSymbols.length}</b> assets
        </span>
        <span>
          <b>{preview.cacheHits}</b> cached
        </span>
        <span>
          <b>{preview.work.filter((item) => item.status !== 'cached').length}</b> source jobs
        </span>
      </div>
      <p>Source jobs may require multiple HTTP requests; initial price history is the largest fetch.</p>
      <p>Next scheduled occurrence: {timeLabel(preview.nextRunAt)}</p>
      {preview.issues.map((issue) => (
        <p key={issue} className="mm-monitor-error">
          {issue}
        </p>
      ))}
      {preview.notes?.map((note) => (
        <p key={note}>{note}</p>
      ))}
      {preview.contextSymbols.length > 0 && <p>Context: {preview.contextSymbols.join(', ')}</p>}
      <details>
        <summary>Why each asset is included</summary>
        {preview.inclusions.map((item) => (
          <div className="mm-monitor-evidence" key={item.symbol}>
            <b>{item.symbol}</b>
            <span>{item.reasons.join(' · ')}</span>
          </div>
        ))}
      </details>
      <details>
        <summary>Source work · {preview.work.length} items</summary>
        {preview.work.map((item, index) => (
          <div className="mm-monitor-evidence" key={`${item.source}-${item.symbol}-${index}`}>
            <b>{item.symbol || 'Global'}</b>
            <span>
              {item.source} · {item.status}
            </span>
          </div>
        ))}
      </details>
    </div>
  );
}
