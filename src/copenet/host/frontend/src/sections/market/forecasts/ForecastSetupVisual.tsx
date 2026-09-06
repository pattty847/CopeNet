import type { ForecastSetup } from './types';
import { setupVisualModel } from './setupVisualModel';
import './setupVisual.css';

const signed = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(2)}`;
export function ForecastSetupVisual({ setup }: { setup: ForecastSetup }) {
  const model = setupVisualModel(setup);
  return <figure className="cf-setup-visual" aria-label="Original setup price map">
    <div className="cf-setup-map">
      <svg width="88" height={model.height} viewBox={`0 0 88 ${model.height}`} aria-hidden="true">
        <rect className="cf-setup-reward" x="8" width="26" y={Math.min(model.entryY, model.targetY)} height={Math.abs(model.targetY - model.entryY)} />
        <rect className="cf-setup-risk" x="8" width="26" y={Math.min(model.entryY, model.stopY)} height={Math.abs(model.stopY - model.entryY)} />
        {model.levels.map((level) => <g key={level.label} className={`cf-setup-${level.kind}`}>
          <path d={`M8 ${level.y} H40 L70 ${level.labelY} H86`} fill="none" stroke="currentColor" />
          <circle cx="21" cy={level.y} r={level.kind === 'entry' ? 4 : 2.5} fill="currentColor" />
        </g>)}
      </svg>
      <dl>{model.levels.map((level) => <div key={level.label} className={`cf-setup-row cf-setup-${level.kind}`}>
        <dt>{level.label}{level.fraction !== null && <small> · {Math.round(level.fraction * 100)}% size</small>}</dt>
        <dd><strong>{level.price}</strong><small>{level.kind === 'entry' ? 'Reference price' : `${signed(level.percent)}% · ${signed(level.riskMultiple)}R`}</small></dd>
      </div>)}</dl>
    </div>
    <figcaption>Price spacing is to scale. Returns measured from entry for this {setup.direction} setup; 1R is the planned entry-to-stop risk. Levels are conditional, not probabilities.</figcaption>
  </figure>;
}
