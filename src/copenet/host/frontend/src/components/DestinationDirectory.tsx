import { Check, PenLine, ShieldAlert, ShieldCheck, Wifi, WifiOff } from 'lucide-react';
import { useDestinations } from '../runtime/adapter';
import { useAppStore } from '../store/useAppStore';
import type { MessageDestination } from '../types/backend';

const PLATFORM_LABELS: Record<string, { label: string; color: string }> = {
  telegram: { label: 'Telegram', color: 'text-operator-accent' },
  slack: { label: 'Slack', color: 'text-operator-success' },
  discord: { label: 'Discord', color: 'text-operator-accent' },
};

function DestinationRow({ dest }: { dest: MessageDestination }) {
  const setComposerOpen = useAppStore((s) => s.setComposerOpen);
  const setComposerTarget = useAppStore((s) => s.setComposerTarget);
  const platform = PLATFORM_LABELS[dest.platform] ?? { label: dest.platform, color: 'text-operator-muted' };

  const openComposer = () => {
    setComposerTarget(dest.target);
    setComposerOpen(true);
  };

  return (
    <div className="flex items-start gap-2.5 py-2 border-b border-operator-border/50 last:border-0">
      {/* Status dot */}
      <span className="mt-1 shrink-0">
        {dest.status === 'configured' ? (
          <Wifi className="w-3 h-3 text-operator-success" />
        ) : (
          <WifiOff className="w-3 h-3 text-operator-error" />
        )}
      </span>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`text-[10px] font-semibold uppercase tracking-wider ${platform.color}`}>
            {platform.label}
          </span>
          {dest.isDefault && (
            <span className="text-[9px] font-semibold uppercase tracking-wider bg-operator-accent/10 text-operator-accent rounded px-1 py-0.5">
              Default
            </span>
          )}
          {dest.requiresApproval ? (
            <span className="flex items-center gap-0.5 text-[9px] text-operator-accent ml-auto shrink-0">
              <ShieldAlert className="w-2.5 h-2.5" />
              Approval required
            </span>
          ) : (
            <span className="flex items-center gap-0.5 text-[9px] text-operator-success ml-auto shrink-0">
              <ShieldCheck className="w-2.5 h-2.5" />
              Direct send
            </span>
          )}
        </div>
        <div className="text-[12px] font-medium text-operator-text mt-0.5 truncate">{dest.displayName}</div>
        {dest.threadLabel && (
          <div className="text-[10px] text-operator-muted">{dest.threadLabel}</div>
        )}
        <div className="text-[10px] font-mono text-operator-muted/70 truncate mt-0.5">{dest.target}</div>
      </div>

      {/* Compose shortcut */}
      <button
        type="button"
        onClick={openComposer}
        title={`Compose message to ${dest.displayName}`}
        className="shrink-0 mt-0.5 p-1.5 rounded-lg text-operator-muted hover:text-operator-accent hover:bg-operator-accent/8 transition-colors duration-150"
      >
        <PenLine className="w-3 h-3" />
      </button>
    </div>
  );
}

interface DestinationDirectoryProps {
  onCompose?: () => void;
}

export function DestinationDirectory({ onCompose }: DestinationDirectoryProps) {
  const destinations = useDestinations();
  const setComposerOpen = useAppStore((s) => s.setComposerOpen);

  const configured = destinations.filter((d) => d.status === 'configured');
  const unconfigured = destinations.filter((d) => d.status !== 'configured');

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted flex items-center gap-1.5">
          <Check className="w-3 h-3 text-operator-success" />
          Messaging · {configured.length} configured
        </div>
        <button
          type="button"
          onClick={() => { setComposerOpen(true); if (onCompose) onCompose(); }}
          className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-semibold text-operator-accent bg-operator-accent/10 hover:bg-operator-accent/20 border border-operator-accent/20 transition-colors duration-150"
        >
          <PenLine className="w-2.5 h-2.5" />
          Compose
        </button>
      </div>

      <div className="bg-operator-panel/40 rounded-xl border border-operator-border px-2.5 py-0.5">
        {configured.map((dest) => (
          <DestinationRow key={dest.id} dest={dest} />
        ))}
        {configured.length === 0 && (
          <div className="py-3 text-center text-[11px] text-operator-muted">
            No destinations configured.
          </div>
        )}
      </div>

      {unconfigured.length > 0 && (
        <div className="text-[10px] text-operator-muted/60 px-1">
          {unconfigured.length} destination{unconfigured.length > 1 ? 's' : ''} not yet configured.
        </div>
      )}
    </div>
  );
}
