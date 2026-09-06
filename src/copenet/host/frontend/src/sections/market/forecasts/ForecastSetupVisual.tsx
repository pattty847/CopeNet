import { useEffect, useRef, useState } from 'react';
import type { ForecastChart, ForecastSetup } from './types';
import { setupVisualModel } from './setupVisualModel';
import './setupVisual.css';

const signed = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(2)}`;
const date = (time: number) => new Date(time * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' });
const price = (value: number) => value.toLocaleString(undefined, { maximumSignificantDigits: 6 });
export function ForecastSetupVisual({ setup, chart }: { setup: ForecastSetup; chart: ForecastChart | null }) {
  const container = useRef<HTMLElement>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(220, entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const model = chart && setupVisualModel(setup, chart, width);
  const point = model && hover != null ? model.points[hover] : null;
  return <figure ref={container} className="cf-setup-visual" aria-label="Original setup price map">
    {!chart || !model ? <p role="status">Loading setup chart…</p> : <>
      <div className="cf-setup-caption"><span><i /> Daily close</span><span>{point ? `${date(point.t)} · ${price(point.close)}` : 'Original setup → actual outcome'}</span></div>
      <svg width="100%" height="250" viewBox={`0 0 ${width} 250`} role="img" aria-label="Actual daily closing prices with original entry, stop and target bands"
        onPointerLeave={() => setHover(null)} onPointerMove={(event) => {
          const position = event.clientX - event.currentTarget.getBoundingClientRect().left;
          if (position > model.x(model.points[model.points.length - 1]?.t ?? chart.publishedAt) + 8) { setHover(null); return; }
          let nearest = 0;
          model.points.forEach((item, index) => { if (Math.abs(model.x(item.t) - position) < Math.abs(model.x(model.points[nearest].t) - position)) nearest = index; });
          setHover(model.points.length ? nearest : null);
        }}>
        <title>Frozen history followed by completed daily closes. Blank future space contains no predicted price path.</title>
        <rect className="cf-setup-reward" x={model.publicationX} width={model.right - model.publicationX} y={Math.min(model.entryY, model.targetY)} height={Math.abs(model.targetY - model.entryY)} />
        <rect className="cf-setup-risk" x={model.publicationX} width={model.right - model.publicationX} y={Math.min(model.entryY, model.stopY)} height={Math.abs(model.stopY - model.entryY)} />
        <line x1={model.publicationX} x2={model.publicationX} y1="12" y2="221" stroke="var(--mkt-muted)" strokeOpacity=".4" strokeDasharray="2 4" />
        {model.levels.map((level) => <g key={level.label} className={`cf-setup-${level.kind}`}>
          <path d={`M${model.publicationX} ${level.y} H${model.right} L${model.right + 6} ${level.labelY}`} fill="none" stroke="currentColor" strokeOpacity=".65" strokeDasharray={level.kind === 'entry' ? '2 3' : 'none'} />
          <text x={model.right + 9} y={level.labelY + 3} fill="currentColor" fontSize="10">{level.label} {price(level.price)}</text>
        </g>)}
        <path data-price-history d={model.historyPath} className="cf-setup-line" />
        <path data-price-outcome d={model.outcomePath} className="cf-setup-line" />
        {point && <circle cx={model.x(point.t)} cy={model.y(point.close)} r="3" fill="#36b7ef" />}
        <g fill="var(--mkt-muted)" fontSize="10">
          <text x="8" y="240">{date(model.start)}</text>
          <text x={model.publicationX} y="240" textAnchor="middle">Recorded</text>
          <text x={model.right} y="240" textAnchor="end">8w</text>
        </g>
      </svg>
      <figcaption>Recorded {date(chart.publishedAt)} · horizon {date(chart.deadlineAt)} (UTC). {chart.outcome.length ? `Tracking through ${date(chart.outcome[chart.outcome.length - 1].t)}.` : 'Awaiting completed sessions after publication.'} Closing prices only; intraday stop/target touches may not appear on the line.</figcaption>
      {!chart.historyAvailable && <p className="cf-setup-notice">Frozen history unavailable.</p>}
      {chart.health !== 'ready' && <p className="cf-setup-notice">{chart.health.replaceAll('_', ' ')}{chart.reason ? ` · ${chart.reason}` : ''}</p>}
      <details><summary>Levels and returns</summary><dl className="cf-setup-values">{model.levels.map((level) => <div key={level.label}>
        <dt>{level.kind === 'stop' ? 'Stop loss' : level.kind === 'entry' ? `${setup.entry.kind} entry` : level.label}{level.fraction != null ? ` · ${Math.round(level.fraction * 100)}% size` : ''}</dt>
        <dd>{level.price} <small>{level.kind === 'entry' ? '' : `${signed(level.percent)}% · ${signed(level.riskMultiple)}R`}</small></dd>
      </div>)}</dl><small>Returns follow the {setup.direction} direction. 1R is planned entry-to-stop risk. Levels are conditional, not probabilities.</small></details>
    </>}
  </figure>;
}
