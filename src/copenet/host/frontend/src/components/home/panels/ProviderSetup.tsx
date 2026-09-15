import { CheckCircle2, CircleAlert, ExternalLink, Terminal } from 'lucide-react';
import { useAppStore } from '../../../store/useAppStore';
import { ProviderAuthCard } from '../../ProviderAuthCard';
import { Card } from './Card';

const CLAUDE_SETUP_URL = 'https://docs.anthropic.com/en/docs/claude-code/getting-started';

export function ProviderSetup({ secMarket }: { secMarket?: { available: boolean; installCommand: string; unavailableFeatures: string[] } }) {
  const providers = useAppStore((state) => state.providers);
  const codexAuth = useAppStore((state) => state.providerAuthStatuses['openai-codex']);
  const codex = providers.find((provider) => provider.id === 'openai-codex');
  const claude = providers.find((provider) => provider.id === 'claude-cli');
  const codexReady = codexAuth?.authenticated === true || codex?.authenticated === true;
  const claudeReady = claude?.available === true && claude.authenticated !== false;
  const providerSetupComplete = codexReady && claudeReady;

  if (providerSetupComplete && secMarket?.available !== false) return null;

  return (
    <Card
      title={providerSetupComplete
        ? 'Optional Market extension'
        : codexReady || claudeReady
          ? 'Provider setup · one more available'
          : 'Choose a model provider to begin'}
      icon={CircleAlert}
      span={12}
      className="hd-provider-setup"
    >
      {!providerSetupComplete && <div className="hd-provider-setup__intro">
        You only need one ready provider. CopeNet keeps sessions and tools local; the selected provider supplies the model.
      </div>}
      {!providerSetupComplete && <div className="hd-provider-setup__grid">
        <div className="hd-provider-setup__lane">
          <div className="hd-provider-setup__lane-title">
            <span>OpenAI Codex</span>
            {codexReady && <CheckCircle2 size={14} aria-label="Ready" />}
          </div>
          {codexReady ? (
            <p>OAuth connected. Codex chats are ready.</p>
          ) : (
            <ProviderAuthCard providerId="openai-codex" displayName="Connect your ChatGPT account" />
          )}
        </div>

        <div className="hd-provider-setup__lane">
          <div className="hd-provider-setup__lane-title">
            <span>Claude CLI</span>
            {claudeReady && <CheckCircle2 size={14} aria-label="Ready" />}
          </div>
          {claudeReady ? (
            <p>Claude CLI is installed and authenticated.</p>
          ) : claude ? (
            <div className="hd-provider-setup__steps">
              <p>Claude CLI is installed but not signed in.</p>
              <code>claude auth login</code>
              <button type="button" className="hd-provider-setup__recheck" onClick={() => window.location.reload()}>
                Recheck after login
              </button>
            </div>
          ) : (
            <div className="hd-provider-setup__steps">
              <p>Install Claude Code, sign in, then restart CopeNet so it can find the CLI on PATH.</p>
              <code>npm install -g @anthropic-ai/claude-code</code>
              <code>claude auth login</code>
              <a href={CLAUDE_SETUP_URL} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={12} /> Official setup guide
              </a>
            </div>
          )}
        </div>
      </div>}
      {!providerSetupComplete && <div className="hd-provider-setup__terminal">
        <Terminal size={12} /> Terminal fallback for OpenAI: <code>uv run copenet auth login --provider openai-codex</code>
      </div>}
      {secMarket?.available === false && (
        <div className="hd-provider-setup__terminal">
          <CircleAlert size={12} /> Optional SEC Market pack is not installed. {secMarket.unavailableFeatures.join(', ')} are unavailable;
          price charts still work. <code>{secMarket.installCommand}</code>
        </div>
      )}
    </Card>
  );
}
