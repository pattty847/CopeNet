// Plots: everything drawn on the chart that is not the candles themselves.
//
// Three layer families share one home, in the order an operator reaches for them — volume,
// technical indicators, then point-in-time financial series. Compare deliberately stays a
// separate tool: it rebases the price pane to indexed percent, which is a mode change rather
// than another layer, and every price-anchored plot here is genuinely inapplicable while it
// is on. Listing compared assets in here would imply they compose, and they do not.
//
// The list answers "what is on my chart"; the picker answers "what else could be". Keeping
// them apart is what stops this from becoming the graveyard the redesign gauntlet warned a
// single combined Plots popover would turn into.

import { useState } from 'react';
import { Plus, X } from 'lucide-react';
import { ChartPopoverShell } from './chartPopoverShell';
import { FinancialSeriesPicker } from './FinancialSeriesPicker';
import { IndicatorPicker } from './indicators/IndicatorPicker';
import { IndicatorRows, type IndicatorRowActions } from './indicators/IndicatorRows';
import { MAX_INDICATORS, type IndicatorInstance } from './indicators/state';
import type { ComputedIndicator } from './indicators/compute';
import { MM } from './marketUi';
import type { FinancialFrequency, FinancialMetricInfo } from './types';

export function PlotsMenu({
  anchor,
  open,
  onClose,
  metrics,
  metric,
  frequency,
  onFrequency,
  onClearMetric,
  onMetric,
  showVolume,
  onShowVolume,
  comparisonActive,
  indicators,
  computedIndicators,
  onAddIndicator,
  indicatorActions,
}: {
  anchor: React.RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  metrics: FinancialMetricInfo[];
  metric: string | null;
  frequency: FinancialFrequency;
  onFrequency: (value: FinancialFrequency) => void;
  onClearMetric: () => void;
  onMetric: (metric: string) => void;
  showVolume: boolean;
  onShowVolume: (value: boolean) => void;
  comparisonActive: boolean;
  indicators: IndicatorInstance[];
  computedIndicators: ComputedIndicator[];
  onAddIndicator: (indicatorId: string) => void;
  indicatorActions: IndicatorRowActions;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const info = metric ? metrics.find((entry) => entry.id === metric) ?? null : null;
  const valuation = info?.factType === 'valuation';
  const choices = info?.frequencies ?? (['quarterly', 'ttm', 'annual'] as FinancialFrequency[]);

  return (
    <ChartPopoverShell anchor={anchor} open={open} onClose={onClose} title="Plots" width={332}>
      <div className="tw-pop__section">
        <label className="tw-switch">
          <span>Volume</span>
          <input type="checkbox" checked={showVolume} onChange={(event) => onShowVolume(event.target.checked)} />
        </label>
      </div>

      <div className="tw-pop__section">
        <div className="tw-pop__label">
          Indicators{indicators.length > 0 ? ` · ${indicators.length}` : ''}
        </div>
        <IndicatorRows
          instances={indicators}
          computed={computedIndicators}
          expanded={expanded}
          onToggleExpanded={setExpanded}
          actions={indicatorActions}
        />
        {picking ? (
          <div className="tw-ind-add">
            <IndicatorPicker
              onPick={(indicatorId) => {
                onAddIndicator(indicatorId);
                setPicking(false);
              }}
              disabled={comparisonActive}
              disabledReason="Indicators are price-anchored and unavailable in Compare mode."
              atCapacity={indicators.length >= MAX_INDICATORS}
            />
            <button type="button" className="tw-btn tw-btn--sm" onClick={() => setPicking(false)}>
              <X size={11} /> Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="tw-plotrow tw-ind-addrow"
            onClick={() => setPicking(true)}
            disabled={comparisonActive}
            title={comparisonActive ? 'Unavailable in Compare mode' : 'Add a technical indicator'}
          >
            <Plus size={12} aria-hidden="true" /> Add indicator
          </button>
        )}
      </div>

      <div className="tw-pop__section">
        <div className="tw-pop__label">Financial series</div>
        {info ? (
          <div className="tw-pop__row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 7 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
              <span style={{ color: MM.info, font: '600 10px Inter' }}>{info.label}</span>
              <button type="button" className="tw-iconbtn" onClick={onClearMetric} aria-label={`Remove ${info.label} plot`} title="Remove plot"><X size={12} /></button>
            </div>
            {!valuation && (
              <div className="tw-choices">
                {choices.map((value) => (
                  <button key={value} type="button" aria-pressed={frequency === value} onClick={() => onFrequency(value)}>
                    {value === 'ttm' ? 'TTM' : value === 'annual' ? 'Annual' : 'Quarter'}
                  </button>
                ))}
              </div>
            )}
            {valuation && <p className="tw-pop__note">TTM series</p>}
          </div>
        ) : null}
        <FinancialSeriesPicker
          metrics={metrics}
          selectedMetric={metric}
          disabled={comparisonActive}
          onSelect={onMetric}
        />
        {comparisonActive && <p className="tw-pop__note">Unavailable in Compare mode</p>}
      </div>
    </ChartPopoverShell>
  );
}
