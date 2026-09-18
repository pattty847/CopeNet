// Where the chart's selection meets the shared settings surfaces. Each kind of painted thing
// adapts itself (drawings, indicators, chart series); this only decides which one is showing.
// A selected drawing wins: it is the thing the operator most recently reached for.
import { useEffect } from 'react';
import { DeletedBar, SelectionBar } from './chartStyle/SelectionBar';
import { SeriesSettings, seriesBarModel, type ChartSeriesId } from './chartStyle/SeriesSettings';
import { useChartStyle } from './chartStyle/store';
import { DrawingSettings, drawingBarModel } from './drawings/DrawingSettings';
import type { ChartWorkspaceBridge } from './drawings/types';
import { IndicatorSettingsPopup, indicatorBarModel } from './indicators/IndicatorStyleable';
import type { ComputedIndicator } from './indicators/compute';
import type { IndicatorRowActions } from './indicators/IndicatorRows';

export type ChartPick = { kind: 'indicator'; instanceId: string; outputKey?: string } | { kind: 'series'; id: ChartSeriesId };

export function ChartSettingsLayer({ workspace, indicators, indicatorActions, overlayLabel, pick, settings, onPick, onSettings }: {
  workspace?: ChartWorkspaceBridge;
  indicators: ComputedIndicator[];
  indicatorActions?: IndicatorRowActions;
  overlayLabel?: string;
  pick: ChartPick | null;
  settings: ChartPick | null;
  onPick: (pick: ChartPick | null) => void;
  onSettings: (pick: ChartPick | null) => void;
}) {
  const style = useChartStyle();
  const drawing = workspace?.objects.find((object) => object.id === workspace.selectedObjectId) ?? null;
  const editing = workspace?.objects.find((object) => object.id === workspace.settingsObjectId) ?? null;
  const handlers = { openSettings: () => onSettings(pick), deselect: () => onPick(null) };
  const pickedIndicator = pick?.kind === 'indicator' ? indicators.find((indicator) => indicator.instanceId === pick.instanceId) : undefined;
  const settingsIndicator = settings?.kind === 'indicator' ? indicators.find((indicator) => indicator.instanceId === settings.instanceId) : undefined;
  // One selection at a time: reaching for a drawing lets go of a picked line.
  useEffect(() => { if (drawing && pick) onPick(null); }, [drawing, pick, onPick]);
  // Delete and Escape mean the same thing for a picked line as they do for a drawing.
  useEffect(() => {
    if (!pick || drawing || settings) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target?.tagName ?? '')) return;
      if (event.key === 'Escape') onPick(null);
      if ((event.key === 'Delete' || event.key === 'Backspace') && pick.kind === 'indicator') { event.preventDefault(); indicatorActions?.onRemove(pick.instanceId); onPick(null); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [pick, drawing, settings, indicatorActions, onPick]);
  return <>
    {workspace && drawing && <SelectionBar model={drawingBarModel(drawing, workspace)} />}
    {!drawing && pick?.kind === 'indicator' && pickedIndicator && indicatorActions &&
      <SelectionBar model={indicatorBarModel(pickedIndicator, pick.outputKey, indicatorActions, handlers)} />}
    {!drawing && pick?.kind === 'series' && <SelectionBar model={seriesBarModel(pick.id, style, overlayLabel, handlers)} />}
    {workspace && !drawing && !pick && workspace.deleted && <DeletedBar label={workspace.deleted.label} onUndo={() => workspace.onUndoDelete?.()} />}
    {workspace && editing && <DrawingSettings key={editing.id} object={editing} workspace={workspace} onClose={() => workspace.onOpenDrawingSettings?.(null)} />}
    {!editing && settingsIndicator && indicatorActions &&
      <IndicatorSettingsPopup key={settingsIndicator.instanceId} indicator={settingsIndicator} actions={indicatorActions} onClose={() => onSettings(null)} />}
    {!editing && settings?.kind === 'series' && <SeriesSettings key={settings.id} id={settings.id} overlayLabel={overlayLabel} onClose={() => onSettings(null)} />}
  </>;
}
