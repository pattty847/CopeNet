// Where the chart's selection meets the shared settings surfaces. Each kind of painted thing
// adapts itself (drawings, indicators, chart series); this only decides which one is showing.
import { DeletedBar, SelectionBar } from './chartStyle/SelectionBar';
import { DrawingSettings, drawingBarModel } from './drawings/DrawingSettings';
import type { ChartWorkspaceBridge } from './drawings/types';

export function ChartSettingsLayer({ workspace }: { workspace?: ChartWorkspaceBridge }) {
  const drawing = workspace?.objects.find((object) => object.id === workspace.selectedObjectId) ?? null;
  const editing = workspace?.objects.find((object) => object.id === workspace.settingsObjectId) ?? null;
  return <>
    {workspace && drawing && <SelectionBar model={drawingBarModel(drawing, workspace)} />}
    {workspace && !drawing && workspace.deleted && <DeletedBar label={workspace.deleted.label} onUndo={() => workspace.onUndoDelete?.()} />}
    {workspace && editing && <DrawingSettings key={editing.id} object={editing} workspace={workspace} onClose={() => workspace.onOpenDrawingSettings?.(null)} />}
  </>;
}
