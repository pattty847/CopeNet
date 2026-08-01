import { useAppStore } from '../store/useAppStore';
import type { ChatEventPayload, TurnStateSnapshot } from '../types/backend';
import {
  buildBatchLabel,
  makeLocalId,
  normalizeAssistantDisplayText,
  normalizeIdentityContextRuntime,
  normalizeMessageParts,
  normalizeToolEffect,
  normalizeToolExecution,
  normalizeToolResultPreview,
} from './wsNormalizers';

export function handleChatEventAction(
  payload: ChatEventPayload,
  refreshSessions: () => Promise<void>,
  refreshMemoryDrafts: () => Promise<void>,
): void {
  const store = useAppStore.getState();
  const runId = payload.runId ? String(payload.runId) : null;
  const sessionKey = payload.sessionKey;
  const toolExecution = normalizeToolExecution(payload.toolExecution);

  if (payload.state === 'reasoning_delta') {
    // Phase 4: native reasoning-summary deltas render as inline "thinking"
    // narration between tool calls (Claude Code-style).
    const text = typeof payload.text === 'string' ? payload.text : '';
    const target = runId ? store.pendingAssistants[runId] : undefined;
    if (target && text) {
      const source = payload.reasoningSource === 'raw' ? 'raw' : payload.reasoningSource === 'summary' ? 'summary' : 'unknown';
      store.appendMessagePart(target.sessionKey, target.localId, { kind: 'thinking', text, source });
    }
    return;
  }

  if (payload.state === 'tool_called') {
    const rawToolCall = payload.toolCall as Record<string, unknown> | null | undefined;
    if (rawToolCall && runId) {
      const liveToolCalls = store.liveToolCallsByRun[runId] || [];
      const toolId = String(rawToolCall.toolId ?? rawToolCall.tool_id ?? 'tool');
      const liveId = String(rawToolCall.callId ?? rawToolCall.call_id ?? `${runId}:${rawToolCall.step ?? liveToolCalls.length}:${toolId}`);
      store.pushLiveToolCall(runId, {
        id: liveId,
        toolId,
        state: 'running',
        summary: `Calling ${toolId}`,
        error: null,
        startedAt: new Date().toISOString(),
        completedAt: null,
      });
      const target = store.pendingAssistants[runId];
      if (target) {
        const callId = String(rawToolCall.callId ?? rawToolCall.call_id ?? `${runId}:${rawToolCall.step ?? liveToolCalls.length}:${rawToolCall.toolId ?? rawToolCall.tool_id ?? 'tool'}`);
        const hint = rawToolCall.hint
          ? String(rawToolCall.hint)
          : rawToolCall.arguments && typeof rawToolCall.arguments === 'object'
            ? JSON.stringify(rawToolCall.arguments)
            : null;
        store.appendMessagePart(target.sessionKey, target.localId, {
          kind: 'tool_call',
          callId,
          toolId,
          turnId: rawToolCall.turnId ? String(rawToolCall.turnId) : null,
          decisionId: rawToolCall.decisionId ? String(rawToolCall.decisionId) : null,
          hint,
          target: rawToolCall.target ? String(rawToolCall.target) : hint,
          at: new Date().toISOString(),
        });
      }
    }
    return;
  }

  if (payload.state === 'tool_result') {
    if (toolExecution && runId) {
      const liveToolCalls = store.liveToolCallsByRun[runId] || [];
      const existingMatch = [...liveToolCalls]
        .reverse()
        .find((call) => call.state === 'running' && call.toolId === toolExecution.toolId);
      store.pushLiveToolCall(runId, {
        id: existingMatch?.id || toolExecution.callId || `${runId}:${toolExecution.toolId}:${liveToolCalls.length}`,
        toolId: toolExecution.toolId,
        state: toolExecution.ok
          ? 'success'
          : toolExecution.summary?.toLowerCase().includes('blocked') || toolExecution.channel === 'policy'
            ? 'blocked'
            : 'failed',
        summary: toolExecution.summary,
        error: toolExecution.error ?? null,
        startedAt: existingMatch?.startedAt || new Date().toISOString(),
        completedAt: new Date().toISOString(),
      });

      const target = store.pendingAssistants[runId];
      if (target) {
        const toolPayloadRecord = payload.toolExecution as unknown as Record<string, unknown> | null | undefined;
        const batchMembers = Array.isArray(toolPayloadRecord?.members) ? toolPayloadRecord?.members : [];
        if (Array.isArray(batchMembers) && batchMembers.length > 1) {
          store.appendMessagePart(target.sessionKey, target.localId, {
            kind: 'tool_batch',
            batchId: `batch-${runId}`,
            label: buildBatchLabel(String(batchMembers[0] && typeof batchMembers[0] === 'object' ? (batchMembers[0] as Record<string, unknown>).toolId || toolExecution.toolId : toolExecution.toolId), batchMembers.length),
            members: batchMembers.map((m: unknown) => {
              const mb = (m || {}) as Record<string, unknown>;
              return {
                callId: String(mb.callId ?? ''),
                toolId: String(mb.toolId ?? toolExecution.toolId),
                turnId: mb.turnId ? String(mb.turnId) : toolExecution.turnId || null,
                decisionId: mb.decisionId ? String(mb.decisionId) : toolExecution.decisionId || null,
                ok: Boolean(mb.ok),
                summary: String(mb.summary ?? ''),
                error: mb.error ? String(mb.error) : null,
                artifactId: mb.artifactId ? String(mb.artifactId) : null,
                target: mb.target ? String(mb.target) : null,
                workspaceRoot: mb.workspaceRoot ? String(mb.workspaceRoot) : null,
                scope: mb.scope === 'outside_workspace' ? 'outside_workspace' : mb.scope === 'inside_workspace' ? 'inside_workspace' : null,
                accessAction: mb.accessAction === 'read' || mb.accessAction === 'write' || mb.accessAction === 'unknown' ? mb.accessAction : null,
                policyDecision:
                  mb.policyDecision === 'allowed' ||
                  mb.policyDecision === 'read_roam' ||
                  mb.policyDecision === 'write_blocked' ||
                  mb.policyDecision === 'approval_required' ||
                  mb.policyDecision === 'unsafe_unknown'
                    ? mb.policyDecision
                    : null,
                policySummary: mb.policySummary ? String(mb.policySummary) : null,
                preview: normalizeToolResultPreview(mb.preview),
                effect: normalizeToolEffect(mb.effect),
              };
            }),
            ok: toolExecution.ok,
            workspaceRoot: toolPayloadRecord?.workspaceRoot ? String(toolPayloadRecord.workspaceRoot) : toolExecution.workspaceRoot || null,
            at: new Date().toISOString(),
          });
        } else {
          store.appendMessagePart(target.sessionKey, target.localId, {
            kind: 'tool_result',
            callId: toolExecution.callId || '',
            toolId: toolExecution.toolId,
            turnId: toolExecution.turnId || null,
            decisionId: toolExecution.decisionId || null,
            ok: toolExecution.ok,
            summary: toolExecution.summary,
            error: toolExecution.error ?? null,
            artifactId: toolExecution.artifactId || null,
            target: toolExecution.target || null,
            workspaceRoot: toolExecution.workspaceRoot || null,
            scope: toolExecution.scope || null,
            accessAction: toolExecution.accessAction || null,
            policyDecision: toolExecution.policyDecision || null,
            policySummary: toolExecution.policySummary || null,
            preview: normalizeToolResultPreview(toolPayloadRecord?.preview),
            effect: toolExecution.effect || null,
            at: new Date().toISOString(),
          });
        }
      }
    }
    return;
  }

  if (payload.state === 'delta') {
    let target = runId ? useAppStore.getState().pendingAssistants[runId] : undefined;
    if (runId && !target) {
      const localId = makeLocalId('assistant');
      store.addMessage(sessionKey, {
        localId,
        sessionKey,
        runId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        provider: payload.provider ? String(payload.provider) : null,
        model: payload.model ? String(payload.model) : null,
        providerSessionId: payload.message?.providerSessionId ? String(payload.message.providerSessionId) : null,
        state: 'delta',
        toolExecution,
        parts: normalizeMessageParts(payload.message?.parts),
        errorMessage: null,
        optimistic: true,
      });
      store.registerPendingAssistant(runId, sessionKey, localId);
      target = { sessionKey, localId };
    }

    if (target) {
      const existing = useAppStore.getState().messages[target.sessionKey]?.find((message) => message.localId === target.localId);
      const chunk = payload.message?.content ? String(payload.message.content) : '';
      const normalizedParts = normalizeMessageParts(payload.message?.parts);
      store.updateMessage(target.sessionKey, target.localId, {
        content: `${existing?.content || ''}${chunk}`,
        provider: payload.provider ? String(payload.provider) : existing?.provider || null,
        model: payload.model ? String(payload.model) : existing?.model || null,
        state: 'delta',
        toolExecution: toolExecution || existing?.toolExecution || null,
        parts: normalizedParts || existing?.parts || null,
        optimistic: true,
      });
      if (!normalizedParts && chunk && existing?.parts != null) {
        store.appendMessagePart(target.sessionKey, target.localId, { kind: 'text', content: chunk });
      }
    }
    return;
  }

  if (payload.state === 'final' || payload.state === 'error' || payload.state === 'aborted') {
    const target = runId ? useAppStore.getState().pendingAssistants[runId] : undefined;
    if (target) {
      const existing = useAppStore.getState().messages[target.sessionKey]?.find((message) => message.localId === target.localId);
      store.updateMessage(target.sessionKey, target.localId, {
        content:
          typeof payload.message?.content === 'string' && payload.message.content.length > 0
            ? normalizeAssistantDisplayText(payload.message.content)
            : existing?.content || '',
        provider: payload.provider ? String(payload.provider) : existing?.provider || null,
        model: payload.model ? String(payload.model) : existing?.model || null,
        state: payload.state,
        toolExecution: toolExecution || existing?.toolExecution || null,
        parts: normalizeMessageParts(payload.message?.parts) || existing?.parts || null,
        errorMessage: payload.errorMessage ? String(payload.errorMessage) : null,
        optimistic: false,
      });
      if (runId) {
        store.clearPendingAssistant(runId);
      }
    } else if (payload.state === 'error') {
      store.addMessage(sessionKey, {
        localId: makeLocalId('system'),
        sessionKey,
        runId,
        role: 'system',
        content: payload.errorMessage ? String(payload.errorMessage) : 'Run failed.',
        timestamp: new Date().toISOString(),
        provider: payload.provider ? String(payload.provider) : null,
        model: payload.model ? String(payload.model) : null,
        providerSessionId: null,
        state: 'error',
        toolExecution,
        errorMessage: payload.errorMessage ? String(payload.errorMessage) : 'Run failed.',
        optimistic: false,
      });
    }

    if (runId) {
      store.clearActiveRun(sessionKey, runId);
      store.clearLiveToolCalls(runId);
    }

    // Capture turnState snapshot from final event before clearing live calls.
    if (payload.state === 'final') {
      const ts = (payload as unknown as Record<string, unknown>).turnState;
      if (ts && typeof ts === 'object') {
        const t = ts as Record<string, unknown>;
        const snapshot: TurnStateSnapshot = {
          turnId: t.turnId ? String(t.turnId) : null,
          decisionId: t.decisionId ? String(t.decisionId) : null,
          toolCallCount: Number(t.toolCallCount ?? 0),
          visitedTools: Array.isArray(t.visitedTools) ? (t.visitedTools as string[]) : [],
          visitedPaths: Array.isArray(t.visitedPaths) ? (t.visitedPaths as string[]) : [],
          groundingActions: Array.isArray(t.groundingActions) ? (t.groundingActions as string[]) : [],
          failedActions: Array.isArray(t.failedActions)
            ? (t.failedActions as Array<{ toolId: string; summary: string; error: string | null }>)
            : [],
          openQuestions: Array.isArray(t.openQuestions) ? (t.openQuestions as string[]) : [],
          lastToolResultSummary: String(t.lastToolResultSummary ?? ''),
          terminalReason: t.terminalReason != null ? String(t.terminalReason) : null,
          transitionReason: String(t.transitionReason ?? 'completed'),
        };
        store.setLastTurnState(sessionKey, snapshot);
      }
      const identityContext = normalizeIdentityContextRuntime((payload as unknown as Record<string, unknown>).identityContext);
      if (identityContext) {
        store.setSessionIdentityUsage(sessionKey, identityContext);
      }
    }

    // Only close the draft if the completed run belongs to the currently active session.
    // Closing unconditionally would destroy a new draft the user opened while a prior run finished.
    if (sessionKey && store.activeSessionKey === sessionKey) {
      store.setDraftOpen(false);
    }
    void refreshSessions();
    // The run may have proposed a memory draft (memory.write) - surface it.
    void refreshMemoryDrafts();
  }
}
