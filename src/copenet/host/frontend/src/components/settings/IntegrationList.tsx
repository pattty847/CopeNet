import { useEffect, useState } from 'react';
import { CheckCircle2, CircleDashed } from 'lucide-react';
import { wsClient } from '../../lib/wsClient';
import type { IntegrationStatus } from '../../types/backend';

/** Optional data integrations, as presence only. Setup stays in `.env`, where each key is
 *  read — the panel names the variable instead of offering a field that writes secrets. */
export function IntegrationList() {
  const [integrations, setIntegrations] = useState<IntegrationStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    wsClient.settingsIntegrations().then(setIntegrations).catch((reason: Error) => setError(reason.message));
  }, []);

  if (error) return <p className="text-[12px] text-operator-error">Couldn't read integration status: {error}</p>;
  if (!integrations) return <p className="text-[12px] text-shell-muted">Checking…</p>;

  return (
    <ul className="divide-y divide-shell-border overflow-hidden rounded-xl border border-shell-border bg-shell-panel">
      {integrations.map((integration) => (
        <li key={integration.id} className="flex items-start gap-3 px-3.5 py-2.5">
          {integration.ready ? (
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-shell-success" aria-label="Ready" />
          ) : (
            <CircleDashed className="mt-0.5 h-3.5 w-3.5 shrink-0 text-shell-muted" aria-label="Not set up" />
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[13px] font-medium text-shell-text">{integration.label}</span>
              <span className={`text-[11px] ${integration.ready ? 'text-shell-success' : 'text-shell-muted'}`}>
                {integration.ready ? 'Ready' : 'Not set up'}
              </span>
            </div>
            <div className="text-[12px] text-shell-muted">{integration.purpose}</div>
            {!integration.ready && (
              <code className="mt-1.5 inline-block rounded border border-shell-border bg-shell-canvas px-1.5 py-0.5 font-mono text-[11px] text-shell-text">
                {integration.setup}
              </code>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
