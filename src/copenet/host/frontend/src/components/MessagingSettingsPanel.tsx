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
import type { MessageDestination, PlatformConnectionStatus } from '../runtime/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PLATFORM_ICON: Record<string, string> = {
  telegram: '✈',
  slack: '#',
  discord: '◆',
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
}: {
  dest: MessageDestination;
  isDefault: boolean;
  onCompose: (target: string) => void;
}) {
  const [showDelete, setShowDelete] = useState(false);

  return (
    <div className="flex items-start gap-2.5 py-2.5 border-b border-operator-border/40 last:border-0">
      {/* Status dot */}
      <span className="mt-1 shrink-0">
        {dest.status === 'configured'
          ? <Wifi className="w-3 h-3 text-operator-success" />
          : <WifiOff className="w-3 h-3 text-operator-error" />
        }
      </span>

      {/* Info */}
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

      {/* Actions */}
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
          title="Edit destination"
          className="p-1.5 rounded-lg text-operator-muted hover:text-operator-text hover:bg-operator-panel transition-colors"
        >
          <Edit3 className="w-3 h-3" />
        </button>
        <button
          type="button"
          onClick={() => setShowDelete(!showDelete)}
          title="Remove destination"
          className="p-1.5 rounded-lg text-operator-muted hover:text-operator-error hover:bg-operator-error/8 transition-colors"
        >
          <Trash2 className="w-3 h-3" />
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

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function MessagingSettingsPanel() {
  const config = useMessagingConfig();
  const setComposerOpen = useAppStore((s) => s.setComposerOpen);
  const setComposerTarget = useAppStore((s) => s.setComposerTarget);
  const [showDestinations, setShowDestinations] = useState(true);

  const handleCompose = (target: string) => {
    setComposerTarget(target);
    setComposerOpen(true);
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
                />
              ))}
              {config.destinations.length === 0 && (
                <div className="py-3 text-center text-[11px] text-operator-muted">
                  No destinations configured.
                </div>
              )}
            </div>
            {/* Add destination */}
            <div className="border-t border-operator-border/40 px-2.5 py-2">
              <button
                type="button"
                className="flex items-center gap-1.5 text-[10px] font-semibold text-operator-muted hover:text-operator-accent transition-colors"
              >
                <Plus className="w-3 h-3" />
                Add destination
              </button>
              <div className="text-[9px] text-operator-muted/50 mt-0.5">
                Requires backend configuration — set chat ID in CopeNet config.
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Approval policy */}
      <ApprovalPolicySection />
    </div>
  );
}
