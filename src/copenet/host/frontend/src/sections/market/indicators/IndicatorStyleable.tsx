// An indicator, described to the shared settings surfaces. Its layout store applies changes
// live (that is what previews them on the chart), so the popup snapshots the instance on open
// and Cancel restores it. Inputs is the registry-generated form this indicator always had.
import { useMemo, useState } from 'react';
import { ChartObjectSettings } from '../chartStyle/ChartObjectSettings';
import type { SelectionBarModel } from '../chartStyle/SelectionBar';
import type { StrokeField, Styleable } from '../chartStyle/types';
import { IndicatorSettings } from './IndicatorSettings';
import type { ComputedIndicator } from './compute';
import type { IndicatorRowActions } from './IndicatorRows';

function strokeFields(indicator: ComputedIndicator, actions: IndicatorRowActions, withVisibility: boolean): StrokeField[] {
  return indicator.outputs.map((output) => ({
    key: output.key, label: output.label,
    value: { color: output.color, width: output.lineWidth, style: output.lineStyle },
    onChange: (next) => actions.onStyle(indicator.instanceId, output.key, {
      ...(next.color ? { color: next.color } : {}), ...(next.width ? { lineWidth: next.width } : {}), ...(next.style ? { lineStyle: next.style } : {}) }),
    visible: withVisibility && indicator.outputs.length > 1
      ? { value: output.visible, onChange: (visible: boolean) => actions.onStyle(indicator.instanceId, output.key, { visible }) } : undefined,
  }));
}

export function indicatorBarModel(indicator: ComputedIndicator, outputKey: string | undefined, actions: IndicatorRowActions,
  handlers: { openSettings: () => void; deselect: () => void }): SelectionBarModel {
  const strokes = strokeFields(indicator, actions, false);
  return {
    id: `indicator:${indicator.instanceId}`, title: indicator.label,
    stroke: strokes.find((field) => field.key === outputKey) ?? strokes[0],
    hide: () => { actions.onVisibility(indicator.instanceId, false); handlers.deselect(); },
    remove: () => { actions.onRemove(indicator.instanceId); handlers.deselect(); },
    ...handlers,
  };
}

export function IndicatorSettingsPopup({ indicator, actions, onClose }: { indicator: ComputedIndicator; actions: IndicatorRowActions; onClose: () => void }) {
  const [snapshot] = useState(indicator.instance);
  const { instanceId } = indicator;
  const target = useMemo<Styleable>(() => ({
    id: `indicator:${instanceId}`, title: indicator.label,
    own: <IndicatorSettings definition={indicator.definition} instance={indicator.instance} hideStyles
      onConfigure={(patch) => actions.onConfigure(instanceId, patch)} onStyle={(key, style) => actions.onStyle(instanceId, key, style)}
      onDuplicate={() => actions.onDuplicate(instanceId)} onReset={() => actions.onReset(instanceId)} onRemove={() => { actions.onRemove(instanceId); onClose(); }} />,
    strokes: strokeFields(indicator, actions, true), fills: [],
    actions: { resetToDefault: () => actions.onReset(instanceId) },
    commit: () => undefined,
    cancel: () => actions.onRestore(snapshot),
  }), [indicator, actions, instanceId, snapshot, onClose]);
  return <ChartObjectSettings target={target} onClose={onClose} />;
}
