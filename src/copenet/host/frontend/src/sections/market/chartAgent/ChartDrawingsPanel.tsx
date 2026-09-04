import { ChartEvidenceViewer } from './ChartEvidenceViewer';
import { useState } from 'react';
import { Eye, EyeOff, Trash2, Undo2 } from 'lucide-react';
import type { ChartObject } from './types';
import type { ChartWorkspaceController } from './useChartWorkspace';

function DrawingEditor({ object, workspace }: { object: ChartObject; workspace: ChartWorkspaceController }) {
  const [label, setLabel] = useState(object.label);
  const [anchors, setAnchors] = useState(object.anchors);
  const [revision] = useState(workspace.document?.revision);
  const [error, setError] = useState<string | null>(null);
  return <form className="ca-object-editor" onSubmit={(event) => {
    event.preventDefault();
    if (revision !== workspace.document?.revision) { setError('The chart changed while you edited. Select the drawing again to refresh.'); return; }
    if (anchors.some((anchor) => !Number.isFinite(anchor.value) || anchor.value <= 0)) { setError('Enter a positive price for each anchor.'); return; }
    void workspace.apply([{ kind: 'update', objectId: object.id, patch: { label, anchors } }]);
  }}>
    <label>Label<input value={label} maxLength={200} onChange={(event) => setLabel(event.target.value)} /></label>
    {anchors.map((anchor, index) => <label key={index}>Anchor {index + 1} · {new Date(anchor.t * 1000).toLocaleDateString()}
      <input type="number" step="any" value={anchor.value} onChange={(event) => setAnchors((current) => current.map((value, i) => i === index ? { ...value, value: Number(event.target.value) } : value))} />
    </label>)}
    {object.rationale && <p>{object.rationale}</p>}
    {object.evidence.length > 0 && <details><summary>Evidence · {object.evidence.length} references</summary>
      {object.evidence.map((reference, index) => <ChartEvidenceViewer key={index} reference={reference} sessionKey={object.owner.sessionKey ?? null} documentId={workspace.document!.documentId} includeAccountContext={workspace.includeAccountContext} />)}
    </details>}
    <small>{object.owner.kind === 'agent' ? 'Agent layer · manual edits protect this object from later agent changes.' : 'Your drawing · protected from agent changes.'}</small>
    {error && <p role="alert" className="ca-error">{error}</p>}
    <button type="submit" disabled={workspace.busy}>Save drawing</button>
  </form>;
}

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
      <button aria-label={`Delete ${object.label}`} onClick={() => void workspace.apply([{ kind: 'delete', objectId: object.id }])} disabled={workspace.busy}><Trash2 size={13} /></button>
    </div>)}
    {workspace.batches.length > 1 && <details className="ca-batches"><summary>Recent drawing batches</summary>
      {workspace.batches.slice(0, 12).map((batch) => <div key={batch.batchId}><span>Revision {batch.revision}</span><button title={batch.batchId} onClick={() => void workspace.undo(batch.batchId)} disabled={workspace.busy}>Undo this batch</button></div>)}
    </details>}
    {selected && <DrawingEditor key={selected.id} object={selected} workspace={workspace} />}
  </section>;
}
