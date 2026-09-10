import { FormEvent, useState, type RefObject } from 'react';
import { KeyRound, Trash2 } from 'lucide-react';
import { TOKEN_STORAGE_KEY } from '../lib/wsConnectionConfig';
import { FloatingPopover } from './FloatingPopover';

function maskedToken(value: string): string {
  return value.length <= 4 ? '••••' : `•••• ${value.slice(-4)}`;
}

/** The only place to change the gateway token once the initial auth banner is dismissed.
 *  Before this, a token typo or a rotated `.copenet.env` value had no in-app recovery path
 *  short of clearing site data. */
export function AccountMenu({ anchorRef, open, onClose }: { anchorRef: RefObject<HTMLElement | null>; open: boolean; onClose: () => void }) {
  const [stored] = useState(() => (typeof window !== 'undefined' ? window.localStorage.getItem(TOKEN_STORAGE_KEY) || '' : ''));
  const [token, setToken] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = token.trim();
    if (!normalized) {
      setError('Enter the private token from your CopeNet .copenet.env file.');
      return;
    }
    window.localStorage.setItem(TOKEN_STORAGE_KEY, normalized);
    window.location.reload();
  };

  const handleClear = () => {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    window.location.reload();
  };

  return (
    <FloatingPopover
      anchorRef={anchorRef}
      open={open}
      onClose={onClose}
      width={288}
      className="overflow-hidden rounded-xl border border-shell-border-strong bg-shell-panel-strong py-1 shadow-lg"
    >
      <div className="px-3 py-2.5">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-shell-muted">Gateway token</div>
        <div className="mt-0.5 text-[11px] text-shell-muted">{stored ? `Saved · ${maskedToken(stored)}` : 'No token saved in this browser.'}</div>
      </div>
      <div className="border-t border-shell-border/60 px-3 py-2.5">
        <form onSubmit={handleSubmit} className="flex flex-col gap-2">
          <label className="block">
            <span className="sr-only">Gateway token</span>
            <span className="relative block">
              <KeyRound className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-shell-muted" />
              <input
                type="password"
                name="gateway-token"
                value={token}
                onChange={(event) => {
                  setToken(event.target.value);
                  if (error) setError(null);
                }}
                autoComplete="current-password"
                spellCheck={false}
                placeholder={stored ? 'New gateway token' : 'Gateway token'}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? 'account-token-error' : undefined}
                className="h-9 w-full rounded-lg border border-shell-border bg-shell-panel pl-8 pr-3 text-[12px] text-shell-text outline-none transition-colors placeholder:text-shell-muted/60 focus:border-operator-accent/45"
              />
            </span>
            {error ? (
              <span id="account-token-error" className="mt-1 block text-[10.5px] text-operator-error">
                {error}
              </span>
            ) : null}
          </label>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              className="h-8 flex-1 rounded-lg bg-operator-accent px-3 text-[11px] font-semibold text-operator-bg transition-opacity hover:opacity-90"
            >
              Save &amp; reconnect
            </button>
            {stored ? (
              <button
                type="button"
                onClick={handleClear}
                title="Clear saved token"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-shell-border text-shell-muted transition-colors hover:border-operator-error/45 hover:text-operator-error"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
        </form>
        <p className="mt-2 text-[10px] leading-4 text-shell-muted/70">Stays in this browser's storage only — never sent anywhere but this gateway.</p>
      </div>
    </FloatingPopover>
  );
}
