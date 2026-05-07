import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronUp,
  Edit3,
  Loader2,
  PenLine,
  Plus,
  RefreshCw,
  Send,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { wsClient } from '../lib/wsClient';
import { useMessagingConfig } from '../runtime/adapter';
import { useAppStore } from '../store/useAppStore';
import { MessagingRoutesSection } from './MessagingRoutesSection';
import type { MessageDestination, PlatformConnectionStatus } from '../runtime/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PLATFORM_ICON: Record<string, string> = {
  telegram: '✈',
  slack: '#',
  discord: '◆',
};

type DestinationDraft = {
  id?: string;
  platform: string;
  target: string;
  displayName: string;
  threadLabel: string;
  isDefault: boolean;
  requiresApproval: boolean;
};

function timeLabel(iso: string | null) {
  if (!iso) return null;
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const m = Math.floor(diffMs / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
}

function toDestinationDraft(dest?: MessageDestination | null): DestinationDraft {
  return {
    id: dest?.id,
    platform: dest?.platform || 'telegram',
    target: dest?.target || '',
    displayName: dest?.displayName || '',
    threadLabel: dest?.threadLabel || '',
    isDefault: dest?.isDefault ?? false,
    requiresApproval: dest?.requiresApproval ?? true,
  };
}

// ---------------------------------------------------------------------------
// Connection status badge
// ---------------------------------------------------------------------------

function ConnectionBadge({ status }: { status: PlatformConnectionStatus }) {
  const configs = {
    connected: { label: 'Connected', tone: 'text-operator-success', bg: 'bg-operator-success/10', icon: Wifi },
    disconnected: { label: 'Disconnected', tone: 'text-operator-muted', bg: 'bg-operator-panel', icon: WifiOff },
    error: { label: 'Error', tone: 'text-operator-error', bg: 'bg-operator-error/10', icon: AlertCircle },
    unconfigured: { label: 'Not configured', tone: 'text-operator-muted/60', bg: 'bg-operator-panel', icon: WifiOff },
  };
  const c = configs[status];
  const Icon = c.icon;
  return (
    <span className={`flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wider ${c.tone} ${c.bg} px-1.5 py-0.5 rounded border border-current/20`}>
      <Icon className="w-2.5 h-2.5" />
      {c.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Telegram platform section
// ---------------------------------------------------------------------------

function TelegramSection() {
  const config = useMessagingConfig();
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<'ok' | 'fail' | null>(null);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  if (!config) return null;
  const tg = config.telegram;

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    setTestMessage(null);
    try {
      const response = await wsClient.testMessagingPlatform('telegram');
      if (response.config) {
        useAppStore.getState().setMessagingConfig(response.config);
        useAppStore.getState().setDestinations(response.config.destinations);
      }
      setTestResult(response.result.ok ? 'ok' : 'fail');
      setTestMessage(response.result.message || null);
    } catch (error) {
      setTestResult('fail');
      setTestMessage(error instanceof Error ? error.message : 'Connection test failed.');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="rounded-xl border border-operator-border bg-operator-panel/30 overflow-hidden">
      {/* Platform header */}
      <div className="flex items-center gap-2.5 px-3 py-2.5 border-b border-operator-border/50">
        <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-operator-accent/10 text-operator-accent text-[13px]">
          {PLATFORM_ICON.telegram}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[12px] font-semibold text-operator-text">Telegram</div>
          {tg?.botUsername && (
            <div className="text-[10px] text-operator-muted font-mono">{tg.botUsername}</div>
          )}
        </div>
        {tg ? (
          <ConnectionBadge status={tg.connectionStatus} />
        ) : (
          <ConnectionBadge status="unconfigured" />
        )}
      </div>

      {/* Config detail */}
      {tg && (
        <div className="px-3 py-2 space-y-2">
          {/* Token row */}
          <div className="flex items-center gap-2">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted w-14 shrink-0">
              Token
            </div>
            <div className="flex-1 font-mono text-[10px] text-operator-muted bg-operator-bg rounded px-2 py-1 border border-operator-border">
              {tg.tokenMasked ?? '—'}
            </div>
          </div>

          {/* Last verified */}
          {tg.lastVerifiedAt && (
            <div className="flex items-center gap-2">
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted w-14 shrink-0">
                Verified
              </div>
              <div className="text-[10px] text-operator-muted">
                {timeLabel(tg.lastVerifiedAt)}
              </div>
            </div>
          )}

          {/* Error */}
          {tg.errorMessage && (
            <div className="rounded-lg border border-operator-error/25 bg-operator-error/6 px-2 py-1.5 text-[10px] text-operator-error">
              {tg.errorMessage}
            </div>
          )}

          {/* Test button */}
          <div className="flex items-center gap-2 pt-0.5">
            <button
              type="button"
              onClick={handleTest}
              disabled={testing}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold text-operator-muted border border-operator-border hover:text-operator-text hover:border-operator-accent/30 transition-colors disabled:opacity-50"
            >
              {testing
                ? <><Loader2 className="w-2.5 h-2.5 animate-spin" /> Testing…</>
                : <><RefreshCw className="w-2.5 h-2.5" /> Test connection</>
              }
            </button>
            {testResult === 'ok' && (
              <span className="flex items-center gap-1 text-[10px] text-operator-success">
                <Check className="w-2.5 h-2.5" /> OK
              </span>
            )}
            {testResult === 'fail' && (
              <span className="flex items-center gap-1 text-[10px] text-operator-error">
                <X className="w-2.5 h-2.5" /> Failed
              </span>
            )}
          </div>
          {testMessage && (
            <div className={`text-[10px] ${testResult === 'fail' ? 'text-operator-error' : 'text-operator-muted'}`}>
              {testMessage}
            </div>
          )}
        </div>
      )}

      {/* Unconfigured CTA */}
      {!tg && (
        <div className="px-3 py-3 text-center space-y-1.5">
          <div className="text-[11px] text-operator-muted">No Telegram bot configured</div>
          <button
            type="button"
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-semibold text-operator-accent border border-operator-accent/25 bg-operator-accent/8 hover:bg-operator-accent/15 transition-colors"
          >
            <Plus className="w-2.5 h-2.5" /> Configure bot token
          </button>
          <div className="text-[9px] text-operator-muted/60">
            Requires backend configuration — add bot token to CopeNet config.
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Destination row (editable-style, read-only for now)
// ---------------------------------------------------------------------------

function DestinationRow({
  dest,
  isDefault,
  onCompose,
  onEdit,
  onDelete,
}: {
  dest: MessageDestination;
  isDefault: boolean;
  onCompose: (target: string) => void;
  onEdit: (destination: MessageDestination) => void;
  onDelete: (destinationId: string) => Promise<void>;
}) {
  const [showDelete, setShowDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await onDelete(dest.id);
      setShowDelete(false);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="border-b border-operator-border/40 last:border-0">
      <div className="flex items-start gap-2.5 py-2.5">
        <span className="mt-1 shrink-0">
          {dest.status === 'configured'
            ? <Wifi className="w-3 h-3 text-operator-success" />
            : <WifiOff className="w-3 h-3 text-operator-error" />
          }
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-operator-accent">
              {PLATFORM_ICON[dest.platform] ?? '→'} {dest.platform}
            </span>
            {isDefault && (
              <span className="text-[9px] font-semibold uppercase tracking-wider bg-operator-accent/10 text-operator-accent rounded px-1 py-0.5">
                Default
              </span>
            )}
            {dest.requiresApproval ? (
              <span className="flex items-center gap-0.5 text-[9px] text-operator-accent ml-auto shrink-0">
                <ShieldAlert className="w-2.5 h-2.5" /> Approval
              </span>
            ) : (
              <span className="flex items-center gap-0.5 text-[9px] text-operator-success ml-auto shrink-0">
                <ShieldCheck className="w-2.5 h-2.5" /> Direct
              </span>
            )}
          </div>
          <div className="text-[12px] font-semibold text-operator-text mt-0.5 truncate">
            {dest.displayName}
          </div>
          {dest.threadLabel && (
            <div className="text-[10px] text-operator-muted">{dest.threadLabel}</div>
          )}
          <div className="text-[10px] font-mono text-operator-muted/60 truncate mt-0.5">
            {dest.target}
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => onCompose(dest.target)}
            title="Compose message"
            className="p-1.5 rounded-lg text-operator-muted hover:text-operator-accent hover:bg-operator-accent/8 transition-colors"
          >
            <PenLine className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={() => onEdit(dest)}
            title="Edit destination"
            className="p-1.5 rounded-lg text-operator-muted hover:text-operator-text hover:bg-operator-panel transition-colors"
          >
            <Edit3 className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={() => setShowDelete((v) => !v)}
            title="Remove destination"
            className="p-1.5 rounded-lg text-operator-muted hover:text-operator-error hover:bg-operator-error/8 transition-colors"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>
      {showDelete && (
        <div className="mb-2 rounded-lg border border-operator-error/20 bg-operator-error/5 px-2.5 py-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[10px] text-operator-muted">
              Remove <span className="text-operator-text">{dest.displayName}</span> from configured destinations?
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setShowDelete(false)}
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

function DestinationEditor({
  initial,
  onCancel,
  onSave,
}: {
  initial?: MessageDestination | null;
  onCancel: () => void;
  onSave: (draft: DestinationDraft) => Promise<void>;
}) {
  const [draft, setDraft] = useState<DestinationDraft>(toDestinationDraft(initial));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateDraft = <K extends keyof DestinationDraft>(key: K, value: DestinationDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const handleSave = async () => {
    if (!draft.target.trim()) {
      setError('Target is required.');
      return;
    }
    if (!draft.displayName.trim()) {
      setError('Display name is required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(draft);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Failed to save destination.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border border-operator-border/60 bg-operator-bg/70 px-2.5 py-2.5 space-y-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
        {draft.id ? 'Edit destination' : 'Add destination'}
      </div>
      <div className="grid gap-2">
        <label className="space-y-1">
          <span className="text-[10px] text-operator-muted">Display name</span>
          <input
            value={draft.displayName}
            onChange={(event) => updateDraft('displayName', event.target.value)}
            className="w-full rounded-lg border border-operator-border bg-operator-panel px-2 py-1.5 text-[11px] text-operator-text outline-none"
            placeholder="@copenet_ops"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[10px] text-operator-muted">Target</span>
          <input
            value={draft.target}
            onChange={(event) => updateDraft('target', event.target.value)}
            className="w-full rounded-lg border border-operator-border bg-operator-panel px-2 py-1.5 text-[11px] font-mono text-operator-text outline-none"
            placeholder="telegram:@copenet_ops"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[10px] text-operator-muted">Thread label (optional)</span>
          <input
            value={draft.threadLabel}
            onChange={(event) => updateDraft('threadLabel', event.target.value)}
            className="w-full rounded-lg border border-operator-border bg-operator-panel px-2 py-1.5 text-[11px] text-operator-text outline-none"
            placeholder="Alerts thread"
          />
        </label>
      </div>
      <div className="flex flex-wrap gap-3 text-[10px] text-operator-muted">
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={draft.isDefault}
            onChange={(event) => updateDraft('isDefault', event.target.checked)}
          />
          Default destination
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={draft.requiresApproval}
            onChange={(event) => updateDraft('requiresApproval', event.target.checked)}
          />
          Require approval
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
          {saving ? 'Saving…' : draft.id ? 'Save changes' : 'Add destination'}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Approval policy toggle
// ---------------------------------------------------------------------------

function ApprovalPolicySection() {
  const config = useMessagingConfig();
  const [defaultApproval, setDefaultApproval] = useState(
    config?.approvalPolicy?.requireApprovalByDefault ?? true,
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDefaultApproval(config.approvalPolicy?.requireApprovalByDefault ?? true);
  }, [config?.approvalPolicy?.requireApprovalByDefault]);

  if (!config) return null;

  const handleToggle = async () => {
    const next = !defaultApproval;
    setDefaultApproval(next);
    setSaving(true);
    try {
      const updated = await wsClient.updateMessagingApprovalPolicy({
        requireApprovalByDefault: next,
        hardlineBlocklist: config.approvalPolicy.hardlineBlocklist,
      });
      if (updated) {
        useAppStore.getState().setMessagingConfig(updated);
        useAppStore.getState().setDestinations(updated.destinations);
      }
    } catch {
      setDefaultApproval(config.approvalPolicy?.requireApprovalByDefault ?? true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted flex items-center gap-1.5">
        <Shield className="w-3 h-3" />
        Approval Policy
      </div>
      <div className="rounded-xl border border-operator-border bg-operator-panel/30 px-3 py-2.5 space-y-2">
        {/* Global toggle */}
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className="text-[11px] font-semibold text-operator-text">
              Require approval by default
            </div>
            <div className="text-[10px] text-operator-muted">
              All sends require operator approval unless overridden per destination.
            </div>
          </div>
          <button
            type="button"
            onClick={() => void handleToggle()}
            disabled={saving}
            className={`relative flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 ${
              defaultApproval ? 'bg-operator-accent' : 'bg-operator-border'
            } ${saving ? 'opacity-60' : ''}`}
          >
            <span
              className={`absolute h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                defaultApproval ? 'translate-x-4.5' : 'translate-x-0.5'
              }`}
            />
          </button>
        </div>

        {/* Per-destination note */}
        <div className="text-[9px] text-operator-muted/60 border-t border-operator-border/40 pt-1.5">
          Per-destination overrides set above take precedence.
          {!defaultApproval && (
            <span className="text-operator-accent font-medium ml-1">
              Warning: direct sends bypass operator review.
            </span>
          )}
          {saving && <span className="ml-1">Saving…</span>}
        </div>
      </div>
    </div>
  );
}

function TelegramRuntimeDefaultsSection() {
  const config = useMessagingConfig();
  const providers = useAppStore((state) => state.providers);
  const profiles = useAppStore((state) => state.profiles);
  const taskModes = useAppStore((state) => state.taskModes);
  const modelsByProvider = useAppStore((state) => state.modelsByProvider);
  const [saving, setSaving] = useState(false);
  const [provider, setProvider] = useState('');
  const [model, setModel] = useState('');
  const [systemPromptId, setSystemPromptId] = useState('');
  const [taskPromptId, setTaskPromptId] = useState('');

  useEffect(() => {
    if (!config) return;
    const fallbackProvider = providers.find((item) => item.available !== false)?.id || providers[0]?.id || '';
    setProvider(config.telegramDefaults?.provider || fallbackProvider);
    setModel(config.telegramDefaults?.model || '');
    setSystemPromptId(config.telegramDefaults?.systemPromptId || profiles.find((item) => item.id === 'default')?.id || profiles[0]?.id || '');
    setTaskPromptId(config.telegramDefaults?.taskPromptId || taskModes.find((item) => item.id === 'none')?.id || taskModes[0]?.id || '');
  }, [config, providers, profiles, taskModes]);

  useEffect(() => {
    if (provider) {
      void wsClient.loadModels(provider);
    }
  }, [provider]);

  if (!config) return null;

  const modelOptions = modelsByProvider[provider] || [];

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await wsClient.updateTelegramRuntimeDefaults({
        provider,
        model,
        systemPromptId,
        taskPromptId,
      });
      if (updated) {
        useAppStore.getState().setMessagingConfig(updated);
        useAppStore.getState().setDestinations(updated.destinations);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted flex items-center gap-1.5">
        <Send className="w-3 h-3" />
        Telegram Runtime
      </div>
      <div className="rounded-xl border border-operator-border bg-operator-panel/30 px-3 py-2.5 space-y-2">
        <div className="text-[10px] text-operator-muted">
          These defaults will seed future Telegram-originated sessions before slash-command overrides exist.
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="space-y-1">
            <span className="text-[10px] text-operator-muted">Provider</span>
            <select
              value={provider}
              onChange={(event) => {
                setProvider(event.target.value);
                setModel('');
              }}
              className="w-full rounded-lg border border-operator-border bg-operator-bg px-2 py-1.5 text-[11px] text-operator-text"
            >
              {providers.map((item) => (
                <option key={item.id} value={item.id}>{item.displayName}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-[10px] text-operator-muted">Model</span>
            <select
              value={model}
              onChange={(event) => setModel(event.target.value)}
              className="w-full rounded-lg border border-operator-border bg-operator-bg px-2 py-1.5 text-[11px] text-operator-text"
            >
              <option value="">Default model</option>
              {modelOptions.map((item) => (
                <option key={item.id} value={item.id}>{item.displayName}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-[10px] text-operator-muted">Profile</span>
            <select
              value={systemPromptId}
              onChange={(event) => setSystemPromptId(event.target.value)}
              className="w-full rounded-lg border border-operator-border bg-operator-bg px-2 py-1.5 text-[11px] text-operator-text"
            >
              {profiles.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-[10px] text-operator-muted">Task mode</span>
            <select
              value={taskPromptId}
              onChange={(event) => setTaskPromptId(event.target.value)}
              className="w-full rounded-lg border border-operator-border bg-operator-bg px-2 py-1.5 text-[11px] text-operator-text"
            >
              {taskModes.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving || !provider}
            className="px-2.5 py-1 rounded-lg text-[10px] font-semibold text-operator-accent border border-operator-accent/25 bg-operator-accent/8 disabled:opacity-60"
          >
            {saving ? 'Saving…' : 'Save Telegram defaults'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function MessagingSettingsPanel() {
  const config = useMessagingConfig();
  const setComposerOpen = useAppStore((s) => s.setComposerOpen);
  const setComposerTarget = useAppStore((s) => s.setComposerTarget);
  const [showDestinations, setShowDestinations] = useState(true);
  const [editingDestination, setEditingDestination] = useState<MessageDestination | null>(null);
  const [addingDestination, setAddingDestination] = useState(false);

  const handleCompose = (target: string) => {
    setComposerTarget(target);
    setComposerOpen(true);
  };

  const applyMessagingConfig = (nextConfig: ReturnType<typeof useMessagingConfig>) => {
    if (!nextConfig) return;
    useAppStore.getState().setMessagingConfig(nextConfig);
    useAppStore.getState().setDestinations(nextConfig.destinations);
  };

  const handleSaveDestination = async (draft: DestinationDraft) => {
    const response = await wsClient.upsertMessagingDestination({
      id: draft.id,
      platform: draft.platform,
      target: draft.target.trim(),
      displayName: draft.displayName.trim(),
      threadLabel: draft.threadLabel.trim() || null,
      isDefault: draft.isDefault,
      requiresApproval: draft.requiresApproval,
      status: 'configured',
    });
    applyMessagingConfig(response.config);
    setEditingDestination(null);
    setAddingDestination(false);
  };

  const handleDeleteDestination = async (destinationId: string) => {
    const response = await wsClient.deleteMessagingDestination(destinationId);
    applyMessagingConfig(response.config);
    if (editingDestination?.id === destinationId) {
      setEditingDestination(null);
    }
  };

  if (!config) {
    return (
      <div className="px-3 py-4 text-[11px] text-operator-muted text-center">
        Messaging not configured. Backend config not yet received.
      </div>
    );
  }

  const configuredCount = config.destinations.filter((d) => d.status === 'configured').length;

  return (
    <div className="space-y-3">
      {/* Platform section */}
      <div className="space-y-2">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted flex items-center gap-1.5">
          <Send className="w-3 h-3" />
          Platform
        </div>
        <TelegramSection />
        <div className="text-[9px] text-operator-muted/50 px-0.5">
          Additional platforms (Slack, Discord) can be added in a future version.
        </div>
      </div>

      {/* Destinations section */}
      <div className="space-y-2">
        <button
          type="button"
          onClick={() => setShowDestinations((v) => !v)}
          className="w-full flex items-center gap-1.5 group"
        >
          <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted group-hover:text-operator-text transition-colors flex items-center gap-1.5">
            <Wifi className="w-3 h-3 text-operator-success" />
            Destinations · {configuredCount} configured
          </div>
          <span className="ml-auto text-operator-muted group-hover:text-operator-text transition-colors">
            {showDestinations ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </span>
        </button>

        {showDestinations && (
          <div className="rounded-xl border border-operator-border bg-operator-panel/30 overflow-hidden">
            <div className="px-2.5">
              {config.destinations.map((dest) => (
                <DestinationRow
                  key={dest.id}
                  dest={dest}
                  isDefault={dest.isDefault}
                  onCompose={handleCompose}
                  onEdit={(destination) => {
                    setEditingDestination(destination);
                    setAddingDestination(false);
                  }}
                  onDelete={handleDeleteDestination}
                />
              ))}
              {config.destinations.length === 0 && (
                <div className="py-3 text-center text-[11px] text-operator-muted">
                  No destinations configured.
                </div>
              )}
              {editingDestination && (
                <div className="py-2">
                  <DestinationEditor
                    initial={editingDestination}
                    onCancel={() => setEditingDestination(null)}
                    onSave={handleSaveDestination}
                  />
                </div>
              )}
              {addingDestination && (
                <div className="py-2">
                  <DestinationEditor
                    onCancel={() => setAddingDestination(false)}
                    onSave={handleSaveDestination}
                  />
                </div>
              )}
            </div>
            {/* Add destination */}
            <div className="border-t border-operator-border/40 px-2.5 py-2">
              <button
                type="button"
                onClick={() => {
                  setAddingDestination((current) => !current);
                  setEditingDestination(null);
                }}
                className="flex items-center gap-1.5 text-[10px] font-semibold text-operator-muted hover:text-operator-accent transition-colors"
              >
                <Plus className="w-3 h-3" />
                {addingDestination ? 'Close destination form' : 'Add destination'}
              </button>
              <div className="text-[9px] text-operator-muted/50 mt-0.5">
                Add real chat targets here so compose and future agent messaging have an honest address book.
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Approval policy */}
      <ApprovalPolicySection />

      <TelegramRuntimeDefaultsSection />

      <MessagingRoutesSection />
    </div>
  );
}
