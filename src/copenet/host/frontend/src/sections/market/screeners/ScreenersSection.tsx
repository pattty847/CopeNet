import { useEffect, useMemo, useRef, useState } from 'react';
import { useScreeners } from './useScreeners';
import { wsClient } from '../../../lib/wsClient';
import { CandidateTable } from './CandidateTable';
import { ScreenerUniverse } from './ScreenerUniverse';
import { ScreenerTiles } from './ScreenerTiles';
import { ScreenerDefinition } from './ScreenerDefinition';
import { ScreenStats } from './ScreenStats';
import { SetupDock } from './SetupDock';
import { SelectionTray } from './SelectionTray';
import { previousRunId, screenChurn } from './churn';
import { summarizeScreen } from './screenSummary';
import { compactMoney, downloadJson, loadSelection, saveSelection, loadPreset, savePreset } from './model';
import type { ScreenerPreview, ScreenerRun } from './types';
import './screeners.css';

const api = wsClient.marketScreeners;
const observedAt = (run: ScreenerRun) => new Date(run.finishedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

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
  const [previous, setPrevious] = useState<{ forRun: string; run: ScreenerRun | null } | null>(null);
  const [focus, setFocus] = useState<Record<string, string>>({});
  const [selection, setSelectionState] = useState(loadSelection);
  const setSelection = (value: { runId: string; symbols: string[] }) => {
    setSelectionState(value);
    saveSelection(value);
  };
  const run = historical ?? state?.latest ?? null;
  const presets = run?.presets ?? state?.presets ?? [];
  const preset = presets.find((item) => item.id === active) ?? presets[0];
  const screen = run?.screens.find((item) => item.id === preset?.id);
  const selected = useMemo(() => new Set(selection.runId === run?.id ? selection.symbols : []), [selection, run?.id]);
  const changePreset = (identifier: string) => {
    setActive(identifier);
    savePreset(identifier);
    const url = new URL(window.location.href);
    url.searchParams.set('screen', identifier);
    window.history.replaceState({}, '', url);
  };

  // Churn needs the run before this one; load it once per run id and keep it.
  const loadingPrevious = useRef<string | null>(null);
  useEffect(() => {
    if (!run || !state) return;
    if (previous?.forRun === run.id || loadingPrevious.current === run.id) return;
    const before = previousRunId(state.history, run);
    if (!before) {
      setPrevious({ forRun: run.id, run: null });
      return;
    }
    loadingPrevious.current = run.id;
    api
      .getRun(before)
      .then((saved) => setPrevious({ forRun: run.id, run: saved.run }))
      .catch(() => setPrevious({ forRun: run.id, run: null }))
      .finally(() => {
        loadingPrevious.current = null;
      });
  }, [run, state, previous]);
  // Churn is only meaningful against a real prior observation; a first run shows nothing.
  const churn = run && previous?.forRun === run.id && previous.run ? screenChurn(run, previous.run) : null;
  const summary = screen && run ? summarizeScreen(screen.rows, run.eligible) : null;
  const focusedRow = screen?.rows.find((row) => row.symbol === focus[`${run?.id}:${preset?.id}`]) ?? null;
  const setFocusedRow = (symbol: string) => run && preset && setFocus((current) => ({ ...current, [`${run.id}:${preset.id}`]: symbol }));

  const latestFailure = state?.history[0]?.status === 'error' ? state.history[0].error : null;
  const running = state?.running ?? false;
  const configChanged = run && JSON.stringify(config) !== JSON.stringify(run.config);
  const toggleSelect = (symbol: string) => {
    if (!run) return;
    const next = new Set(selected);
    if (next.has(symbol)) next.delete(symbol);
    else next.add(symbol);
    setSelection({ runId: run.id, symbols: [...next] });
  };
  return (
    <div className="scr">
      <form
        className="scr-meta"
        onSubmit={(event) => {
          event.preventDefault();
          void act(async () => setPreview(await api.preview(config)));
        }}
      >
        <div className="scr-meta__line">
          {run ? (
            <>
              <span className="scr-eyebrow">Observed</span>
              <b>{observedAt(run)}</b>
              <span className="scr-meta__dot">·</span>
              <span>TradingView</span>
              <span className="scr-meta__dot">·</span>
              <span>delayed ≤ 15 min</span>
              <span className="scr-meta__dot">·</span>
              <b>{run.eligible.toLocaleString()}</b>
              <span>eligible of {run.received.toLocaleString()} returned</span>
              {run.truncated && <span className="scr-meta__warn">PARTIAL · result ceiling reached</span>}
              {configChanged && <span className="scr-meta__warn">Universe changed · results show the saved run</span>}
            </>
          ) : (
            <>
              <span className="scr-eyebrow">TradingView</span>
              <span>{running ? 'Screen in progress' : 'No saved observation'}</span>
              <span className="scr-meta__dot">·</span>
              <span>quotes may be delayed, daily bars may be unfinished</span>
            </>
          )}
          <span className="scr-meta__grow" />
          {run && !editingUniverse && (
            <>
              <span className="scr-eyebrow">Universe</span>
              <b>cap ≥ {compactMoney(run.config.minCap)}</b>
              {run.config.maxCap != null && <b>≤ {compactMoney(run.config.maxCap)}</b>}
              <span className="scr-meta__dot">·</span>
              <b>price ≥ ${run.config.minPrice}</b>
              <span className="scr-meta__dot">·</span>
              <b>liq ≥ {compactMoney(run.config.minDollarVolume)}</b>
              <span>/day</span>
            </>
          )}
          {run && (
            <button type="button" className="tw-btn tw-btn--sm" aria-expanded={editingUniverse} onClick={() => setEditingUniverse(!editingUniverse)}>
              {editingUniverse ? 'Hide universe' : 'Edit universe'}
            </button>
          )}
          <button className="tw-btn tw-btn--sm" type="submit" disabled={busy || running || !state}>
            {running ? 'Screen in progress…' : 'Review & run all five'}
          </button>
        </div>
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
      </form>
      {preview && (
        <section className="scr-preview" aria-label="Review screener scope">
          <h3>Run these five screens</h3>
          <p>
            {preview.scope} Up to {preview.maxRows.toLocaleString()} returned instruments.
          </p>
          <p>
            Market cap {compactMoney(preview.config.minCap)}–{preview.config.maxCap == null ? 'no ceiling' : compactMoney(preview.config.maxCap)} · Price ≥ $
            {preview.config.minPrice} · Liquidity ≈ ≥ {compactMoney(preview.config.minDollarVolume)}
          </p>
          <ul>
            {preview.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <div>
            <button
              type="button"
              className="tw-btn"
              disabled={busy || running}
              onClick={() =>
                void act(async () => {
                  await api.run(preview.config, preview.scopeToken);
                  setPreview(null);
                  setHistorical(null);
                  setEditingUniverse(false);
                  setState((current) => (current ? { ...current, running: true } : current));
                  await reload();
                })
              }
            >
              Run screeners
            </button>
            <button type="button" className="tw-btn" disabled={busy} onClick={() => setPreview(null)}>
              Cancel
            </button>
          </div>
        </section>
      )}
      {(error || latestFailure) && (
        <div className="scr-error" role="alert">
          {error || latestFailure}{' '}
          <button
            type="button"
            className="tw-btn tw-btn--sm"
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
          <ScreenerTiles presets={presets} run={run} active={preset?.id ?? ''} churn={churn} onSelect={changePreset} />
          {preset && <ScreenerDefinition preset={preset} summary={summary} minCap={run?.config.minCap ?? config.minCap} />}
          {summary && screen && run && <ScreenStats summary={summary} eligible={run.eligible} missingFields={screen.missingFields} />}
          {run && preset && screen ? (
            <div className="scr-body">
              <div className="scr-results">
                <CandidateTable
                  key={`${run.id}-${preset.id}`}
                  rows={screen.rows}
                  preset={preset}
                  selected={selected}
                  focus={focusedRow?.symbol ?? null}
                  newSymbols={churn?.[preset.id]?.added ?? new Set()}
                  onSelect={(symbols) => setSelection({ runId: run.id, symbols })}
                  onFocus={setFocusedRow}
                  onOpen={onOpen}
                />
              </div>
              <SetupDock preset={preset} row={focusedRow} selected={focusedRow ? selected.has(focusedRow.symbol) : false} onOpen={onOpen} onToggleSelect={toggleSelect} />
            </div>
          ) : (
            <div className="scr-empty">No saved results yet. Review the universe and run the five screens to discover candidates.</div>
          )}
          {run && (
            <SelectionTray
              selected={[...selected]}
              busy={busy}
              onClear={() => setSelection({ runId: run.id, symbols: [] })}
              onCopy={() =>
                void act(async () => {
                  await navigator.clipboard.writeText([...selected].join(', '));
                  setNotice('Selected symbols copied.');
                })
              }
              onExport={() =>
                void act(async () => {
                  const saved = await api.getRun(run.id);
                  downloadJson({ ...saved.run, selectedSymbols: [...selected] }, `screener-${run.id}.json`);
                })
              }
              onCreateList={(name) =>
                act(async () => {
                  const receipt = await api.handoff(run.id, [...selected], name);
                  setNotice(
                    `Created “${receipt.watchlist}” with ${receipt.symbols.length} names. Open it in the watchlist; choose it explicitly in Scans & alerts to acquire research data.`,
                  );
                  await onHandoff(receipt.watchlist);
                })
              }
            />
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
