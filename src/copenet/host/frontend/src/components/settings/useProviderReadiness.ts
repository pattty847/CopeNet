import { useAppStore } from '../../store/useAppStore';

/** One answer to "can this operator start a chat?", shared by Home onboarding and Settings. */
export function useProviderReadiness() {
  const providers = useAppStore((state) => state.providers);
  const codexAuth = useAppStore((state) => state.providerAuthStatuses['openai-codex']);
  const codex = providers.find((provider) => provider.id === 'openai-codex');
  const claude = providers.find((provider) => provider.id === 'claude-cli');
  const lmStudio = providers.find((provider) => provider.id === 'lm-studio');
  const codexReady = codexAuth?.authenticated === true || codex?.authenticated === true;
  const claudeReady = claude?.available === true && claude.authenticated !== false;
  const lmStudioReady = lmStudio?.available === true;
  // `providers.list` returns every registered lane, including ones that failed to start,
  // so an empty list only ever means the catalog has not arrived yet.
  const loaded = providers.length > 0;
  return {
    loaded,
    codexReady,
    claudeReady,
    claudeInstalled: Boolean(claude),
    lmStudio,
    lmStudioReady,
    anyReady: codexReady || claudeReady || lmStudioReady,
  };
}
