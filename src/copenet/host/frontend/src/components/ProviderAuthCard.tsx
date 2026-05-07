/**
 * ProviderAuthCard — shows auth status for a single provider.
 *
 * For openai-codex: OAuth-backed, shows authenticated/expired/unauthenticated,
 * accountId if known, token expiry, and login/logout affordances.
 *
 * Backend wiring:
 *   - Reads: provider.auth.status RPC  → returns ProviderAuthStatus
 *   - Login: provider.auth.beginLogin  → returns authorizeUrl (open in browser)
 *   - Logout: provider.auth.logout     → clears stored auth
 *
 * V1 gaps (documented):
 *   - Login flow currently requires the operator to open the authorizeUrl in
 *     their browser manually (no deep-link / system-browser auto-open from UI).
 *   - provider.auth.completeLogin is not wired in UI — the callback URL
 *     hits the local server directly (localhost:1455/auth/callback). The UI
 *     will see the status update on next refresh() call.
 *   - No WebSocket push event when auth state changes; operator must click
 *     Refresh to pick up new auth state after completing login.
 */

import { useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  ExternalLink,
  KeyRound,
  LogOut,
  RefreshCw,
  ShieldAlert,
  User,
} from 'lucide-react';
import { wsClient } from '../lib/wsClient';
import { useAppStore } from '../store/useAppStore';
import { useProviderAuth } from '../runtime/adapter';
import type { ProviderAuthStatus } from '../runtime/types';

// ---------------------------------------------------------------------------
// Helper: expiry display
// ---------------------------------------------------------------------------

function formatExpiry(expiresAt: number | null): string {
  if (!expiresAt) return 'unknown';
  const now = Date.now();
  const diffMs = expiresAt - now;
  if (diffMs <= 0) return 'expired';
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 60) return `expires in ${diffMin}m`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `expires in ${diffHrs}h`;
  const diffDays = Math.floor(diffHrs / 24);
  return `expires in ${diffDays}d`;
}

// ---------------------------------------------------------------------------
// Connected state
// ---------------------------------------------------------------------------

function AuthenticatedView({
  status,
  onLogout,
  loggingOut,
}: {
  status: ProviderAuthStatus;
  onLogout: () => void;
  loggingOut: boolean;
}) {
  const expiry = formatExpiry(status.expiresAt);
  const isExpired = status.expired;

  return (
    <div className="space-y-2">
      <div className="flex items-start gap-2.5">
        <div
          className={`flex h-7 w-7 items-center justify-center rounded-lg shrink-0 ${
            isExpired
              ? 'bg-amber-400/10 text-amber-400'
              : 'bg-operator-success/10 text-operator-success'
          }`}
        >
          {isExpired ? (
            <AlertCircle className="w-3.5 h-3.5" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className={`text-[11px] font-semibold ${isExpired ? 'text-amber-400' : 'text-operator-success'}`}
            >
              {isExpired ? 'Token Expired' : 'Authenticated'}
            </span>
            <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted bg-operator-panel px-1.5 py-0.5 rounded">
              OAuth
            </span>
          </div>
          {status.accountId && (
            <div className="flex items-center gap-1 mt-0.5">
              <User className="w-2.5 h-2.5 text-operator-muted/60 shrink-0" />
              <span className="text-[11px] text-operator-muted font-mono truncate">
                {status.accountId}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Expiry row */}
      <div className="flex items-center gap-1.5 text-[10px]">
        <Clock className="w-2.5 h-2.5 text-operator-muted/60 shrink-0" />
        <span
          className={`font-mono ${isExpired ? 'text-amber-400' : 'text-operator-muted'}`}
        >
          {expiry}
        </span>
        {status.scopes.length > 0 && (
          <span className="text-operator-muted/50 ml-1 truncate">
            · {status.scopes.join(', ')}
          </span>
        )}
      </div>

      {/* Logout */}
      <button
        onClick={onLogout}
        disabled={loggingOut}
        className="flex items-center gap-1.5 text-[11px] text-operator-muted hover:text-operator-error transition-colors duration-150 disabled:opacity-50"
      >
        <LogOut className="w-3 h-3" />
        {loggingOut ? 'Logging out…' : 'Log out'}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Login flow
// ---------------------------------------------------------------------------

function LoginView({
  status,
  onBeginLogin,
  loginUrl,
  beginningLogin,
}: {
  status: ProviderAuthStatus;
  onBeginLogin: () => void;
  loginUrl: string | null;
  beginningLogin: boolean;
}) {
  return (
    <div className="space-y-2.5">
      <div className="flex items-start gap-2.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-operator-error/10 text-operator-error shrink-0">
          <ShieldAlert className="w-3.5 h-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-semibold text-operator-error">Not authenticated</div>
          <div className="text-[11px] text-operator-muted mt-0.5">
            OpenAI Codex requires OAuth login.
          </div>
        </div>
      </div>

      {!loginUrl && (
        <button
          onClick={onBeginLogin}
          disabled={beginningLogin}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-operator-accent/40 bg-operator-accent/10 px-3 py-1.5 text-[12px] font-medium text-operator-accent hover:bg-operator-accent/20 transition-colors duration-150 disabled:opacity-50"
        >
          <KeyRound className="w-3 h-3" />
          {beginningLogin ? 'Preparing login…' : 'Log in to Codex'}
        </button>
      )}

      {loginUrl && (
        <div className="space-y-1.5">
          <div className="text-[11px] text-operator-text">
            Open the link below in your browser to complete login:
          </div>
          <a
            href={loginUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-[11px] text-operator-accent hover:text-operator-text transition-colors duration-150 font-mono break-all"
          >
            <ExternalLink className="w-3 h-3 shrink-0" />
            <span className="truncate">{loginUrl}</span>
          </a>
          <div className="text-[10px] text-operator-muted/70 italic">
            The callback is handled locally. Click Refresh after completing login.
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProviderAuthCard
// ---------------------------------------------------------------------------

interface ProviderAuthCardProps {
  providerId: string;
  displayName?: string;
}

export function ProviderAuthCard({ providerId, displayName }: ProviderAuthCardProps) {
  const { status, loading, error, refresh } = useProviderAuth(providerId);
  const setStatus = useAppStore((s) => s.setProviderAuthStatus);

  const [loggingOut, setLoggingOut] = useState(false);
  const [loginUrl, setLoginUrl] = useState<string | null>(null);
  const [beginningLogin, setBeginningLogin] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      const next = await wsClient.providerAuthLogout(providerId);
      setStatus(providerId, next);
      setLoginUrl(null);
    } catch {
      // Ignore — operator can refresh
    } finally {
      setLoggingOut(false);
    }
  };

  const handleBeginLogin = async () => {
    setBeginningLogin(true);
    try {
      const info = await wsClient.providerAuthBeginLogin(providerId);
      setLoginUrl(info.authorizeUrl);
    } catch {
      setLoginUrl(null);
    } finally {
      setBeginningLogin(false);
    }
  };

  return (
    <div className="border-t border-operator-border/70 pt-2">
      <div className="flex items-center gap-2 pb-2">
        <KeyRound className="w-3 h-3 text-operator-muted shrink-0" />
        <span className="text-[11px] font-semibold text-operator-text truncate flex-1">
          {displayName ?? providerId}
        </span>
        <button
          onClick={refresh}
          disabled={loading}
          title="Refresh auth status"
          className="text-operator-muted hover:text-operator-text transition-colors duration-150 disabled:opacity-40"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="pb-1">
        {loading && !status && (
          <div className="flex items-center gap-2 text-[11px] text-operator-muted">
            <RefreshCw className="w-3 h-3 animate-spin" />
            Checking auth status…
          </div>
        )}

        {error && !status && (
          <div className="text-[11px] text-operator-error space-y-1">
            <div className="flex items-center gap-1.5">
              <AlertCircle className="w-3 h-3 shrink-0" />
              <span>Could not reach auth backend</span>
            </div>
            <div className="text-[10px] text-operator-muted font-mono">{error}</div>
            <div className="text-[10px] text-operator-muted/60 italic">
              Backend dep: provider.auth.status RPC
            </div>
          </div>
        )}

        {status && status.authenticated && !status.expired && (
          <AuthenticatedView status={status} onLogout={handleLogout} loggingOut={loggingOut} />
        )}

        {status && (status.expired || !status.authenticated) && (
          <>
            {status.authenticated && status.expired && (
              <div className="mb-2">
                <AuthenticatedView
                  status={status}
                  onLogout={handleLogout}
                  loggingOut={loggingOut}
                />
              </div>
            )}
            <LoginView
              status={status}
              onBeginLogin={handleBeginLogin}
              loginUrl={loginUrl}
              beginningLogin={beginningLogin}
            />
          </>
        )}

        {!loading && !error && !status && (
          <div className="text-[11px] text-operator-muted italic">
            Auth status unavailable.
            <span className="block text-[10px] mt-0.5 not-italic text-operator-muted/60">
              Backend dep: provider.auth.status RPC
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
