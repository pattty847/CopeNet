// A drawing, described to the shared settings surfaces. The bar applies each change at once;
// the popup edits a draft that the canvas previews live, and Ok sends ONE update patch, so a
// whole editing session is one revision and one undo step.
import { useEffect, useMemo, useState } from 'react';
import type { ChartObject, DrawingPatch } from '../chartAgent/types';
import { ChartEvidenceViewer } from '../chartAgent/ChartEvidenceViewer';
import { futureDrawingTimes } from '../chartDecorations';
import { ChartObjectSettings } from '../chartStyle/ChartObjectSettings';
import type { SelectionBarModel } from '../chartStyle/SelectionBar';
import { readChartStyle, writeChartStyle } from '../chartStyle/store';
import type { FillField, StrokeField, Styleable } from '../chartStyle/types';
import { DEFAULT_DRAWING_COLOR, DRAWING_KINDS, SEGMENT_EXTENTS, fillOpacityOf, strokeOf } from './kinds';
import { drawingPatch } from './patch';
import type { ChartWorkspaceBridge } from './types';

const TIMEFRAMES: Array<{ value: ChartObject['timeframe']; label: string }> = [
  { value: 'D', label: 'Daily' }, { value: 'W', label: 'Weekly' }, { value: 'M', label: 'Monthly' },
];

function strokeField(object: ChartObject, change: (patch: DrawingPatch) => void): StrokeField {
  const stroke = strokeOf(object);
  return { key: 'stroke', label: 'Line', value: { color: object.color, ...stroke },
    onChange: (next) => change({ ...(next.color ? { color: next.color } : {}), ...(next.width ? { lineWidth: next.width } : {}), ...(next.style ? { lineStyle: next.style } : {}) }) };
}
function fillField(object: ChartObject, change: (patch: DrawingPatch) => void): FillField {
  return { key: 'fill', label: 'Fill', opacityOnly: true, value: { color: object.color, opacity: fillOpacityOf(object) },
    onChange: (next) => { if (next.opacity !== undefined) change({ fillOpacity: next.opacity }); } };
}
const titleOf = (object: ChartObject) => object.label || DRAWING_KINDS[object.kind].label;

export function drawingBarModel(object: ChartObject, workspace: ChartWorkspaceBridge): SelectionBarModel {
  const spec = DRAWING_KINDS[object.kind];
  const change = (patch: DrawingPatch) => workspace.onUpdate({ id: object.id, patch });
  return {
    id: object.id, title: titleOf(object), busy: workspace.interactionEnabled === false,
    stroke: spec.stroke ? strokeField(object, change) : { ...strokeField(object, change), colorOnly: true },
    fill: spec.fill ? fillField(object, change) : undefined,
    text: { value: object.label, onChange: (label) => change({ label }), openOnSelect: workspace.labelRequestId === object.id },
    lock: { value: object.locked === true, toggle: () => change({ locked: !object.locked }) },
    hide: () => { change({ visible: false }); workspace.onSelectObject(null); },
    remove: () => workspace.onDeleteObject(object.id),
    openSettings: () => workspace.onOpenDrawingSettings?.(object.id),
    deselect: () => workspace.onSelectObject(null),
  };
}

export function drawingStyleable(original: ChartObject, draft: ChartObject, setDraft: (next: ChartObject) => void, workspace: ChartWorkspaceBridge): Styleable {
  const spec = DRAWING_KINDS[draft.kind];
  const change = (patch: DrawingPatch) => setDraft({ ...draft, ...patch });
  const segment = SEGMENT_EXTENTS.some((entry) => entry.kind === draft.kind);
  const shown = draft.timeframes ?? [draft.timeframe];
  const bars = workspace.bars ?? [];
  return {
    id: `drawing:${original.id}`, title: titleOf(draft),
    // An agent drawing is a claim: why it was drawn and what it cites stay one tap away.
    ownLabel: 'Evidence',
    own: original.rationale || original.evidence.length ? <div className="cs-evidence">
      {original.rationale && <p>{original.rationale}</p>}
      {original.evidence.map((reference, index) => <ChartEvidenceViewer key={index} reference={reference} sessionKey={original.owner.sessionKey ?? null}
        documentId={workspace.documentId} includeAccountContext={workspace.includeAccountContext === true} />)}
    </div> : undefined,
    strokes: [spec.stroke ? strokeField(draft, change) : { ...strokeField(draft, change), colorOnly: true, label: 'Color' }],
    fills: spec.fill ? [fillField(draft, change)] : [],
    choices: segment ? [{ key: 'extent', label: 'Extend', value: draft.kind, choices: SEGMENT_EXTENTS.map(({ kind, label }) => ({ value: kind, label })),
      onChange: (kind) => change({ kind: kind as ChartObject['kind'] }) }] : [],
    toggles: [
      ...(segment || draft.kind === 'channel' ? [{ key: 'stats', label: 'Show stats on the chart', value: draft.showStats === true, onChange: (showStats: boolean) => change({ showStats }) }] : []),
      { key: 'locked', label: 'Lock anchors', value: draft.locked === true, onChange: (locked: boolean) => change({ locked }) },
    ],
    text: { value: draft.label, onChange: (label) => change({ label }) },
    anchors: { times: [...bars.map((bar) => bar.t), ...futureDrawingTimes(bars)],
      fields: draft.anchors.map((anchor, index) => ({ key: `anchor-${index}`, label: `Point ${index + 1}`, time: anchor.t, price: anchor.value,
        onChange: (next) => change({ anchors: draft.anchors.map((current, position) => position === index
          ? { ...current, t: next.time ?? current.t, value: next.price ?? current.value } : current) }) })) },
    visibility: TIMEFRAMES.map(({ value, label }) => ({ key: value, label, value: shown.includes(value),
      onChange: (on) => { const next = TIMEFRAMES.map((entry) => entry.value).filter((entry) => entry === value ? on : shown.includes(entry)); if (next.length) change({ timeframes: next }); } })),
    actions: {
      remove: () => workspace.onDeleteObject(original.id),
      saveAsDefault: () => { const style = readChartStyle(); writeChartStyle({ ...style, drawingDefaults: { ...style.drawingDefaults,
        [draft.kind]: { color: draft.color, lineWidth: draft.lineWidth, lineStyle: draft.lineStyle, fillOpacity: draft.fillOpacity } } }); },
      resetToDefault: () => setDraft({ ...draft, color: DEFAULT_DRAWING_COLOR, lineWidth: 1, lineStyle: draft.owner.kind === 'agent' ? 'dashed' : 'solid',
        fillOpacity: fillOpacityOf({ ...draft, fillOpacity: undefined }) }),
    },
    commit: () => { const patch = drawingPatch(original, draft); if (Object.keys(patch).length) workspace.onUpdate({ id: original.id, patch }); },
    cancel: () => undefined,
  };
}

export function DrawingSettings({ object, workspace, onClose }: { object: ChartObject; workspace: ChartWorkspaceBridge; onClose: () => void }) {
  const [draft, setDraft] = useState(object);
  const { onDraft } = workspace;
  useEffect(() => { onDraft?.(draft); }, [draft, onDraft]);
  useEffect(() => () => onDraft?.(null), [onDraft]);
  const target = useMemo(() => drawingStyleable(object, draft, setDraft, workspace), [object, draft, workspace]);
  return <ChartObjectSettings target={target} onClose={onClose} />;
}
