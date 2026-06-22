import { Brain, Check, Pencil, Plus, Save, Sparkles, Trash2, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { formatLowercaseRelativeAge } from '../../lib/formatting';
import { wsClient } from '../../lib/wsClient';
import { useAppStore } from '../../store/useAppStore';
import type { MemoryItem } from '../../types/backend';

const CATEGORY_LABELS: Record<MemoryItem['category'], string> = {
  preference: 'Preference',
  project_convention: 'Convention',
  ongoing_priority: 'Priority',
  fact: 'Fact',
};

const CATEGORY_OPTIONS: MemoryItem['category'][] = ['preference', 'project_convention', 'ongoing_priority', 'fact'];

export function MemorySurface() {
  const identityContext = useAppStore((state) => state.identityContext);
  const memoryItems = useAppStore((state) => state.memoryItems);
  const memoryDrafts = useAppStore((state) => state.memoryDrafts);
  const [composerOpen, setComposerOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  // When set, the composer is editing a model-proposed DRAFT — Save approves it.
  const [approvingDraftId, setApprovingDraftId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    category: 'preference' as MemoryItem['category'],
    title: '',
    summary: '',
    detail: '',
  });

  const visibleItems = useMemo(() => memoryItems.filter((item) => !item.archived).slice(0, 8), [memoryItems]);
  const drafts = useMemo(() => memoryDrafts.slice(0, 12), [memoryDrafts]);

  function beginCreate() {
    setEditingId(null);
    setApprovingDraftId(null);
    setForm({ category: 'preference', title: '', summary: '', detail: '' });
    setComposerOpen(true);
  }

  function beginEdit(item: MemoryItem) {
    setEditingId(item.id);
    setApprovingDraftId(null);
    setForm({
      category: item.category,
      title: item.title,
      summary: item.summary,
      detail: item.detail || '',
    });
    setComposerOpen(true);
  }

  function beginApproveEdit(item: MemoryItem) {
    setEditingId(null);
    setApprovingDraftId(item.id);
    setForm({
      category: item.category,
      title: item.title,
      summary: item.summary,
      detail: item.detail || '',
    });
    setComposerOpen(true);
  }

  async function save() {
    if (!form.title.trim() || !form.summary.trim()) return;
    setSaving(true);
    try {
      if (approvingDraftId) {
        await wsClient.approveMemory(approvingDraftId, {
          category: form.category,
          title: form.title,
          summary: form.summary,
          detail: form.detail || null,
        });
      } else {
        await wsClient.upsertMemory({
          id: editingId,
          category: form.category,
          title: form.title,
          summary: form.summary,
          detail: form.detail || undefined,
        });
      }
      setComposerOpen(false);
      setEditingId(null);
      setApprovingDraftId(null);
    } finally {
      setSaving(false);
    }
  }

  async function archive(item: MemoryItem) {
    await wsClient.archiveMemory(item.id, true);
  }

  async function approveDraft(item: MemoryItem) {
    await wsClient.approveMemory(item.id);
  }

  async function discardDraft(item: MemoryItem) {
    await wsClient.discardMemory(item.id);
  }

  return (
    <div className="shell-home-panel rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">Identity + Memory</div>
          <div className="mt-1 text-[12px] text-shell-muted">
            {identityContext?.stableIdentity ? 'CopeNet knows its operator context and remembers durable preferences.' : 'Memory stays user-visible and editable.'}
          </div>
        </div>
        <button
          type="button"
          onClick={composerOpen ? () => setComposerOpen(false) : beginCreate}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-shell-border bg-shell-panel-strong text-shell-muted transition-colors duration-150 hover:border-shell-accent/30 hover:text-shell-accent"
          title={composerOpen ? 'Close memory editor' : 'Add memory'}
        >
          {composerOpen ? <X className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
        </button>
      </div>

      <div className="mb-3 rounded-[16px] border border-shell-border bg-shell-panel-strong px-3 py-3">
        <div className="flex items-center gap-2 text-shell-text">
          <div className="flex h-7 w-7 items-center justify-center rounded-xl bg-shell-accent-soft text-shell-accent">
            <Brain className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[12px] font-medium">Identity prompt ready</div>
            <div className="truncate text-[11px] text-shell-muted" title={identityContext?.situationalBriefing || identityContext?.stableIdentity || undefined}>
              {identityContext?.situationalBriefing || identityContext?.stableIdentity || 'No operator identity overlay yet.'}
            </div>
          </div>
        </div>
      </div>

      {composerOpen && (
        <div className="mb-3 space-y-2 rounded-[18px] border border-shell-border bg-shell-panel-strong px-3 py-3">
          <div className="grid gap-2 sm:grid-cols-[120px_minmax(0,1fr)]">
            <select
              value={form.category}
              onChange={(event) => setForm((current) => ({ ...current, category: event.target.value as MemoryItem['category'] }))}
              className="rounded-[12px] border border-shell-border bg-shell-panel px-3 py-2 text-[12px] text-shell-text outline-none"
            >
              {CATEGORY_OPTIONS.map((category) => (
                <option key={category} value={category}>{CATEGORY_LABELS[category]}</option>
              ))}
            </select>
            <input
              value={form.title}
              onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
              placeholder="Memory title"
              className="rounded-[12px] border border-shell-border bg-shell-panel px-3 py-2 text-[12px] text-shell-text outline-none placeholder:text-shell-muted"
            />
          </div>
          <input
            value={form.summary}
            onChange={(event) => setForm((current) => ({ ...current, summary: event.target.value }))}
            placeholder="What should CopeNet remember?"
            className="w-full rounded-[12px] border border-shell-border bg-shell-panel px-3 py-2 text-[12px] text-shell-text outline-none placeholder:text-shell-muted"
          />
          <textarea
            value={form.detail}
            onChange={(event) => setForm((current) => ({ ...current, detail: event.target.value }))}
            placeholder="Optional detail"
            rows={3}
            className="w-full resize-none rounded-[12px] border border-shell-border bg-shell-panel px-3 py-2 text-[12px] text-shell-text outline-none placeholder:text-shell-muted"
          />
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving || !form.title.trim() || !form.summary.trim()}
              className="inline-flex items-center gap-1.5 rounded-[10px] border border-shell-accent/35 bg-shell-accent px-3 py-1.5 text-[11px] font-semibold text-[#1a1209] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Save className="h-3 w-3" />
              {approvingDraftId ? 'Approve memory' : editingId ? 'Update memory' : 'Save memory'}
            </button>
          </div>
        </div>
      )}

      {drafts.length > 0 && (
        <div className="mb-3 space-y-1.5 rounded-[18px] border border-shell-accent/30 bg-shell-accent-soft/40 px-3 py-3">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-shell-accent">
            <Sparkles className="h-3 w-3" />
            Proposed by CopeNet · awaiting your approval ({drafts.length})
          </div>
          {drafts.map((item) => (
            <div key={item.id} className="rounded-[14px] border border-shell-border bg-shell-panel px-3 py-2.5">
              <div className="flex items-center gap-2">
                <span className="rounded-full border border-shell-border bg-shell-panel-strong px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.16em] text-shell-accent">
                  {CATEGORY_LABELS[item.category]}
                </span>
                <span className="text-[10px] text-shell-muted">{formatLowercaseRelativeAge(item.updatedAt)}</span>
              </div>
              <div className="mt-1 text-[12px] font-medium text-shell-text">{item.title}</div>
              <div className="mt-0.5 text-[11px] leading-5 text-shell-muted">{item.summary}</div>
              <div className="mt-2 flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => void approveDraft(item)}
                  className="inline-flex items-center gap-1 rounded-[9px] border border-shell-accent/35 bg-shell-accent px-2.5 py-1 text-[10.5px] font-semibold text-[#1a1209] transition-colors hover:bg-shell-accent/90"
                >
                  <Check className="h-3 w-3" /> Approve
                </button>
                <button
                  type="button"
                  onClick={() => beginApproveEdit(item)}
                  className="inline-flex items-center gap-1 rounded-[9px] border border-shell-border px-2.5 py-1 text-[10.5px] font-semibold text-shell-muted transition-colors hover:border-shell-accent/30 hover:text-shell-accent"
                >
                  <Pencil className="h-3 w-3" /> Edit
                </button>
                <button
                  type="button"
                  onClick={() => void discardDraft(item)}
                  className="ml-auto inline-flex items-center gap-1 rounded-[9px] border border-shell-border px-2.5 py-1 text-[10.5px] font-semibold text-shell-muted transition-colors hover:border-shell-error/40 hover:text-shell-error"
                >
                  <X className="h-3 w-3" /> Discard
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-1.5">
        {visibleItems.length > 0 ? visibleItems.map((item) => (
          <div key={item.id} className="rounded-[14px] border border-shell-border bg-shell-panel-strong px-3 py-2.5">
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="rounded-full border border-shell-border bg-shell-panel px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.16em] text-shell-accent">
                    {CATEGORY_LABELS[item.category]}
                  </span>
                  <span className="text-[10px] text-shell-muted">{formatLowercaseRelativeAge(item.updatedAt)}</span>
                </div>
                <button type="button" onClick={() => beginEdit(item)} className="mt-1 block text-left text-[12px] font-medium text-shell-text hover:text-shell-accent">
                  {item.title}
                </button>
                <div className="mt-0.5 text-[11px] leading-5 text-shell-muted">{item.summary}</div>
              </div>
              <button
                type="button"
                onClick={() => void archive(item)}
                className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-lg border border-shell-border text-shell-muted transition-colors duration-150 hover:border-shell-accent/30 hover:text-shell-accent"
                title="Archive memory"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          </div>
        )) : (
          <div className="rounded-[16px] border border-dashed border-shell-border bg-shell-bg px-3 py-4 text-[12px] leading-5 text-shell-muted">
            No memory items yet. Save preferences, conventions, or active priorities here so CopeNet remembers them on purpose.
          </div>
        )}
      </div>
    </div>
  );
}
