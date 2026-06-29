import { Check, FileText, Trash2, UserPen } from 'lucide-react';
import { useMemo, useState } from 'react';
import { formatLowercaseRelativeAge } from '../../lib/formatting';
import { wsClient } from '../../lib/wsClient';
import { useAppStore } from '../../store/useAppStore';

// USER.md proposals — model-proposed identity deltas the operator reviews. Approving
// merges the delta into the active persona's USER.md; discarding drops it.
export function UserNotesSurface() {
  const userNoteDrafts = useAppStore((state) => state.userNoteDrafts);
  const [busyId, setBusyId] = useState<string | null>(null);
  const drafts = useMemo(() => userNoteDrafts.slice(0, 12), [userNoteDrafts]);

  async function approve(id: string) {
    setBusyId(id);
    try {
      await wsClient.approveUserNote(id);
    } finally {
      setBusyId(null);
    }
  }

  async function discard(id: string) {
    setBusyId(id);
    try {
      await wsClient.discardUserNote(id);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="shell-home-panel rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">USER.md</div>
          <div className="mt-1 text-[12px] text-shell-muted">
            Who CopeNet knows you to be. Proposed edits land here for your review.
          </div>
        </div>
        <UserPen className="mt-0.5 h-3.5 w-3.5 shrink-0 text-shell-accent/60" />
      </div>

      {drafts.length === 0 ? (
        <div className="rounded-[14px] border border-dashed border-shell-border bg-shell-bg px-3 py-3 text-[11px] text-shell-muted">
          No proposed USER.md updates. CopeNet proposes durable identity edits with{' '}
          <span className="font-medium text-shell-text">user.remember</span>; they appear here for you to approve.
        </div>
      ) : (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-shell-accent">
            <FileText className="h-3 w-3" />
            Proposed by CopeNet · awaiting your approval ({drafts.length})
          </div>
          {drafts.map((item) => (
            <div key={item.id} className="rounded-[14px] border border-shell-border bg-shell-panel-strong px-3 py-2.5">
              <div className="flex items-center gap-1.5">
                <span className="rounded-full bg-shell-accent-soft px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-shell-accent">
                  {item.targetSection}
                </span>
                <span className="ml-auto text-[10px] text-shell-muted">{formatLowercaseRelativeAge(item.createdAt)}</span>
              </div>
              <div className="mt-1.5 text-[12px] font-medium text-shell-text">{item.summary}</div>
              <pre className="mt-1 max-h-28 overflow-auto whitespace-pre-wrap rounded-[10px] border border-shell-border bg-shell-bg px-2.5 py-1.5 text-[11px] leading-snug text-shell-muted">
                {item.body}
              </pre>
              <div className="mt-2 flex items-center gap-1.5">
                <button
                  type="button"
                  disabled={busyId === item.id}
                  onClick={() => void approve(item.id)}
                  className="inline-flex items-center gap-1 rounded-[9px] border border-shell-accent/35 bg-shell-accent px-2.5 py-1 text-[10.5px] font-semibold text-[#1a1209] transition-colors hover:bg-shell-accent/90 disabled:opacity-50"
                >
                  <Check className="h-3 w-3" /> Approve
                </button>
                <button
                  type="button"
                  disabled={busyId === item.id}
                  onClick={() => void discard(item.id)}
                  className="ml-auto inline-flex items-center gap-1 rounded-[9px] border border-shell-border px-2.5 py-1 text-[10.5px] font-semibold text-shell-muted transition-colors hover:border-shell-error/40 hover:text-shell-error disabled:opacity-50"
                >
                  <Trash2 className="h-3 w-3" /> Discard
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
