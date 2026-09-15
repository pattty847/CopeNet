import { TickerMonitorPanel } from '../monitoring/TickerMonitors';
import { useState } from 'react';
import { usePositionContext } from './PositionContext';
import { money, percent, scenario } from './model';
import './position.css';

export function PositionPanel() {
  const context = usePositionContext();
  const [price, setPrice] = useState('');
  if (!context) return null;
  const { state, preferences, update, hidden } = context;
  const { data, error, reload, loading } = state;
  const position = data?.position;
  if (!position) return <div className="tw-position-panel">{data?.warnings.map((warning) => <p key={warning} role="status">{warning}</p>)}<p role={error ? 'alert' : 'status'}>{error ?? (loading ? 'Loading saved position…' : 'No equity position in the saved Webull account.')}</p><button className="tw-btn" onClick={() => void reload()}>Reload saved position</button></div>;
  const estimate = scenario(position, Number(price));
  return <section className="tw-position-panel" aria-label="Your position">
    <div className="tw-position-summary">
      <div><span>Unrealized · snapshot</span><strong>{money(position.unrealized_pl, position.currency)} <small>{percent(position.unrealized_pl_pct)}</small></strong></div>
      <dl><div><dt>Shares</dt><dd>{position.quantity.toLocaleString()}</dd></div><div><dt>Average cost</dt><dd>{money(position.avg_cost, position.currency)}</dd></div><div><dt>Portfolio weight</dt><dd>{position.allocation_pct == null ? '—' : `${position.allocation_pct.toFixed(2)}%`}</dd></div></dl>
    </div>
    <p className="tw-position-source">Webull · synced {new Date(position.synced_at).toLocaleString()} · Price: {position.price_source}</p>
    {error && <p role="alert">{error} · Last saved position retained.</p>}
    {[...(data?.warnings ?? []), ...(position.warnings ?? [])].map((warning, index) => <p key={index} role="status">{warning}</p>)}
    <fieldset className="tw-position-options"><legend>On chart</legend>{([
      ['visible', 'Position line'], ['shading', 'P&L shading'], ['fills', 'Recorded buys / sells'], ['cursor', 'P&L at cursor'],
    ] as const).map(([key, label]) => <label key={key}><input type="checkbox" checked={preferences[key]} onChange={(event) => update({ [key]: event.target.checked })} />{label}</label>)}</fieldset>
    {hidden && <p className="tw-position-source">Position overlays pause in replay and comparison views.</p>}
    <div className="tw-position-scenario"><label>What if price reaches <input className="tw-input" type="number" step="any" min="0" value={price} onChange={(event) => setPrice(event.target.value)} placeholder="Price" /></label><output>{estimate ? `${money(estimate.dollars, position.currency)} · ${percent(estimate.percent)}` : '—'}</output><span>Current shares and average cost · excludes fees. Also hold Alt over the chart.</span></div>
    <TickerMonitorPanel />
    <details className="tw-position-story"><summary>Position story <span>{data?.fillCount ?? 0} filled orders</span></summary>
      <p>{data?.historyNote} {data?.fillsSyncedAt ? `Fills synced ${new Date(data.fillsSyncedAt).toLocaleString()}.` : 'Sync fill history in Market → Portfolio to load filled orders.'}</p>
      {data && data.fillCount > data.fills.length && <p>Showing the latest {data.fills.length} of {data.fillCount} filled orders.</p>}
      {data?.fills.length ? <div className="tw-position-table"><table><thead><tr><th>Executed</th><th>Action</th><th>Shares</th><th>Price</th></tr></thead><tbody>{[...data.fills].reverse().map((fill) => <tr key={`${fill.id}:${fill.filledAt}`}><td>{new Date(fill.filledAt).toLocaleString()}</td><td>{fill.side === 'BUY' ? 'Buy' : fill.side === 'SHORT' ? 'Short' : 'Sell'}</td><td>{fill.quantity.toLocaleString()}</td><td>{money(fill.price, position.currency)}{fill.priceSource === 'limit' ? ' (estimate)' : ''}</td></tr>)}</tbody></table></div> : <p>No saved filled orders for this ticker.</p>}
    </details>
  </section>;
}

export function PositionChip() {
  const context = usePositionContext();
  const position = context?.state.data?.position;
  if (!context || !position || context.hidden || !context.preferences.visible) return null;
  return <button type="button" className="tw-position-chip" onClick={context.open} title={`Webull position synced ${new Date(position.synced_at).toLocaleString()}. Hold Alt over the chart for a price scenario.`}>
    <span>Position</span><b>{position.quantity.toLocaleString()} shares</b><span>{money(position.unrealized_pl, position.currency)} · {percent(position.unrealized_pl_pct)}</span><small>snapshot</small>
  </button>;
}
