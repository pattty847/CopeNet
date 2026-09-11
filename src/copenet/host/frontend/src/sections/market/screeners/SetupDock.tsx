// The focused row's setup, drawn from cached daily history only. Screeners discover
// names; they never acquire research data, so an uncached symbol gets prose and a link
// to the ticker workspace rather than a fetch.
import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import type { IndicatorBar } from '../indicators/types';
import type { Candidate, Preset } from './types';
import { formatRuleValue, ruleValue, ruleWindows, windowPosition } from './ruleWindows';
import { STRIP_HEIGHT, VISUAL_HEIGHT, setupVisualModel } from './setupVisualModel';

const api = wsClient.marketScreeners;
const cache = new Map<string, Promise<IndicatorBar[] | null>>();
function loadBars(symbol: string): Promise<IndicatorBar[] | null> {
  let pending = cache.get(symbol);
  if (!pending) {
    pending = api.setup(symbol).then((payload) => payload.bars);
    cache.set(symbol, pending);
    pending.catch(() => cache.delete(symbol));
  }
  return pending;
}

const price = (value: number) => (value >= 1000 ? value.toLocaleString('en-US', { maximumFractionDigits: 0 }) : value.toFixed(2));
const ZONE_FILL: Record<string, string> = { up: 'rgba(105,197,137,.12)', down: 'rgba(217,109,95,.12)', either: 'rgba(205,199,188,.10)' };
const ZONE_STROKE: Record<string, string> = { up: 'var(--mkt-up)', down: 'var(--mkt-down)', either: 'var(--mkt-muted)' };
const OVERLAY_STYLE: Record<string, React.SVGProps<SVGPathElement>> = {
  sma50: { stroke: 'var(--mkt-soft)', strokeDasharray: '3 3', strokeOpacity: 0.8 },
  sma200: { stroke: 'var(--mkt-dim)', strokeOpacity: 0.9 },
  high52: { stroke: 'var(--mkt-dimmer)', strokeDasharray: '1 3' },
};

export function SetupDock({
  preset,
  row,
  selected,
  onOpen,
  onToggleSelect,
}: {
  preset: Preset;
  row: Candidate | null;
  selected: boolean;
  onOpen: (symbol: string) => void;
  onToggleSelect: (symbol: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(320);
  const [bars, setBars] = useState<{ symbol: string; bars: IndicatorBar[] | null } | 'loading' | null>(null);
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.floor(entry.contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const symbol = row?.symbol ?? null;
  useEffect(() => {
    if (!symbol) {
      setBars(null);
      return;
    }
    let alive = true;
    setBars('loading');
    loadBars(symbol)
      .then((result) => alive && setBars({ symbol, bars: result }))
      .catch(() => alive && setBars({ symbol, bars: null }));
    return () => {
      alive = false;
    };
  }, [symbol]);

  if (!row) {
    return (
      <aside className="scr-dock" aria-label="Setup view">
        <div className="scr-dock__empty">
          <b>Setup view.</b> Click a row to draw its last six months with this setup's indicators and the rule window. Only names already in the price cache
          draw; the screener never fetches history for you.
        </div>
      </aside>
    );
  }
  const loaded = bars !== 'loading' && bars?.symbol === row.symbol ? bars.bars : undefined;
  const model = loaded ? setupVisualModel(loaded, preset, row, width) : null;
  const windows = ruleWindows(preset).filter((rule) => rule.low != null);
  return (
    <aside className="scr-dock" aria-label={`Setup view for ${row.symbol}`}>
      <div className="scr-dock__head">
        <span className="scr-dock__symbol">{row.symbol}</span>
        <span className="scr-dock__company">{row.name || row.symbol}</span>
        <span className="scr-dock__price">{price(row.price)}</span>
        <span className="scr-dock__change" data-direction={row.change == null ? '' : row.change >= 0 ? 'Bullish' : 'Bearish'}>
          {row.change == null ? '—' : `${row.change > 0 ? '+' : ''}${row.change.toFixed(2)}%`}
        </span>
      </div>
      <div ref={container}>
        {loaded === undefined && <p className="scr-dock__note">Reading the price cache…</p>}
        {loaded === null && (
          <p className="scr-dock__note">
            <b>{row.symbol}</b> is not in the local price cache, so there is nothing to draw. Open the ticker to load six months of daily history; the
            screener itself never fetches it.
          </p>
        )}
        {model && (
          <figure className="scr-setup">
            <figcaption>
              <span>
                <i /> Daily close · 6 months
              </span>
              <span>
                {preset.name} · {preset.direction.toLowerCase()}
              </span>
            </figcaption>
            <svg viewBox={`0 0 ${model.width} ${VISUAL_HEIGHT}`} role="img" aria-label="Six months of daily closes with the setup's indicators and rule zone">
              {model.bandPath && <path d={model.bandPath} fill="rgba(143,184,232,.08)" />}
              {model.zone && (
                <g>
                  <rect
                    x={model.observedX - 1}
                    y={model.zone.top}
                    width={Math.max(0, model.width - 56 - model.observedX)}
                    height={Math.max(1, model.zone.bottom - model.zone.top)}
                    fill={ZONE_FILL[model.zone.tone]}
                  />
                  <path d={`M${model.observedX} ${model.zone.top} H${model.width - 56}`} stroke={ZONE_STROKE[model.zone.tone]} strokeOpacity={0.6} />
                  <path d={`M${model.observedX} ${model.zone.bottom} H${model.width - 56}`} stroke={ZONE_STROKE[model.zone.tone]} strokeOpacity={0.6} />
                  <text x={model.width - 52} y={model.zone.top + 3} fill={ZONE_STROKE[model.zone.tone]} fontSize="9">
                    {model.zone.labelTop}
                  </text>
                  <text x={model.width - 52} y={model.zone.bottom + 3} fill={ZONE_STROKE[model.zone.tone]} fontSize="9">
                    {model.zone.labelBottom}
                  </text>
                </g>
              )}
              {model.overlays.map((overlay) => (
                <path key={overlay.key} d={overlay.path} fill="none" strokeWidth={1} {...OVERLAY_STYLE[overlay.key]} />
              ))}
              <line x1={model.observedX} x2={model.observedX} y1={10} y2={VISUAL_HEIGHT - 16} stroke="var(--mkt-muted)" strokeOpacity={0.4} strokeDasharray="2 4" />
              <path d={model.pricePath} fill="none" stroke="var(--mkt-info)" strokeWidth={1.4} />
              <circle cx={model.observedX} cy={model.lastY} r={2.5} fill="var(--mkt-info)" />
              {model.levels.map((level) => (
                <text key={level.label} x={model.observedX + 6} y={level.y + 3} fill="var(--mkt-dim)" fontSize="8">
                  {level.label}
                </text>
              ))}
              <g fill="var(--mkt-dim)" fontSize="9">
                <text x={8} y={VISUAL_HEIGHT - 3}>{model.startLabel}</text>
                <text x={model.observedX} y={VISUAL_HEIGHT - 3} textAnchor="middle">
                  {model.observedLabel}
                </text>
              </g>
            </svg>
            <svg viewBox={`0 0 ${model.width} ${STRIP_HEIGHT}`} role="img" aria-label={model.strip.kind === 'rsi' ? 'RSI with the rule window shaded' : 'Volume against its 30-day average'}>
              {model.strip.kind === 'rsi' ? (
                <>
                  {model.strip.windowTop != null && model.strip.windowBottom != null && (
                    <rect x={8} y={model.strip.windowTop} width={Math.max(0, model.width - 56 - 8)} height={model.strip.windowBottom - model.strip.windowTop} fill={ZONE_FILL[model.zone?.tone ?? 'either']} />
                  )}
                  <path d={model.strip.path} fill="none" stroke="var(--mkt-soft)" strokeWidth={1} />
                  <circle cx={model.observedX} cy={model.strip.lastY} r={2} fill="var(--mkt-text)" />
                  {model.strip.windowTop != null && (
                    <text x={model.width - 52} y={model.strip.windowTop + 3} fill="var(--mkt-dim)" fontSize="8">
                      RSI {model.strip.high}
                    </text>
                  )}
                  {model.strip.windowBottom != null && (
                    <text x={model.width - 52} y={model.strip.windowBottom + 3} fill="var(--mkt-dim)" fontSize="8">
                      RSI {model.strip.low}
                    </text>
                  )}
                  <text x={model.observedX + 6} y={model.strip.lastY + 3} fill="var(--mkt-text)" fontSize="8">
                    {model.strip.last?.toFixed(1) ?? ''}
                  </text>
                  <text x={8} y={STRIP_HEIGHT - 2} fill="var(--mkt-dim)" fontSize="8">
                    RSI 14 · shaded = rule window
                  </text>
                </>
              ) : (
                <>
                  {model.strip.bars.map((bar, index) => (
                    <rect key={index} x={bar.x} y={bar.y} width={bar.width} height={bar.height} fill={bar.last ? 'var(--mkt-text)' : 'var(--mkt-dimmer)'} />
                  ))}
                  <path d={model.strip.averagePath} fill="none" stroke="var(--mkt-muted)" strokeWidth={1} />
                  <text x={model.observedX + 6} y={14} fill="var(--mkt-muted)" fontSize="8">
                    Rel. vol {model.strip.relativeVolume?.toFixed(2) ?? '—'}× · 30d avg
                  </text>
                  <text x={8} y={STRIP_HEIGHT - 2} fill="var(--mkt-dim)" fontSize="8">
                    Volume · last 40 sessions
                  </text>
                </>
              )}
            </svg>
            <p className="scr-dock__note">
              Closes from the local split-only price cache; indicators recomputed here. TradingView's values (right) may differ slightly and include today's
              unfinished session.
            </p>
          </figure>
        )}
      </div>
      <dl className="scr-dock__rules">
        {windows.map((rule) => {
          const value = ruleValue(row, rule);
          const position = windowPosition(rule, value);
          return (
            <div key={rule.key}>
              <dt>{rule.label}</dt>
              <dd>{formatRuleValue(rule, value)}</dd>
              <dd className="scr-window" aria-hidden="true">
                {position != null && <i style={{ left: `${(position * 100).toFixed(1)}%` }} />}
              </dd>
            </div>
          );
        })}
      </dl>
      <div className="scr-dock__actions">
        <button type="button" className="tw-btn tw-btn--sm" onClick={() => onOpen(row.symbol)}>
          Open ticker ↗
        </button>
        <button type="button" className="tw-btn tw-btn--sm" onClick={() => onToggleSelect(row.symbol)}>
          {selected ? 'Remove from selection' : 'Add to selection'}
        </button>
      </div>
    </aside>
  );
}
