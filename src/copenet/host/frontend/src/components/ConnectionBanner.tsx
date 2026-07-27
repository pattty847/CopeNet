import { FormEvent, useState } from 'react';
import { AlertCircle, KeyRound, WifiOff } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { Spinner } from './Spinner';

export function ConnectionBanner() {
  const wsStatus = useAppStore((state) => state.wsStatus);
  const authError = useAppStore((state) => state.authError);

  if (wsStatus === 'connected') return null;

  if (wsStatus === 'auth_failed') {
    return <GatewayTokenForm authError={authError} />;
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

export function GatewayTokenForm({ authError }: { authError: string | null }) {
  const [token, setToken] = useState('');
  const [tokenError, setTokenError] = useState<string | null>(null);

  const handleTokenSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = token.trim();
    if (!normalized) {
      setTokenError('Enter the private token from your CopeNet .copenet.env file.');
      return;
    }
    window.localStorage.setItem('copnet.token', normalized);
    window.location.reload();
  };

  return (
    <div className="animate-fade-in-up mb-3 rounded-xl border border-shell-error/25 bg-shell-error/6 px-3.5 py-3 text-[13px] text-shell-text">
      <div className="flex items-start gap-2.5">
        <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-operator-error" />
        <div className="min-w-0">
          <div className="font-semibold text-operator-error">{authError || 'Authentication failed.'}</div>
          <div className="mt-0.5 text-[11px] leading-5 text-shell-muted">
            Enter the private gateway token once. It stays in this browser and is never added to the URL.
          </div>
        </div>
      </div>
      <form onSubmit={handleTokenSubmit} className="mt-2.5 flex flex-col gap-2 sm:flex-row sm:items-start">
        <label className="min-w-0 flex-1">
          <span className="sr-only">Gateway token</span>
          <span className="relative block">
            <KeyRound className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-shell-muted" />
            <input
              type="password"
              name="gateway-token"
              value={token}
              onChange={(event) => {
                setToken(event.target.value);
                if (tokenError) setTokenError(null);
              }}
              autoComplete="current-password"
              spellCheck={false}
              placeholder="Gateway token"
              aria-invalid={tokenError ? true : undefined}
              aria-describedby={tokenError ? 'gateway-token-error' : undefined}
              className="h-9 w-full rounded-lg border border-shell-border bg-shell-panel pl-8 pr-3 text-[12px] text-shell-text outline-none transition-colors placeholder:text-shell-muted/60 focus:border-operator-accent/45"
            />
          </span>
          {tokenError ? (
            <span id="gateway-token-error" className="mt-1 block text-[10.5px] text-operator-error">
              {tokenError}
            </span>
          ) : null}
        </label>
        <button
          type="submit"
          className="h-9 shrink-0 rounded-lg bg-operator-accent px-3.5 text-[11px] font-semibold text-operator-bg transition-opacity hover:opacity-90"
        >
          Save & reconnect
        </button>
      </form>
    </div>
  );
}
