import { useState } from 'react';
import { useScreeners } from './useScreeners';
import { wsClient } from '../../../lib/wsClient';
import { CandidateTable } from './CandidateTable';
import { ScreenerUniverse } from './ScreenerUniverse';
import { compactMoney, downloadJson, loadSelection, saveSelection, loadPreset, savePreset } from './model';
import type { ScreenerPreview, ScreenerRun } from './types';
import './screeners.css';

const api = wsClient.marketScreeners;
export function ScreenersSection({
  onOpen,
  onHandoff,
}: {
  onOpen: (symbol: string) => void;
  onHandoff: (name: string) => Promise<void>;
}) {
  const { state, setState, config, setConfig, busy, error, setError, notice, setNotice, reload, act } = useScreeners();
  const [editingUniverse, setEditingUniverse] = useState(false);
  const [preview, setPreview] = useState<ScreenerPreview | null>(null);
  const [active, setActive] = useState(loadPreset);
  const [historical, setHistorical] = useState<ScreenerRun | null>(null);
  const [selection, setSelectionState] = useState(loadSelection);
  const setSelection = (value: { runId: string; symbols: string[] }) => {
    setSelectionState(value);
    saveSelection(value);
  };
  const [name, setName] = useState('');
  const run = historical ?? state?.latest;
  const presets = run?.presets ?? state?.presets ?? [];
  const preset = presets.find((item) => item.id === active) ?? presets[0];
  const screen = run?.screens.find((item) => item.id === preset?.id);
  const selected = new Set(selection.runId === run?.id ? selection.symbols : []);
  const changePreset = (identifier: string) => {
    setActive(identifier);
    savePreset(identifier);
    const url = new URL(window.location.href);
    url.searchParams.set('screen', identifier);
    window.history.replaceState({}, '', url);
  };
  const latestFailure = state?.history[0]?.status === 'error' ? state.history[0].error : null;
  const running = state?.running ?? false;
  const configChanged = run && JSON.stringify(config) !== JSON.stringify(run.config);
  return (
    <div className="scr">
      <header className="scr-heading">
        <div>
          <h2>Screeners</h2>
          <p>Find liquid names. Inspect the setup. Build a research list.</p>
        </div>
        <div className="scr-source">
          <b>TradingView</b>
          <span>
            {running
              ? 'Screen in progress'
              : run
                ? `Observed ${new Date(run.finishedAt).toLocaleString()}`
                : 'No saved observation'}
          </span>
          <small>Quotes may be delayed · daily bars may be unfinished</small>
        </div>
      </header>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void act(async () => setPreview(await api.preview(config)));
        }}
      >
        {(!run || editingUniverse) && (
          <ScreenerUniverse
            config={config}
            disabled={busy || running || !state}
            onChange={(next) => {
              setConfig(next);
              setPreview(null);
            }}
          />
        )}
        <div className="scr-run-controls">
          {run && (
            <button
              type="button"
              className="tw-btn"
              aria-expanded={editingUniverse}
              onClick={() => setEditingUniverse(!editingUniverse)}
            >
              {editingUniverse ? 'Hide universe' : 'Edit universe'}
            </button>
          )}
          <button className="tw-btn" type="submit" disabled={busy || running || !state}>
            {running ? 'Screen in progress…' : 'Review & run all five'}
          </button>
          <span>
            {configChanged
              ? 'Universe changed · results still show the saved run.'
              : 'Manual runs only. No model calls.'}
          </span>
        </div>
      </form>
      {preview && (
        <section className="scr-preview" aria-label="Review screener scope">
          <h3>Run these five screens</h3>
          <p>
            {preview.scope} Up to {preview.maxRows.toLocaleString()} returned instruments.
          </p>
          <p>
            Market cap {compactMoney(preview.config.minCap)}–
            {preview.config.maxCap == null ? 'no ceiling' : compactMoney(preview.config.maxCap)} · Price ≥ $
            {preview.config.minPrice} · Liquidity ≈ ≥ {compactMoney(preview.config.minDollarVolume)}
          </p>
          <ul>
            {preview.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <div>
            <button
              className="tw-btn"
              disabled={busy || running}
              onClick={() =>
                void act(async () => {
                  await api.run(preview.config, preview.scopeToken);
                  setPreview(null);
                  setHistorical(null);
                  setState((current) => (current ? { ...current, running: true } : current));
                  await reload();
                })
              }
            >
              Run screeners
            </button>
            <button className="tw-btn" disabled={busy} onClick={() => setPreview(null)}>
              Cancel
            </button>
          </div>
        </section>
      )}
      {(error || latestFailure) && (
        <div className="scr-error" role="alert">
          {error || latestFailure}{' '}
          <button
            className="tw-btn"
            onClick={() => {
              setError('');
              void reload();
            }}
          >
            Reload saved state
          </button>
        </div>
      )}
      {notice && (
        <div className="scr-notice" role="status">
          {notice}
        </div>
      )}
      {!state && !error && (
        <div className="scr-empty" role="status">
          Loading saved screeners…
        </div>
      )}
      {state && (
        <>
          <nav className="scr-presets" aria-label="Screener setups">
            {presets.map((item, index) => (
              <button key={item.id} aria-pressed={preset?.id === item.id} onClick={() => changePreset(item.id)}>
                <span className="scr-preset-number">0{index + 1}</span>
                <strong>{item.name}</strong>
                <span>{item.direction}</span>
                <b>{run?.screens.find((value) => value.id === item.id)?.rows.length ?? '—'}</b>
              </button>
            ))}
          </nav>
          {preset && (
            <div className="scr-setup">
              <div>
                <h3>{preset.name}</h3>
                <p>{preset.description}</p>
                <ul>
                  {preset.rules.map((rule) => (
                    <li key={rule}>{rule}</li>
                  ))}
                </ul>
              </div>
              <aside>
                <b>Next research step</b>
                <p>{preset.next}</p>
              </aside>
            </div>
          )}
          {run && (
            <div className="scr-coverage">
              <span>
                <b>{run.eligible.toLocaleString()}</b> eligible / {run.received.toLocaleString()} returned
              </span>
              <span>
                {Object.values(run.excluded).reduce((sum, count) => sum + count, 0)} excluded ·{' '}
                {screen?.missingFields ?? 0} missing setup fields
              </span>
              <span>
                {run.truncated ? 'PARTIAL · result ceiling reached' : 'Returned universe below the result ceiling'}
              </span>
              <span>
                Saved cap {compactMoney(run.config.minCap)}–
                {run.config.maxCap == null ? 'no ceiling' : compactMoney(run.config.maxCap)} · liquidity ≈ ≥{' '}
                {compactMoney(run.config.minDollarVolume)}
              </span>
            </div>
          )}
          {run && (
            <div className="scr-handoff">
              <div>
                <strong>{selected.size} selected</strong>
                <button
                  className="tw-btn"
                  disabled={!selected.size}
                  onClick={() => setSelection({ runId: run.id, symbols: [] })}
                >
                  Clear
                </button>
                <button
                  className="tw-btn"
                  disabled={!selected.size || busy}
                  onClick={() =>
                    void act(async () => {
                      await navigator.clipboard.writeText([...selected].join(', '));
                      setNotice('Selected symbols copied.');
                    })
                  }
                >
                  Copy symbols
                </button>
                <button
                  className="tw-btn"
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      const saved = await api.getRun(run.id);
                      downloadJson({ ...saved.run, selectedSymbols: [...selected] }, `screener-${run.id}.json`);
                    })
                  }
                >
                  Export evidence JSON
                </button>
              </div>
              {selected.size > 0 && (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    void act(async () => {
                      const receipt = await api.handoff(run.id, [...selected], name.trim());
                      setNotice(
                        `Created “${receipt.watchlist}” with ${receipt.symbols.length} names. Open it in the watchlist; choose it explicitly in Scans & alerts to acquire research data.`,
                      );
                      setName('');
                      await onHandoff(receipt.watchlist);
                    });
                  }}
                >
                  <label>
                    New research list{' '}
                    <input
                      value={name}
                      required
                      maxLength={30}
                      onChange={(event) => setName(event.target.value)}
                      placeholder="e.g. September setups"
                    />
                  </label>
                  <button className="tw-btn" disabled={!selected.size || busy || selected.size > 500}>
                    Create watchlist
                  </button>
                </form>
              )}
              <small>
                New lists have automatic scanning disabled. Click a symbol to open its chart and research tools.
              </small>
            </div>
          )}
          {run && preset && screen ? (
            <CandidateTable
              key={`${run.id}-${preset.id}`}
              rows={screen.rows}
              preset={preset}
              selected={selected}
              onSelect={(symbols) => setSelection({ runId: run.id, symbols })}
              onOpen={onOpen}
            />
          ) : (
            <div className="scr-empty">
              No saved results yet. Review the universe and run the five screens to discover candidates.
            </div>
          )}
          {state.history.length > 0 && (
            <footer className="scr-history">
              <label>
                Observation{' '}
                <select
                  disabled={busy}
                  value={historical?.id ?? ''}
                  onChange={(event) => {
                    const id = event.target.value;
                    if (!id) {
                      setHistorical(null);
                      return;
                    }
                    void act(async () => {
                      const saved = await api.getRun(id);
                      setHistorical(saved.run);
                    });
                  }}
                >
                  <option value="">Latest successful run</option>
                  {state.history
                    .filter((item) => item.status === 'complete')
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {new Date(item.finishedAt).toLocaleString()}
                      </option>
                    ))}
                </select>
              </label>
              <span>Rules are research hypotheses. Rankings are metric order, not forecasts or probabilities.</span>
            </footer>
          )}
        </>
      )}
    </div>
  );
}
