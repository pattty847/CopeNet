import { AlertCircle, WifiOff } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { Spinner } from './Spinner';

export function ConnectionBanner() {
  const wsStatus = useAppStore((state) => state.wsStatus);
  const authError = useAppStore((state) => state.authError);

  if (wsStatus === 'connected') return null;

  if (wsStatus === 'auth_failed') {
    return (
      <div className="bg-operator-error/10 border-b border-operator-error/30 text-operator-text px-4 py-2 flex items-center gap-3 text-sm font-mono">
        <AlertCircle className="w-4 h-4 text-operator-error" />
        <span className="text-operator-error">{authError || 'Authentication failed.'}</span>
      </div>
    );
  }

  return (
    <div className="bg-operator-error/10 border-b border-operator-error/30 text-operator-text px-4 py-2 flex items-center gap-3 text-sm font-mono">
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
