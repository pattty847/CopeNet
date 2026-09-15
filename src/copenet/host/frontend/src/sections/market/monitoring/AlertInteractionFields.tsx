import { AlertOperandEditor } from './AlertOperandEditor';
import type { AlertRule, IndicatorOption } from './types';

export function AlertInteractionFields({ rule, catalogue, update }: {
  rule: AlertRule; catalogue: IndicatorOption[]; update: (change: Partial<AlertRule>) => void;
}) {
  const confirmation = rule.confirmation;
  return <>
    <label className="mm-check">
      <input type="checkbox" checked={!!confirmation} onChange={(event) => update({ confirmation: event.target.checked
        ? { left: { kind: 'indicator', indicatorId: 'mama', config: { fastLimit: 0.5, slowLimit: 0.05 }, output: 'mama' },
            right: { kind: 'indicator', indicatorId: 'mama', config: { fastLimit: 0.5, slowLimit: 0.05 }, output: 'fama' }, direction: rule.direction }
        : null })} /> Use a custom close confirmation
    </label>
    {confirmation ? <>
      <div className="mm-monitor-fields mm-monitor-operands">
        <AlertOperandEditor label="Confirm at close" operand={confirmation.left} catalogue={catalogue} onChange={(left) => update({ confirmation: { ...confirmation, left } })} />
        <AlertOperandEditor label="Compare at close" operand={confirmation.right} catalogue={catalogue} onChange={(right) => update({ confirmation: { ...confirmation, right } })} />
      </div>
      <label>At the completed candle
        <select className="tw-input" value={confirmation.direction} onChange={(event) => update({ confirmation: { ...confirmation, direction: event.target.value as 'above' | 'below' } })}>
          <option value="above">Is at or above</option><option value="below">Is at or below</option>
        </select>
      </label>
    </> : <p>Confirmation checks whether the close finishes at or {rule.direction} the signal, using the completed candle’s signal value.</p>}
  </>;
}
