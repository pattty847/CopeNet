// What the selected setup looks for, in prose and as a rule grid whose third column is the
// matched population's median — the definition describes the matches, not only the rule.
import type { Preset } from './types';
import { formatRuleValue, ruleWindows } from './ruleWindows';
import type { ScreenSummary } from './screenSummary';
import { compactMoney } from './model';

const DIRECTION_GLYPH: Record<string, string> = { Bullish: '↑', Bearish: '↓', Either: '↕' };

export function ScreenerDefinition({ preset, summary, minCap }: { preset: Preset; summary: ScreenSummary | null; minCap: number }) {
  const windows = ruleWindows(preset);
  return (
    <div className="scr-definition">
      <div>
        <h3>
          {preset.name}
          <span data-direction={preset.direction}>
            {DIRECTION_GLYPH[preset.direction] ?? ''} {preset.direction}
          </span>
        </h3>
        <p>{preset.description}</p>
        <p className="scr-definition__next">
          <span className="scr-eyebrow">Before you act</span>
          {preset.next}
        </p>
      </div>
      <dl className="scr-rules">
        <dt className="scr-eyebrow">Rule</dt>
        <dt className="scr-eyebrow">Condition</dt>
        <dt className="scr-eyebrow">Matched median</dt>
        {windows.length > 0
          ? windows.map((rule) => (
              <div key={rule.key} className="scr-rules__row">
                <dd>{rule.label}</dd>
                <dd className="scr-rules__condition">{rule.condition}</dd>
                <dd className="scr-rules__median">
                  {rule.key === 'marketCap'
                    ? `≥ ${compactMoney(Math.max(15e9, minCap))} floor`
                    : summary
                      ? formatRuleValue(rule, summary.medians[rule.key] ?? null)
                      : '—'}
                </dd>
              </div>
            ))
          : preset.rules.map((rule) => (
              <div key={rule} className="scr-rules__row">
                <dd>{rule}</dd>
                <dd />
                <dd />
              </div>
            ))}
      </dl>
    </div>
  );
}
