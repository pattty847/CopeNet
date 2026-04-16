import { AlertCircle, WifiOff } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { Spinner } from './Spinner';

export function ConnectionBanner() {
  const wsStatus = useAppStore((state) => state.wsStatus);
  const authError = useAppStore((state) => state.authError);

  if (wsStatus === 'connected') return null;

  if (wsStatus === 'auth_failed') {
    return (
      <div className="animate-fade-in-up mb-3 flex items-center gap-2.5 rounded-xl border border-shell-error/25 bg-shell-error/6 px-3.5 py-2.5 text-[13px] text-shell-text">
        <AlertCircle className="w-3.5 h-3.5 text-operator-error shrink-0" />
        <span className="text-operator-error">{authError || 'Authentication failed.'}</span>
      </div>
    );
  }

  return (
    <div className="animate-fade-in-up mb-3 flex items-center gap-2.5 rounded-xl border border-shell-border bg-shell-panel px-3.5 py-2.5 text-[13px] text-shell-text shadow-shell">
      {wsStatus === 'connecting' ? (
        <>
          <div className="scale-50 origin-left">
            <Spinner variant="bars" className="text-operator-accent" />
          </div>
          <span className="text-operator-accent font-medium">Connecting to backend…</span>
        </>
      ) : (
        <>
          <WifiOff className="w-3.5 h-3.5 text-operator-error shrink-0" />
          <span className="text-operator-error font-medium">Disconnected. Retrying…</span>
        </>
      )}
    </div>
  );
}
