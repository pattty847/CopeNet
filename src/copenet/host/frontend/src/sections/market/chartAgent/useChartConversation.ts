import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import { safeUUID } from '../../../lib/wsNormalizers';
import { useAppStore } from '../../../store/useAppStore';
import type { DraftSettings, Session } from '../../../types/backend';
import type { ChartDetail, MarketCapture, MarketContext } from './types';
import type { ChartWorkspaceController } from './useChartWorkspace';

const DRAFT_KEY = 'copenet.chart.pendingDraft';
function loadDraft() {
  const fallback = { ...useAppStore.getState().draftSettings, taskPromptId: 'none', personaId: '', personaFlavorId: '', personaPrivacyTier: 'off' as const };
  try {
    const saved = JSON.parse(localStorage.getItem(DRAFT_KEY) ?? 'null');
    if (saved?.key && saved?.settings) return saved as { key: string; settings: DraftSettings };
  } catch { /* no pending first send */ }
  return { key: `chart-${safeUUID()}`, settings: fallback };
}

export function useChartConversation(workspace: ChartWorkspaceController) {
  const sessions = useAppStore((state) => state.sessions);
  const session = sessions.find((row) => row.key === workspace.sessionKey) ?? null;
  const [draft, setDraft] = useState(loadDraft);
  const [input, setInput] = useState('');
  const [detail, setDetail] = useState<ChartDetail>('balanced');
  const [access, setAccess] = useState<'read' | 'annotate'>('annotate');
  const [modelOverride, setModelOverride] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const sendInProgress = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [lastCapture, setLastCapture] = useState<{ observationId: string; capture: MarketCapture } | null>(null);
  const pending = useRef<{ message: string; capture: MarketCapture; key: string; session?: Session; observationId?: string; detail: ChartDetail; access: 'read' | 'annotate'; model: string | null } | null>(null);
  const sessionKey = session?.key ?? workspace.sessionKey;
  const activeRun = useAppStore((state) => sessionKey ? state.activeRunsBySession[sessionKey] : null);
  const messages = useAppStore((state) => sessionKey ? state.messages[sessionKey] : undefined) ?? [];
  const providers = useAppStore((state) => state.providers);
  const provider = session?.provider ?? draft.settings.provider;
  const models = useAppStore((state) => state.modelsByProvider[provider]) ?? [];
  const model = modelOverride ?? session?.model ?? draft.settings.model;

  useEffect(() => {
    void wsClient.loadModels(provider).catch((reason) => setError(reason instanceof Error ? reason.message : 'Models unavailable.'));
  }, [provider]);
  useEffect(() => {
    if (!sessionKey || sending || activeRun) return;
    void wsClient.refreshSessions().catch(() => undefined);
    void wsClient.loadHistory(sessionKey).catch((reason) => setError(reason instanceof Error ? reason.message : 'Conversation unavailable.'));
  }, [sessionKey, sending, activeRun]);
  useEffect(() => { setModelOverride(null); }, [sessionKey]);

  const changeProvider = (next: string) => {
    if (sessionKey || sending) return;
    pending.current = null; setModelOverride(null);
    setDraft((current) => ({ key: `chart-${safeUUID()}`, settings: { ...current.settings, provider: next, model: '' } }));
  };
  const changeModel = (next: string) => {
    setModelOverride(next);
    if (!session) setDraft((current) => ({ ...current, settings: { ...current.settings, model: next } }));
  };

  const send = async () => {
    if (!input.trim() || sendInProgress.current || activeRun || session?.archived) return;
    sendInProgress.current = true;
    setSending(true); setError(null);
    try {
      if (workspace.sessionKey && !session) throw new Error('Wait for the linked chart session to load.');
      // Freeze before session creation or capture RPC awaits. A retry keeps its original evidence.
      if (!pending.current || pending.current.message !== input.trim()) pending.current = {
        message: input.trim(), capture: workspace.capture(), key: safeUUID(), detail, access, model,
      };
      const submission = pending.current;
      if (!submission.session) {
        if (session) submission.session = session;
        else {
          localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
          submission.session = await wsClient.marketChart.createSession(draft.key, draft.settings);

        }
      }
      if (workspace.sessionKey !== submission.session.key) {
        await wsClient.marketChart.linkSession(submission.session.key);
        workspace.setSessionKey(submission.session.key);
        localStorage.removeItem(DRAFT_KEY);
      }
      if (!submission.observationId) {
        const receipt = await wsClient.marketChart.capture(submission.session.key, submission.key, submission.capture);
        submission.observationId = receipt.observationId;
      }
      setLastCapture({ observationId: submission.observationId, capture: submission.capture });
      const marketContext: MarketContext = { observationId: submission.observationId, documentId: submission.capture.documentId,
        viewId: submission.capture.viewId, detail: submission.detail, access: submission.access };
      const result = await wsClient.marketChart.send({ session: submission.session, message: submission.message,
        marketContext, displayContext: { symbol: submission.capture.instrument.symbol, timeframe: submission.capture.timeframe },
        idempotencyKey: submission.key, runtimeOverride: { model: submission.model ?? undefined } });
      setInput((current) => current.trim() === submission.message ? '' : current); pending.current = null;
      if (result?.status === 'completed' || result?.status === 'cached') await wsClient.loadHistory(submission.session.key);
      void workspace.refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not send this chart question.'); }
    finally { sendInProgress.current = false; setSending(false); }
  };

  const captureForForecast = async () => {
    if (workspace.sessionKey && !session) throw new Error('Wait for the linked chart session to load.');
    const capture = workspace.capture(false);
    const key = safeUUID();
    let owner = session;
    if (!owner) {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
      owner = await wsClient.marketChart.createSession(draft.key, draft.settings);
    }
    if (workspace.sessionKey !== owner.key) {
      await wsClient.marketChart.linkSession(owner.key);
      workspace.setSessionKey(owner.key);
      localStorage.removeItem(DRAFT_KEY);
    }
    const receipt = await wsClient.marketChart.capture(owner.key, key, capture);
    return { sessionKey: owner.key, observationId: receipt.observationId, documentId: capture.documentId };
  };

  const newConversation = async () => {
    if (sendInProgress.current || activeRun) return;
    sendInProgress.current = true; setSending(true); setError(null);
    try {
      await wsClient.marketChart.linkSession(null);
      workspace.setSessionKey(null);
      pending.current = null;
      const nextDraft = { key: `chart-${safeUUID()}`, settings: { ...draft.settings, provider, model: model ?? '' } };
      setDraft(nextDraft);
      localStorage.setItem(DRAFT_KEY, JSON.stringify(nextDraft));
      setModelOverride(null); setLastCapture(null); setInput('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not start a new conversation.'); }
    finally { sendInProgress.current = false; setSending(false); }
  };

  const stop = async () => {
    if (!sessionKey || !activeRun) return;
    try { await wsClient.abortRun(sessionKey, activeRun); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not stop this turn.'); }
  };
  return { session, sessionKey, input, setInput, detail, setDetail, access, setAccess, sending, error, activeRun, messages,
    captureForForecast, providers, provider, models, model, changeProvider, changeModel, send, stop, lastCapture, newConversation,
    resetSubmission: () => { pending.current = null; setError(null); } };
}
