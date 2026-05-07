import { Edit3, MessageSquareShare, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { wsClient } from '../lib/wsClient';
import { useMessagingConfig } from '../runtime/adapter';
import { useAppStore } from '../store/useAppStore';
import type { Session, TelegramSessionRoute } from '../types/backend';

type RouteDraft = {
  id?: string;
  platform: string;
  chatId: string;
  threadId: string;
  sessionKey: string;
  titleOverride: string;
};

function toRouteDraft(route?: TelegramSessionRoute | null): RouteDraft {
  return {
    id: route?.id,
    platform: route?.platform || 'telegram',
    chatId: route?.chatId || '',
    threadId: route?.threadId || '',
    sessionKey: route?.sessionKey || '',
    titleOverride: route?.titleOverride || '',
  };
}

function sessionLabel(session: Session) {
  const model = session.model?.trim();
  return model ? `${session.title} · ${model}` : session.title;
}

function RouteRow({
  route,
  session,
  onEdit,
  onDelete,
}: {
  route: TelegramSessionRoute;
  session: Session | undefined;
  onEdit: (route: TelegramSessionRoute) => void;
  onDelete: (routeId: string) => Promise<void>;
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await onDelete(route.id);
      setConfirmingDelete(false);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="border-b border-operator-border/40 last:border-0 py-2.5">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 text-operator-accent">
          <MessageSquareShare className="w-3 h-3" />
        </span>
        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-operator-accent">
              Telegram route
            </span>
            {route.threadId && (
              <span className="text-[9px] font-semibold uppercase tracking-wider rounded px-1 py-0.5 bg-operator-panel text-operator-muted border border-operator-border/60">
                thread {route.threadId}
              </span>
            )}
          </div>
          <div className="text-[12px] font-mono text-operator-text truncate">{route.chatId}</div>
          <div className="text-[10px] text-operator-muted truncate">
            {session ? sessionLabel(session) : route.sessionKey}
          </div>
          {route.titleOverride && (
            <div className="text-[10px] text-operator-muted/70 truncate">
              title override: {route.titleOverride}
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => onEdit(route)}
            title="Edit route"
            className="p-1.5 rounded-lg text-operator-muted hover:text-operator-text hover:bg-operator-panel transition-colors"
          >
            <Edit3 className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={() => setConfirmingDelete((value) => !value)}
            title="Delete route"
            className="p-1.5 rounded-lg text-operator-muted hover:text-operator-error hover:bg-operator-error/8 transition-colors"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>
      {confirmingDelete && (
        <div className="mt-2 rounded-lg border border-operator-error/20 bg-operator-error/5 px-2.5 py-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[10px] text-operator-muted">
              Remove this Telegram route?
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setConfirmingDelete(false)}
                className="px-2 py-1 rounded text-[10px] font-semibold text-operator-muted hover:text-operator-text"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleDelete()}
                disabled={deleting}
                className="px-2 py-1 rounded text-[10px] font-semibold text-operator-error border border-operator-error/25 disabled:opacity-60"
              >
                {deleting ? 'Removing…' : 'Remove'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RouteEditor({
  initial,
  sessions,
  onCancel,
  onSave,
}: {
  initial?: TelegramSessionRoute | null;
  sessions: Session[];
  onCancel: () => void;
  onSave: (draft: RouteDraft) => Promise<void>;
}) {
  const [draft, setDraft] = useState<RouteDraft>(toRouteDraft(initial));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateDraft = <K extends keyof RouteDraft>(key: K, value: RouteDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const handleSave = async () => {
    if (!draft.chatId.trim()) {
      setError('Chat id is required.');
      return;
    }
    if (!draft.sessionKey.trim()) {
      setError('Mapped session is required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(draft);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Failed to save route.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border border-operator-border/60 bg-operator-bg/70 px-2.5 py-2.5 space-y-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
        {draft.id ? 'Edit Telegram route' : 'Add Telegram route'}
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        <label className="space-y-1 md:col-span-2">
          <span className="text-[10px] text-operator-muted">Chat id</span>
          <input
            value={draft.chatId}
            onChange={(event) => updateDraft('chatId', event.target.value)}
            className="w-full rounded-lg border border-operator-border bg-operator-panel px-2 py-1.5 text-[11px] font-mono text-operator-text outline-none"
            placeholder="-1001234567890"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[10px] text-operator-muted">Thread id (optional)</span>
          <input
            value={draft.threadId}
            onChange={(event) => updateDraft('threadId', event.target.value)}
            className="w-full rounded-lg border border-operator-border bg-operator-panel px-2 py-1.5 text-[11px] font-mono text-operator-text outline-none"
            placeholder="42"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[10px] text-operator-muted">Mapped session</span>
          <select
            value={draft.sessionKey}
            onChange={(event) => updateDraft('sessionKey', event.target.value)}
            className="w-full rounded-lg border border-operator-border bg-operator-panel px-2 py-1.5 text-[11px] text-operator-text outline-none"
          >
            <option value="">Choose session…</option>
            {sessions.map((session) => (
              <option key={session.key} value={session.key}>{sessionLabel(session)}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1 md:col-span-2">
          <span className="text-[10px] text-operator-muted">Title override (optional)</span>
          <input
            value={draft.titleOverride}
            onChange={(event) => updateDraft('titleOverride', event.target.value)}
            className="w-full rounded-lg border border-operator-border bg-operator-panel px-2 py-1.5 text-[11px] text-operator-text outline-none"
            placeholder="Ops backchannel"
          />
        </label>
      </div>
      {error && <div className="text-[10px] text-operator-error">{error}</div>}
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-2.5 py-1 rounded-lg text-[10px] font-semibold text-operator-muted hover:text-operator-text"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
          className="px-2.5 py-1 rounded-lg text-[10px] font-semibold text-operator-accent border border-operator-accent/25 bg-operator-accent/8 disabled:opacity-60"
        >
          {saving ? 'Saving…' : draft.id ? 'Save route' : 'Add route'}
        </button>
      </div>
    </div>
  );
}

export function MessagingRoutesSection() {
  const config = useMessagingConfig();
  const sessions = useAppStore((state) => state.sessions);
  const [showRoutes, setShowRoutes] = useState(true);
  const [editingRoute, setEditingRoute] = useState<TelegramSessionRoute | null>(null);
  const [addingRoute, setAddingRoute] = useState(false);

  if (!config) return null;

  const applyRoutes = (routes: TelegramSessionRoute[]) => {
    const current = useAppStore.getState().messagingConfig;
    if (!current) return;
    useAppStore.getState().setMessagingConfig({ ...current, routes });
  };

  const handleSaveRoute = async (draft: RouteDraft) => {
    const response = await wsClient.upsertMessagingRoute({
      id: draft.id,
      platform: draft.platform,
      chatId: draft.chatId.trim(),
      threadId: draft.threadId.trim() || null,
      sessionKey: draft.sessionKey.trim(),
      titleOverride: draft.titleOverride.trim() || null,
    });
    applyRoutes(response.routes);
    setEditingRoute(null);
    setAddingRoute(false);
  };

  const handleDeleteRoute = async (routeId: string) => {
    const response = await wsClient.deleteMessagingRoute(routeId);
    applyRoutes(response.routes);
    if (editingRoute?.id === routeId) {
      setEditingRoute(null);
    }
  };

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setShowRoutes((value) => !value)}
        className="w-full flex items-center gap-1.5 group"
      >
        <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted group-hover:text-operator-text transition-colors flex items-center gap-1.5">
          <MessageSquareShare className="w-3 h-3 text-operator-accent" />
          Telegram Session Routes · {config.routes.length}
        </div>
      </button>
      {showRoutes && (
        <div className="rounded-xl border border-operator-border bg-operator-panel/30 overflow-hidden">
          <div className="px-2.5">
            {config.routes.map((route) => (
              <RouteRow
                key={route.id}
                route={route}
                session={sessions.find((session) => session.key === route.sessionKey)}
                onEdit={(nextRoute) => {
                  setEditingRoute(nextRoute);
                  setAddingRoute(false);
                }}
                onDelete={handleDeleteRoute}
              />
            ))}
            {config.routes.length === 0 && (
              <div className="py-3 text-center text-[11px] text-operator-muted">
                No Telegram chat routes configured yet.
              </div>
            )}
            {editingRoute && (
              <div className="py-2">
                <RouteEditor
                  initial={editingRoute}
                  sessions={sessions}
                  onCancel={() => setEditingRoute(null)}
                  onSave={handleSaveRoute}
                />
              </div>
            )}
            {addingRoute && (
              <div className="py-2">
                <RouteEditor
                  sessions={sessions}
                  onCancel={() => setAddingRoute(false)}
                  onSave={handleSaveRoute}
                />
              </div>
            )}
          </div>
          <div className="border-t border-operator-border/40 px-2.5 py-2">
            <button
              type="button"
              onClick={() => {
                setAddingRoute((current) => !current);
                setEditingRoute(null);
              }}
              className="flex items-center gap-1.5 text-[10px] font-semibold text-operator-muted hover:text-operator-accent transition-colors"
            >
              <Plus className="w-3 h-3" />
              {addingRoute ? 'Close route form' : 'Add Telegram route'}
            </button>
            <div className="text-[9px] text-operator-muted/50 mt-0.5">
              Map one Telegram chat or thread to a specific CopeNet session before inbound routing goes live.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
