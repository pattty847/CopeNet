import { Eye, EyeOff, Settings2, Trash2, Undo2 } from 'lucide-react';
import type { ChartWorkspaceController } from './useChartWorkspace';

export function ChartDrawingsPanel({ workspace }: { workspace: ChartWorkspaceController }) {
  const objects = workspace.document?.objects ?? [];
  const render = workspace.renderStatus.find((receipt) => receipt.viewId === workspace.viewId && receipt.revision === workspace.document?.revision);
  const selected = objects.find((object) => object.id === workspace.selectedObjectId);
  return <section className="ca-drawings" aria-label="Chart drawings">
    <div className="ca-section-head"><span>Drawings <small>{objects.length}</small></span>
      {workspace.batches[0] && <button title="Undo latest drawing batch" onClick={() => void workspace.undo(workspace.batches[0].batchId)} disabled={workspace.busy}><Undo2 size={13} /> Undo batch</button>}
    </div>
    {workspace.document && <p className="ca-muted" role="status">Revision {workspace.document.revision} · {render?.status === 'rendered' ? 'Painted in this view' : render?.status === 'hidden' ? 'Saved · hidden in this view' : render?.status === 'failed' ? 'Saved · rendering failed' : 'Saved · awaiting paint receipt'}{render?.reason ? ` · ${render.reason}` : ''}</p>}
    {!objects.length && <p className="ca-muted">Ask the agent to mark a level, or use a drawing tool above the chart.</p>}
    {objects.map((object) => <div className="ca-object-row" data-selected={selected?.id === object.id} key={object.id}>
      <button className="ca-object-name" onClick={() => workspace.setSelectedObjectId(selected?.id === object.id ? null : object.id)}>
        <i style={{ background: object.color }} /><span>{object.label || object.kind}<small>{object.timeframe} · {object.owner.kind === 'agent' ? 'Agent' : 'You'}</small></span>
      </button>
      <button aria-label={`${object.visible ? 'Hide' : 'Show'} ${object.label}`} onClick={() => void workspace.apply([{ kind: 'update', objectId: object.id, patch: { visible: !object.visible } }])} disabled={workspace.busy}>{object.visible ? <Eye size={13} /> : <EyeOff size={13} />}</button>
      <button aria-label={`Settings for ${object.label}`} onClick={() => workspace.bridge?.onOpenDrawingSettings?.(object.id)}><Settings2 size={13} /></button>
      <button aria-label={`Delete ${object.label}`} onClick={() => void workspace.apply([{ kind: 'delete', objectId: object.id }])} disabled={workspace.busy}><Trash2 size={13} /></button>
    </div>)}
    {workspace.batches.length > 1 && <details className="ca-batches"><summary>Recent drawing batches</summary>
      {workspace.batches.slice(0, 12).map((batch) => <div key={batch.batchId}><span>Revision {batch.revision}</span><button title={batch.batchId} onClick={() => void workspace.undo(batch.batchId)} disabled={workspace.busy}>Undo this batch</button></div>)}
    </details>}
  </section>;
}
