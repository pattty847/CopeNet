import { AlertCircle, WifiOff } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { Spinner } from './Spinner';

export function ConnectionBanner() {
  const wsStatus = useAppStore((state) => state.wsStatus);
  const authError = useAppStore((state) => state.authError);

  if (wsStatus === 'connected') return null;

  if (wsStatus === 'auth_failed') {
    return (
      <div className="mb-4 flex items-center gap-3 rounded-2xl border border-shell-error/30 bg-shell-error/8 px-4 py-3 text-sm text-shell-text">
        <AlertCircle className="w-4 h-4 text-operator-error" />
        <span className="text-operator-error">{authError || 'Authentication failed.'}</span>
      </div>
    );
  }

  return (
    <div className="mb-4 flex items-center gap-3 rounded-2xl border border-shell-border bg-shell-panel px-4 py-3 text-sm text-shell-text shadow-shell">
      {wsStatus === 'connecting' ? (
        <>
          <div className="scale-50 origin-left">
            <Spinner variant="bars" className="text-operator-accent" />
          </div>
          <span className="text-operator-accent">Connecting to backend...</span>
        </>
      ) : (
        <>
          <WifiOff className="w-4 h-4 text-operator-error" />
          <span className="text-operator-error">Disconnected. Retrying…</span>
        </>
      )}
    </div>
  );
}
