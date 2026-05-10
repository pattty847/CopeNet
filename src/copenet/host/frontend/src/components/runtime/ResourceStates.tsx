import { AlertTriangle, LucideIcon } from 'lucide-react';

// Shared loading/empty/error visuals for runtime panels. Kept terse and
// aligned with the CopeNet operator styling (panels, accent, muted muted
// copy). All three share the same vertical rhythm so switching between
// them doesn't jolt the layout.

interface StateShellProps {
  icon: LucideIcon;
  title: string;
  body: string;
  tone?: 'muted' | 'accent' | 'error';
}

function StateShell({ icon: Icon, title, body, tone = 'muted' }: StateShellProps) {
  const iconTone =
    tone === 'error'
      ? 'text-operator-error'
      : tone === 'accent'
      ? 'text-operator-accent'
      : 'text-operator-muted/80';
  const bgTone =
    tone === 'error'
      ? 'bg-operator-error/8'
      : tone === 'accent'
      ? 'bg-operator-accent/8'
      : 'bg-operator-panel/60';
  return (
    <div className="px-4 py-10 text-center">
      <div className={`mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-2xl ${bgTone} ${iconTone}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="text-[12.5px] text-operator-text font-medium mb-1.5">{title}</div>
      <div className="text-[11.5px] text-operator-muted/85 leading-relaxed max-w-[260px] mx-auto">
        {body}
      </div>
    </div>
  );
}

export function LoadingState({ label = 'Loading runtime state…' }: { label?: string }) {
  return (
    <div className="px-3 py-4 space-y-2">
      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-operator-muted/85 mb-1">
        {label}
      </div>
      <div className="shimmer rounded-xl bg-operator-panel/40 h-12" />
      <div className="shimmer rounded-xl bg-operator-panel/30 h-9" />
      <div className="shimmer rounded-xl bg-operator-panel/20 h-9" />
    </div>
  );
}

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  body: string;
}

export function EmptyState({ icon, title, body }: EmptyStateProps) {
  return <StateShell icon={icon} title={title} body={body} tone="muted" />;
}

interface ErrorStateProps {
  title?: string;
  message: string;
}

export function ErrorState({ title = 'Could not load runtime state', message }: ErrorStateProps) {
  return <StateShell icon={AlertTriangle} title={title} body={message} tone="error" />;
}
