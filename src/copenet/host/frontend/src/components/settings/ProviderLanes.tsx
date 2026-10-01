import { CheckCircle2, ExternalLink, Terminal } from 'lucide-react';
import { ProviderAuthCard } from '../ProviderAuthCard';
import { useProviderReadiness } from './useProviderReadiness';

const CLAUDE_SETUP_URL = 'https://docs.anthropic.com/en/docs/claude-code/getting-started';

// Below this the harness's own instructions and tool schemas crowd out the conversation.
const LM_STUDIO_MIN_CONTEXT = 16_384;

const code = 'self-start rounded border border-shell-border bg-shell-canvas px-1.5 py-1 font-mono text-[11px] text-shell-text';

function Lane({ title, ready, children }: { title: string; ready: boolean; children: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-shell-border bg-shell-panel px-3.5 py-3">
      <div className="flex items-center justify-between text-[13px] font-semibold text-shell-text">
        <span>{title}</span>
        {ready && <CheckCircle2 className="h-3.5 w-3.5 text-shell-success" aria-label="Ready" />}
      </div>
      <div className="mt-2 flex flex-col gap-2 text-[12px] leading-relaxed text-shell-muted">{children}</div>
    </div>
  );
}

/** Every provider lane with its setup steps. Home shows these only until one is ready;
 *  after that they live in Settings, where a connected lane also offers sign-out. */
export function ProviderLanes({ columns = 2 }: { columns?: 1 | 2 }) {
  const { codexReady, claudeReady, claudeInstalled, lmStudio, lmStudioReady } = useProviderReadiness();

  return (
    <div className="flex flex-col gap-2.5">
      <div className={`grid gap-2.5 ${columns === 2 ? 'md:grid-cols-2' : ''}`}>
        <Lane title="ChatGPT · OpenAI Codex" ready={codexReady}>
          <ProviderAuthCard providerId="openai-codex" displayName="ChatGPT account" />
        </Lane>

        <Lane title="Claude · Claude Code" ready={claudeReady}>
          {claudeReady ? (
            <p>Claude Code is installed and signed in.</p>
          ) : claudeInstalled ? (
            <>
              <p>Claude Code is installed but not signed in.</p>
              <code className={code}>claude auth login</code>
              <button type="button" className="self-start text-shell-accent hover:underline" onClick={() => window.location.reload()}>
                Recheck after login
              </button>
            </>
          ) : (
            <>
              <p>Install Claude Code, sign in, then restart CopeNet so it can find the CLI on PATH.</p>
              <code className={code}>npm install -g @anthropic-ai/claude-code</code>
              <code className={code}>claude auth login</code>
              <a className="inline-flex items-center gap-1 self-start text-shell-accent hover:underline" href={CLAUDE_SETUP_URL} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-3 w-3" /> Official setup guide
              </a>
            </>
          )}
        </Lane>

        {lmStudio && (
          <Lane title="Local · LM Studio" ready={lmStudioReady}>
            {lmStudioReady ? (
              <LmStudioLoaded models={lmStudio.loadedModels ?? []} />
            ) : (
              <>
                <p>Not reachable. Start the LM Studio server; on another machine, turn on Serve on Local Network and point CopeNet at it.</p>
                <code className={code}>COPNET_LM_STUDIO_BASE_URL=http://&lt;gpu-host&gt;:1234</code>
              </>
            )}
            {lmStudio.baseUrl && <span className="font-mono text-[11px]">{lmStudio.baseUrl}</span>}
          </Lane>
        )}
      </div>
      {!codexReady && (
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-shell-muted">
          <Terminal className="h-3 w-3" /> Terminal fallback for OpenAI:
          <code className={code}>uv run copenet auth login --provider openai-codex</code>
        </div>
      )}
    </div>
  );
}

function LmStudioLoaded({ models }: { models: { id: string; contextLength: number | null }[] }) {
  if (models.length === 0) {
    return <p>Connected, nothing loaded. Load a model in LM Studio, or pick one in a new chat and LM Studio loads it on first use.</p>;
  }
  return (
    <ul className="flex flex-col gap-1">
      {models.map((model) => {
        const short = model.contextLength !== null && model.contextLength < LM_STUDIO_MIN_CONTEXT;
        return (
          <li key={model.id} className="flex flex-col">
            <span className="font-mono text-[11px] text-shell-text">{model.id}</span>
            <span className={short ? 'text-shell-error' : undefined}>
              {model.contextLength === null ? 'context unknown' : `${model.contextLength.toLocaleString()} token context`}
              {short && ' — reload it with at least 16K, or tool turns will drop history'}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
