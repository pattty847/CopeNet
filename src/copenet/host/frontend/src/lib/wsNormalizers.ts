import type {
  ApprovalRequest,
  IdentityContextRuntime,
  MemoryItem,
  UserNoteProposal,
  Message,
  MessageDestination,
  MessagePart,
  MessagingConfig,
  Model,
  PersonaContextPayload,
  PersonaFlavorDraft,
  PersonaHomeSummary,
  PersonaSettings,
  Provider,
  PublicMessagePayload,
  PulseRecord,
  ReturnBriefingPayload,
  RuntimeContext,
  Session,
  SessionMergeState,
  ShellAllowlistEntry,
  TelegramSessionRoute,
  TextPart,
  ToolDescriptor,
  ToolEffect,
  ToolExecution,
  ToolResultPreview,
  WorkspaceIntelSummary,
} from '../types/backend';
import { physicalFilePreviewLines } from './filePreview';

// crypto.randomUUID only exists in SECURE contexts (https or localhost). When
// CopeNet is reached over plain http on the tailnet (e.g. iOS Safari at
// http://<host>.ts.net:17123), it's undefined — so fall back to a v4 UUID built
// from getRandomValues, which IS available on insecure origins.
export function safeUUID(): string {
  const c: Crypto | undefined = typeof crypto !== 'undefined' ? crypto : undefined;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  const bytes = new Uint8Array(16);
  if (c && typeof c.getRandomValues === 'function') {
    c.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10xx
  const hex: string[] = [];
  for (let i = 0; i < 16; i += 1) hex.push(bytes[i].toString(16).padStart(2, '0'));
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10, 16).join('')}`;
}

export function makeLocalId(prefix: string): string {
  return `${prefix}-${safeUUID()}`;
}

export function normalizeToolEffect(raw: unknown): ToolEffect | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  if (payload.schema_version !== 'tool_effect.v1') return null;
  const turnId = String(payload.turn_id || '').trim();
  const toolId = String(payload.tool_id || '').trim();
  const effectId = String(payload.effect_id || '').trim();
  if (!turnId || !toolId || !effectId) return null;
  const kind = String(payload.kind || 'raw') as ToolEffect['kind'];
  const evidenceRole = String(payload.evidence_role || 'none') as ToolEffect['evidence_role'];
  return {
    schema_version: 'tool_effect.v1',
    effect_id: effectId,
    decision_id: payload.decision_id ? String(payload.decision_id) : null,
    turn_id: turnId,
    tool_id: toolId,
    kind,
    target: payload.target ? String(payload.target) : null,
    preview: payload.preview && typeof payload.preview === 'object' ? payload.preview as Record<string, unknown> : null,
    artifact_id: payload.artifact_id ? String(payload.artifact_id) : null,
    evidence_role: evidenceRole,
  };
}

export function normalizeToolExecution(raw: unknown): ToolExecution | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const toolId = String(payload.toolId || '').trim();
  if (!toolId) return null;
  return {
    toolId,
    ok: Boolean(payload.ok),
    summary: String(payload.summary || '').trim(),
    turnId: payload.turnId ? String(payload.turnId) : null,
    decisionId: payload.decisionId ? String(payload.decisionId) : null,
    callId: payload.callId ? String(payload.callId) : null,
    channel: payload.channel ? String(payload.channel) : null,
    error: payload.error ? String(payload.error) : null,
    artifactId: payload.artifactId ? String(payload.artifactId) : null,
    target: payload.target ? String(payload.target) : null,
    workspaceRoot: payload.workspaceRoot ? String(payload.workspaceRoot) : null,
    scope: payload.scope === 'outside_workspace' ? 'outside_workspace' : payload.scope === 'inside_workspace' ? 'inside_workspace' : null,
    accessAction: payload.accessAction === 'read' || payload.accessAction === 'write' || payload.accessAction === 'unknown' ? payload.accessAction : null,
    policyDecision:
      payload.policyDecision === 'allowed' ||
      payload.policyDecision === 'read_roam' ||
      payload.policyDecision === 'write_blocked' ||
      payload.policyDecision === 'approval_required' ||
      payload.policyDecision === 'unsafe_unknown'
        ? payload.policyDecision
        : null,
    policySummary: payload.policySummary ? String(payload.policySummary) : null,
    effect: normalizeToolEffect(payload.effect),
  };
}

/**
 * How much of a preview to keep. The inline transcript wants a teaser; the
 * Inspect drawer wants the whole thing the backend bothered to send. Same
 * normalizer, two budgets — the defaults preserve the inline behavior exactly.
 */
export interface PreviewLimits {
  maxChars?: number;
  maxLines?: number;
  maxMatches?: number;
  maxResults?: number;
}

const DEFAULT_PREVIEW_LIMITS: Required<PreviewLimits> = {
  maxChars: 500,
  maxLines: 600,
  maxMatches: 8,
  maxResults: 8,
};

export function normalizeToolResultPreview(raw: unknown, limits?: PreviewLimits): ToolResultPreview | null {
  if (!raw || typeof raw !== 'object') return null;
  const { maxChars, maxLines, maxMatches, maxResults } = { ...DEFAULT_PREVIEW_LIMITS, ...limits };
  const payload = raw as Record<string, unknown>;
  const type = String(payload.type || '');
  if (type === 'file_read') {
    return {
      type: 'file_read',
      path: String(payload.path || ''),
      lines: physicalFilePreviewLines(payload.lines, maxLines),
      startLine: payload.startLine != null ? Math.max(1, Number(payload.startLine)) : 1,
      totalLines: payload.totalLines != null ? Number(payload.totalLines) : null,
    };
  }
  if (type === 'repo_search') {
    const rawMatches = Array.isArray(payload.matches) ? payload.matches.slice(0, maxMatches) : [];
    return {
      type: 'repo_search',
      query: String(payload.query || ''),
      matches: rawMatches.map((m: unknown) => {
        const match = (m || {}) as Record<string, unknown>;
        return {
          path: String(match.path || ''),
          line: Number(match.line || 0),
          snippet: String(match.snippet || ''),
        };
      }),
      totalMatches: payload.totalMatches != null ? Number(payload.totalMatches) : null,
    };
  }
  if (type === 'diff') {
    return {
      type: 'diff',
      path: String(payload.path || ''),
      diff: String(payload.diff || ''),
      linesAdded: Number(payload.linesAdded || 0),
      linesRemoved: Number(payload.linesRemoved || 0),
      truncated: Boolean(payload.truncated),
      created: Boolean(payload.created),
      afterDigest: payload.afterDigest ? String(payload.afterDigest) : undefined,
    };
  }
  if (type === 'plan') {
    const rawItems = Array.isArray(payload.items) ? payload.items : [];
    const valid = ['pending', 'in_progress', 'completed'];
    return {
      type: 'plan',
      items: rawItems.map((it: unknown) => {
        const item = (it || {}) as Record<string, unknown>;
        const status = String(item.status || 'pending');
        return {
          content: String(item.content || ''),
          status: (valid.includes(status) ? status : 'pending') as 'pending' | 'in_progress' | 'completed',
        };
      }),
    };
  }
  if (type === 'web_search') {
    const rawResults = Array.isArray(payload.results) ? payload.results.slice(0, maxResults) : [];
    return {
      type: 'web_search',
      query: String(payload.query || ''),
      results: rawResults.map((r: unknown) => {
        const row = (r || {}) as Record<string, unknown>;
        return {
          title: String(row.title || ''),
          url: String(row.url || ''),
          snippet: String(row.snippet || ''),
        };
      }),
    };
  }
  if (type === 'web_doc') {
    return {
      type: 'web_doc',
      url: String(payload.url || ''),
      title: String(payload.title || ''),
      wordCount: Number(payload.wordCount || 0),
      text: String(payload.text || ''),
    };
  }
  if (typeof payload.path === 'string' && typeof payload.content === 'string') {
    const lines = physicalFilePreviewLines(payload.content, maxLines);
    return {
      type: 'file_read',
      path: String(payload.path),
      lines,
      startLine: payload.startLine != null ? Math.max(1, Number(payload.startLine)) : 1,
      totalLines: payload.totalLines != null ? Number(payload.totalLines) : physicalFilePreviewLines(payload.content).length,
    };
  }
  if (Array.isArray(payload.matches)) {
    return {
      type: 'repo_search',
      query: typeof payload.query === 'string' ? payload.query : '',
      matches: payload.matches.slice(0, maxMatches).map((m: unknown) => {
        const match = (m || {}) as Record<string, unknown>;
        return {
          path: String(match.path || ''),
          line: Number(match.line || 0),
          snippet: String(match.text || match.snippet || ''),
        };
      }),
      totalMatches: Array.isArray(payload.matches) ? payload.matches.length : null,
    };
  }
  if (typeof payload.preview === 'string') {
    return { type: 'raw', text: String(payload.preview).slice(0, maxChars) };
  }
  // Fall back to raw text preview
  const text = payload.text ? String(payload.text) : JSON.stringify(payload);
  return { type: 'raw', text: text.slice(0, maxChars) };
}

export function buildBatchLabel(toolId: string, count: number): string {
  if (toolId.includes('read') || toolId === 'files.read') return `Read ${count} files`;
  if (toolId.includes('search') || toolId.includes('rg')) return `Search ${count} paths`;
  return `${count} tool calls`;
}

export function normalizeApprovalRequest(raw: unknown): ApprovalRequest | null {
  if (!raw || typeof raw !== 'object') return null;
  const p = raw as Record<string, unknown>;
  const approvalId = String(p.approvalId || '');
  if (!approvalId) return null;
  const action = (p.proposedAction || {}) as Record<string, unknown>;
  const validStatus = ['pending', 'approved', 'rejected', 'modified', 'expired'];
  const validClass = [
    'external_communication',
    'filesystem_write',
    'process_execution',
    'network_side_effect',
    'credential_or_sensitive_target',
  ];
  return {
    approvalId,
    runId: String(p.runId || ''),
    sessionKey: String(p.sessionKey || ''),
    status: (validStatus.includes(String(p.status)) ? String(p.status) : 'pending') as ApprovalRequest['status'],
    actionClass: (validClass.includes(String(p.actionClass)) ? String(p.actionClass) : 'process_execution') as ApprovalRequest['actionClass'],
    toolId: String(p.toolId || ''),
    proposedAction: {
      description: String(action.description || ''),
      target: action.target != null ? String(action.target) : null,
      payload: (action.payload && typeof action.payload === 'object' ? action.payload : {}) as Record<string, unknown>,
    },
    rationale: p.rationale != null ? String(p.rationale) : null,
    createdAt: String(p.createdAt || new Date().toISOString()),
    resolvedAt: p.resolvedAt != null ? String(p.resolvedAt) : null,
    outcome: (p.outcome as ApprovalRequest['outcome']) ?? null,
  };
}

export function normalizeSession(raw: unknown): Session {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    key: String(payload.key || ''),
    sessionId: String(payload.sessionId || ''),
    title: payload.title ? String(payload.title) : null,
    provider: String(payload.provider || ''),
    model: payload.model ? String(payload.model) : null,
    systemPromptId: payload.systemPromptId ? String(payload.systemPromptId) : null,
    taskPromptId: payload.taskPromptId ? String(payload.taskPromptId) : null,
    personaId: payload.personaId ? String(payload.personaId) : null,
    personaFlavorId: payload.personaFlavorId ? String(payload.personaFlavorId) : null,
    personaPrivacyTier: payload.personaPrivacyTier ? String(payload.personaPrivacyTier) as Session['personaPrivacyTier'] : null,
    workspaceRoot: payload.workspaceRoot ? String(payload.workspaceRoot) : null,
    archived: Boolean(payload.archived),
    providerSessionId: payload.providerSessionId ? String(payload.providerSessionId) : null,
    createdAt: String(payload.createdAt || new Date().toISOString()),
    updatedAt: String(payload.updatedAt || new Date().toISOString()),
    lastRunId: payload.lastRunId ? String(payload.lastRunId) : null,
    inFlightRunId: payload.inFlightRunId ? String(payload.inFlightRunId) : null,
    sessionType: payload.sessionType === 'fleet_lane' ? 'fleet_lane' : 'standard',
    parentSessionKey: payload.parentSessionKey ? String(payload.parentSessionKey) : null,
    participantId: payload.participantId ? String(payload.participantId) : null,
  };
}

export function normalizeProvider(raw: unknown): Provider {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    displayName: String(payload.displayName || payload.id || ''),
    available: payload.available !== false,
    error: payload.error ? String(payload.error) : '',
    capabilities: (payload.capabilities as Record<string, boolean> | undefined) || {},
  };
}

export function normalizeModel(raw: unknown): Model {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    displayName: String(payload.displayName || payload.id || ''),
    provider: String(payload.provider || ''),
    description: payload.description ? String(payload.description) : null,
    kind: String(payload.kind || 'chat'),
    capabilities: (payload.capabilities as Record<string, boolean> | undefined) || {},
    recommendedFor: Array.isArray(payload.recommendedFor) ? payload.recommendedFor.map(String) : [],
    metadata: (payload.metadata as Record<string, unknown> | undefined) || {},
  };
}

export function normalizeTool(raw: unknown): ToolDescriptor {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    name: String(payload.name || payload.id || ''),
    description: String(payload.description || ''),
    category: String(payload.category || ''),
    inputSchema: (payload.inputSchema as Record<string, unknown> | undefined) || {},
    safetyLevel: String(payload.safetyLevel || ''),
    capabilities: Array.isArray(payload.capabilities) ? payload.capabilities.map(String) : [],
    riskClass: payload.riskClass ? String(payload.riskClass) : undefined,
    approvalMode: payload.approvalMode ? String(payload.approvalMode) : undefined,
    evidenceRole: payload.evidenceRole ? String(payload.evidenceRole) : undefined,
    sideEffect: payload.sideEffect ? String(payload.sideEffect) : undefined,
    requiresConfirmation: Boolean(payload.requiresConfirmation),
  };
}

export function normalizePersonaHome(raw: unknown): PersonaHomeSummary | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  return {
    personaId: String(payload.personaId || 'default'),
    personaFlavorId: payload.personaFlavorId ? String(payload.personaFlavorId) : null,
    personaPrivacyTier: String(payload.personaPrivacyTier || 'private') as PersonaHomeSummary['personaPrivacyTier'],
    active: Boolean(payload.active),
    rootDir: String(payload.rootDir || ''),
    loadedFiles: Array.isArray(payload.loadedFiles) ? payload.loadedFiles.map((value) => String(value)).filter(Boolean) : [],
  };
}

export function normalizePersonaSettings(raw: unknown): PersonaSettings | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const overridesRaw = payload.modelOverrides && typeof payload.modelOverrides === 'object'
    ? payload.modelOverrides as Record<string, unknown>
    : {};
  const modelOverrides: PersonaSettings['modelOverrides'] = {};
  for (const [key, value] of Object.entries(overridesRaw)) {
    if (!value || typeof value !== 'object') continue;
    const override = value as Record<string, unknown>;
    modelOverrides[key] = {
      personaId: String(override.personaId || 'default'),
      flavorId: override.flavorId ? String(override.flavorId) : null,
    };
  }
  return {
    defaultPersonaId: String(payload.defaultPersonaId || 'default'),
    defaultPrivacyTier: String(payload.defaultPrivacyTier || 'private') as PersonaSettings['defaultPrivacyTier'],
    modelOverrides,
  };
}

export function normalizePersonaContext(raw: unknown): PersonaContextPayload | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const tier = String(payload.personaPrivacyTier || 'private');
  return {
    personaId: String(payload.personaId || 'default'),
    personaFlavorId: payload.personaFlavorId ? String(payload.personaFlavorId) : null,
    personaPrivacyTier: tier === 'safe' || tier === 'off' ? tier : 'private',
    prompt: String(payload.prompt || ''),
    loadedFiles: Array.isArray(payload.loadedFiles) ? payload.loadedFiles.map((value) => String(value)).filter(Boolean) : [],
  };
}

export function normalizePersonaFlavorDraft(raw: unknown): PersonaFlavorDraft | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  return {
    displayName: String(payload.displayName || payload.name || 'Model Flavor'),
    identityMarkdown: String(payload.identityMarkdown || payload.identity || ''),
    soulMarkdown: String(payload.soulMarkdown || payload.soul || ''),
    notesMarkdown: String(payload.notesMarkdown || payload.notes || ''),
  };
}

export function normalizeMemoryItem(raw: unknown): MemoryItem | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const category = String(payload.category || '');
  if (!['preference', 'project_convention', 'ongoing_priority', 'fact'].includes(category)) return null;
  return {
    id: String(payload.id || ''),
    category: category as MemoryItem['category'],
    title: String(payload.title || 'Memory'),
    summary: String(payload.summary || payload.title || ''),
    detail: payload.detail ? String(payload.detail) : null,
    tags: Array.isArray(payload.tags) ? payload.tags.map((tag) => String(tag)).filter(Boolean) : [],
    source: String(payload.source || 'explicit'),
    confidence: Number(payload.confidence || 0),
    createdAt: String(payload.createdAt || new Date().toISOString()),
    updatedAt: String(payload.updatedAt || payload.createdAt || new Date().toISOString()),
    archived: Boolean(payload.archived),
    lastSessionKey: payload.lastSessionKey ? String(payload.lastSessionKey) : null,
  };
}

export function normalizeUserNote(raw: unknown): UserNoteProposal | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const id = String(payload.id || '');
  if (!id) return null;
  const status = String(payload.status || 'draft');
  return {
    id,
    targetSection: String(payload.targetSection || 'Summary'),
    summary: String(payload.summary || 'USER.md update'),
    body: String(payload.body || ''),
    status: status === 'approved' ? 'approved' : 'draft',
    createdAt: String(payload.createdAt || new Date().toISOString()),
    updatedAt: String(payload.updatedAt || payload.createdAt || new Date().toISOString()),
    lastSessionKey: payload.lastSessionKey ? String(payload.lastSessionKey) : null,
  };
}

export function normalizeShellAllowlist(raw: unknown): ShellAllowlistEntry[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item): ShellAllowlistEntry | null => {
      if (!item || typeof item !== 'object') return null;
      const payload = item as Record<string, unknown>;
      const command = String(payload.command || '').trim();
      if (!command) return null;
      return { command, addedAt: String(payload.addedAt || '') };
    })
    .filter((entry): entry is ShellAllowlistEntry => entry != null);
}

export function normalizeIdentityContextRuntime(raw: unknown): IdentityContextRuntime | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  return {
    memoryCount: Number(payload.memoryCount || 0),
    memoryItemIds: Array.isArray(payload.memoryItemIds) ? payload.memoryItemIds.map((value) => String(value)).filter(Boolean) : [],
    personaActive: Boolean(payload.personaActive),
    personaId: payload.personaId ? String(payload.personaId) : null,
    personaFlavorId: payload.personaFlavorId ? String(payload.personaFlavorId) : null,
    personaPrivacyTier: payload.personaPrivacyTier ? String(payload.personaPrivacyTier) as IdentityContextRuntime['personaPrivacyTier'] : null,
  };
}

export function normalizeReturnBriefing(raw: unknown): ReturnBriefingPayload | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  return {
    briefingId: String(payload.briefingId || ''),
    generatedAt: String(payload.generatedAt || new Date().toISOString()),
    attentionItems: Array.isArray(payload.attentionItems)
      ? payload.attentionItems.map((item: unknown) => {
          const row = (item || {}) as Record<string, unknown>;
          return {
            id: String(row.id || ''),
            title: String(row.title || ''),
            urgency: String(row.urgency || 'low') as ReturnBriefingPayload['attentionItems'][number]['urgency'],
            source: String(row.source || ''),
            detail: row.detail ? String(row.detail) : null,
          };
        })
      : [],
    activityItems: Array.isArray(payload.activityItems)
      ? payload.activityItems.map((item: unknown) => {
          const row = (item || {}) as Record<string, unknown>;
          return {
            id: String(row.id || ''),
            summary: String(row.summary || ''),
            sessionKey: row.sessionKey ? String(row.sessionKey) : null,
            toolsUsed: row.toolsUsed != null ? Number(row.toolsUsed) : undefined,
            at: String(row.at || new Date().toISOString()),
          };
        })
      : [],
    watchItems: Array.isArray(payload.watchItems)
      ? payload.watchItems.map((item: unknown) => {
          const row = (item || {}) as Record<string, unknown>;
          return {
            id: String(row.id || ''),
            label: String(row.label || ''),
            signal: String(row.signal || ''),
            source: row.source ? String(row.source) : null,
          };
        })
      : [],
    noticeText: payload.noticeText ? String(payload.noticeText) : null,
    noticeSource: payload.noticeSource ? String(payload.noticeSource) : null,
  };
}

export function normalizePulse(raw: unknown): PulseRecord | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const pulseId = String(payload.pulseId || '').trim();
  if (!pulseId) return null;
  return {
    pulseId,
    status:
      payload.status === 'saved' || payload.status === 'dismissed'
        ? payload.status
        : 'new',
    title: String(payload.title || ''),
    summary: String(payload.summary || ''),
    whyNow: String(payload.whyNow || ''),
    sourceSessionKeys: Array.isArray(payload.sourceSessionKeys) ? payload.sourceSessionKeys.map(String) : [],
    sourceRunIds: Array.isArray(payload.sourceRunIds) ? payload.sourceRunIds.map(String) : [],
    sourceSessions: Array.isArray(payload.sourceSessions)
      ? payload.sourceSessions
          .map((item) => {
            const row = (item || {}) as Record<string, unknown>;
            const sessionKey = String(row.sessionKey || '').trim();
            if (!sessionKey) return null;
            return {
              sessionKey,
              title: String(row.title || sessionKey),
            };
          })
          .filter((item): item is { sessionKey: string; title: string } => item != null)
      : [],
    createdAt: String(payload.createdAt || new Date().toISOString()),
    updatedAt: String(payload.updatedAt || new Date().toISOString()),
    savedAt: payload.savedAt ? String(payload.savedAt) : null,
    dismissedAt: payload.dismissedAt ? String(payload.dismissedAt) : null,
  };
}

export function normalizeDestination(raw: unknown): MessageDestination | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const id = String(payload.id || '').trim();
  const target = String(payload.target || '').trim();
  if (!id || !target) return null;
  return {
    id,
    platform: String(payload.platform || 'telegram').trim() || 'telegram',
    target,
    displayName: String(payload.displayName || target).trim() || target,
    threadLabel: payload.threadLabel ? String(payload.threadLabel) : null,
    isDefault: Boolean(payload.isDefault),
    requiresApproval: payload.requiresApproval !== false,
    status:
      payload.status === 'configured' || payload.status === 'unconfigured' || payload.status === 'error'
        ? payload.status
        : 'configured',
  };
}

export function normalizeTelegramRoute(raw: unknown): TelegramSessionRoute | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const id = String(payload.id || '').trim();
  const chatId = String(payload.chatId || '').trim();
  const sessionKey = String(payload.sessionKey || '').trim();
  if (!id || !chatId || !sessionKey) return null;
  return {
    id,
    platform: String(payload.platform || 'telegram').trim() || 'telegram',
    chatId,
    threadId: payload.threadId ? String(payload.threadId) : null,
    sessionKey,
    titleOverride: payload.titleOverride ? String(payload.titleOverride) : null,
  };
}

export function normalizeMessagingConfig(raw: unknown): MessagingConfig | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const destinations = Array.isArray(payload.destinations)
    ? payload.destinations.map(normalizeDestination).filter((item): item is MessageDestination => item != null)
    : [];
  const approvalRaw = (payload.approvalPolicy || {}) as Record<string, unknown>;
  const telegramRaw = payload.telegram && typeof payload.telegram === 'object' ? (payload.telegram as Record<string, unknown>) : null;
  const telegramDefaultsRaw =
    payload.telegramDefaults && typeof payload.telegramDefaults === 'object'
      ? (payload.telegramDefaults as Record<string, unknown>)
      : null;
  const routes = Array.isArray(payload.routes)
    ? payload.routes.map(normalizeTelegramRoute).filter((item): item is TelegramSessionRoute => item != null)
    : [];
  return {
    telegram: telegramRaw
      ? {
          botUsername: telegramRaw.botUsername ? String(telegramRaw.botUsername) : null,
          tokenMasked: telegramRaw.tokenMasked ? String(telegramRaw.tokenMasked) : null,
          connectionStatus:
            telegramRaw.connectionStatus === 'connected' ||
            telegramRaw.connectionStatus === 'disconnected' ||
            telegramRaw.connectionStatus === 'error' ||
            telegramRaw.connectionStatus === 'unconfigured'
              ? telegramRaw.connectionStatus
              : 'unconfigured',
          lastVerifiedAt: telegramRaw.lastVerifiedAt ? String(telegramRaw.lastVerifiedAt) : null,
          errorMessage: telegramRaw.errorMessage ? String(telegramRaw.errorMessage) : null,
        }
      : null,
    destinations,
    approvalPolicy: {
      requireApprovalByDefault: approvalRaw.requireApprovalByDefault !== false,
      hardlineBlocklist: Array.isArray(approvalRaw.hardlineBlocklist) ? approvalRaw.hardlineBlocklist.map(String) : [],
    },
    telegramDefaults: telegramDefaultsRaw
      ? {
          provider: telegramDefaultsRaw.provider ? String(telegramDefaultsRaw.provider) : null,
          model: telegramDefaultsRaw.model ? String(telegramDefaultsRaw.model) : null,
          systemPromptId: telegramDefaultsRaw.systemPromptId ? String(telegramDefaultsRaw.systemPromptId) : null,
          taskPromptId: telegramDefaultsRaw.taskPromptId ? String(telegramDefaultsRaw.taskPromptId) : null,
        }
      : null,
    routes,
  };
}

export function normalizePrompt(raw: unknown) {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    name: String(payload.name || payload.id || ''),
  };
}

export function normalizeRuntimeContext(raw: unknown): RuntimeContext | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const workspaceRoot = String(payload.workspaceRoot || '').trim();
  if (!workspaceRoot) return null;
  return {
    workspaceRoot,
    fileToolScope: 'workspace_home_visible_roaming',
    shellToolScope: 'cwd_default',
    shellAllowlist: Array.isArray(payload.shellAllowlist) ? payload.shellAllowlist.map(String) : [],
    workspaceIntel: normalizeWorkspaceIntelSummary(payload.workspaceIntel),
    note: String(payload.note || '').trim(),
  };
}

export function normalizeWorkspaceIntelSummary(raw: unknown): WorkspaceIntelSummary | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const workspaceRoot = String(payload.workspaceRoot || '').trim();
  if (!workspaceRoot) return null;
  const cacheStatus = String(payload.cacheStatus || 'cached').trim();
  return {
    workspaceRoot,
    cacheStatus:
      cacheStatus === 'fresh' || cacheStatus === 'refreshed' || cacheStatus === 'stale'
        ? cacheStatus
        : 'cached',
    languages: Array.isArray(payload.languages) ? payload.languages.map(String) : [],
    packageManagers: Array.isArray(payload.packageManagers) ? payload.packageManagers.map(String) : [],
    recommendedDefaultChecks: Array.isArray(payload.recommendedDefaultChecks)
      ? payload.recommendedDefaultChecks.map(String)
      : [],
  };
}

export function normalizeMergeState(raw: unknown): SessionMergeState | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const status = String(payload.status || '').trim();
  if (!status) return null;
  const rawSources = Array.isArray(payload.sources) ? payload.sources : [];
  return {
    status:
      status === 'running' || status === 'complete' || status === 'failed'
        ? status
        : 'pending',
    sourceSessionKeys: Array.isArray(payload.sourceSessionKeys) ? payload.sourceSessionKeys.map(String) : [],
    totalSources: Number(payload.totalSources || rawSources.length || 0),
    completedSources: Number(payload.completedSources || 0),
    startedAt: String(payload.startedAt || new Date().toISOString()),
    completedAt: payload.completedAt ? String(payload.completedAt) : null,
    briefRunId: payload.briefRunId ? String(payload.briefRunId) : null,
    briefArtifactId: payload.briefArtifactId ? String(payload.briefArtifactId) : null,
    conflicts: Array.isArray(payload.conflicts) ? payload.conflicts.map(String) : [],
    sources: rawSources.map((item: unknown) => {
      const source = (item || {}) as Record<string, unknown>;
      const sourceStatus = String(source.status || '').trim();
      return {
        sessionKey: String(source.sessionKey || ''),
        title: String(source.title || source.sessionKey || ''),
        status:
          sourceStatus === 'running' || sourceStatus === 'complete' || sourceStatus === 'failed'
            ? sourceStatus
            : 'pending',
        summary: source.summary ? String(source.summary) : null,
        error: source.error ? String(source.error) : null,
        decisionCount: Number(source.decisionCount || 0),
        openQuestionCount: Number(source.openQuestionCount || 0),
      };
    }),
  };
}

export function normalizeMessage(
  raw: PublicMessagePayload | null | undefined,
  sessionKey: string,
  localId: string,
  fallbackRole: Message['role'],
  fallbackState: Message['state'],
  optimistic = false,
): Message {
  const content = typeof raw?.content === 'string' ? normalizeAssistantDisplayText(raw.content) : '';
  return {
    localId,
    sessionKey,
    runId: raw?.runId ? String(raw.runId) : null,
    role: raw?.role === 'assistant' || raw?.role === 'system' ? raw.role : fallbackRole,
    content,
    timestamp: raw?.timestamp ? String(raw.timestamp) : new Date().toISOString(),
    provider: raw?.provider ? String(raw.provider) : null,
    model: raw?.model ? String(raw.model) : null,
    providerSessionId: raw?.providerSessionId ? String(raw.providerSessionId) : null,
    state: (raw?.state as Message['state']) || fallbackState,
    toolExecution: normalizeToolExecution(raw?.toolExecution),
    errorMessage: null,
    optimistic,
    parts: normalizeMessageParts(raw?.parts),
    attachments: normalizeChatAttachments(raw?.attachments),
    requestedToolIds: Array.isArray(raw?.requestedToolIds)
      ? [...new Set(raw.requestedToolIds.map((toolId) => String(toolId).trim()).filter(Boolean))]
      : null,
  };
}

export function normalizeChatAttachments(raw: unknown): Message['attachments'] {
  if (!Array.isArray(raw)) return null;
  const attachments: NonNullable<Message['attachments']> = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const payload = item as Record<string, unknown>;
    const attachmentId = String(payload.attachmentId || '');
    if (!attachmentId) continue;
    attachments.push({
      attachmentId,
      mimeType: String(payload.mimeType || 'application/octet-stream'),
      filename: String(payload.filename || 'image'),
    });
  }
  return attachments.length > 0 ? attachments : null;
}

export function normalizeAssistantDisplayText(raw: string): string {
  return raw;
}

export function normalizeMessageParts(raw: unknown): MessagePart[] | null {
  if (!Array.isArray(raw)) return null;
  const parts: MessagePart[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const payload = item as Record<string, unknown>;
    const kind = String(payload.kind || '');
    if (kind === 'text') {
      const content = typeof payload.content === 'string' ? payload.content : typeof payload.text === 'string' ? payload.text : '';
      const normalized = normalizeAssistantDisplayText(content);
      if (normalized) parts.push({ kind: 'text', content: normalized } as TextPart);
      continue;
    }
    if (kind === 'thinking') {
      const text = typeof payload.text === 'string' ? payload.text : typeof payload.content === 'string' ? payload.content : '';
      if (text) parts.push({ kind: 'thinking', text });
      continue;
    }
    if (kind === 'tool_call') {
      const toolCall = payload.toolCall && typeof payload.toolCall === 'object' ? payload.toolCall as Record<string, unknown> : payload;
      parts.push({
        kind: 'tool_call',
        callId: String(toolCall.callId ?? payload.callId ?? ''),
        toolId: String(toolCall.toolId ?? payload.toolId ?? ''),
        turnId: toolCall.turnId ? String(toolCall.turnId) : payload.turnId ? String(payload.turnId) : null,
        decisionId: toolCall.decisionId ? String(toolCall.decisionId) : payload.decisionId ? String(payload.decisionId) : null,
        hint: toolCall.hint ? String(toolCall.hint) : null,
        target: toolCall.target ? String(toolCall.target) : payload.target ? String(payload.target) : null,
        at: typeof payload.at === 'string' ? payload.at : new Date().toISOString(),
      });
      continue;
    }
    if (kind === 'tool_result') {
      const toolExecution = payload.toolExecution && typeof payload.toolExecution === 'object'
        ? payload.toolExecution as Record<string, unknown>
        : payload;
      const members = Array.isArray(toolExecution.members) ? toolExecution.members : [];
      if (members.length > 1) {
        parts.push({
          kind: 'tool_batch',
          batchId: typeof payload.runId === 'string' && payload.runId
            ? `batch-${payload.runId}`
            : String(toolExecution.callId ?? payload.callId ?? makeLocalId('batch')),
          label: buildBatchLabel('files.read', members.length),
          members: members.map((m: unknown) => {
            const member = (m || {}) as Record<string, unknown>;
            return {
              callId: String(member.callId ?? ''),
              toolId: String(member.toolId ?? ''),
              turnId: member.turnId ? String(member.turnId) : null,
              decisionId: member.decisionId ? String(member.decisionId) : null,
              ok: Boolean(member.ok),
              summary: String(member.summary ?? ''),
              error: member.error ? String(member.error) : null,
              artifactId: member.artifactId ? String(member.artifactId) : null,
              target: member.target ? String(member.target) : null,
              workspaceRoot: member.workspaceRoot ? String(member.workspaceRoot) : null,
              scope: member.scope === 'outside_workspace' ? 'outside_workspace' : member.scope === 'inside_workspace' ? 'inside_workspace' : null,
              accessAction: member.accessAction === 'read' || member.accessAction === 'write' || member.accessAction === 'unknown' ? member.accessAction : null,
              policyDecision:
                member.policyDecision === 'allowed' ||
                member.policyDecision === 'read_roam' ||
                member.policyDecision === 'write_blocked' ||
                member.policyDecision === 'approval_required' ||
                member.policyDecision === 'unsafe_unknown'
                  ? member.policyDecision
                  : null,
              policySummary: member.policySummary ? String(member.policySummary) : null,
              preview: normalizeToolResultPreview(member.preview),
              effect: normalizeToolEffect(member.effect),
            };
          }),
          ok: Boolean(toolExecution.ok ?? payload.ok),
          workspaceRoot: toolExecution.workspaceRoot ? String(toolExecution.workspaceRoot) : payload.workspaceRoot ? String(payload.workspaceRoot) : null,
          at: typeof payload.at === 'string' ? payload.at : new Date().toISOString(),
        });
      } else {
        parts.push({
          kind: 'tool_result',
          callId: String(toolExecution.callId ?? payload.callId ?? ''),
          toolId: String(toolExecution.toolId ?? payload.toolId ?? ''),
          turnId: toolExecution.turnId ? String(toolExecution.turnId) : payload.turnId ? String(payload.turnId) : null,
          decisionId: toolExecution.decisionId ? String(toolExecution.decisionId) : payload.decisionId ? String(payload.decisionId) : null,
          ok: Boolean(toolExecution.ok ?? payload.ok),
          summary: String(toolExecution.summary ?? payload.summary ?? ''),
          error: toolExecution.error ? String(toolExecution.error) : payload.error ? String(payload.error) : null,
          artifactId: toolExecution.artifactId ? String(toolExecution.artifactId) : payload.artifactId ? String(payload.artifactId) : null,
          target: toolExecution.target ? String(toolExecution.target) : payload.target ? String(payload.target) : null,
          workspaceRoot: toolExecution.workspaceRoot ? String(toolExecution.workspaceRoot) : payload.workspaceRoot ? String(payload.workspaceRoot) : null,
          scope: toolExecution.scope === 'outside_workspace' ? 'outside_workspace' : toolExecution.scope === 'inside_workspace' ? 'inside_workspace' : payload.scope === 'outside_workspace' ? 'outside_workspace' : payload.scope === 'inside_workspace' ? 'inside_workspace' : null,
          accessAction:
            toolExecution.accessAction === 'read' || toolExecution.accessAction === 'write' || toolExecution.accessAction === 'unknown'
              ? toolExecution.accessAction
              : payload.accessAction === 'read' || payload.accessAction === 'write' || payload.accessAction === 'unknown'
                ? payload.accessAction
                : null,
          policyDecision:
            toolExecution.policyDecision === 'allowed' ||
            toolExecution.policyDecision === 'read_roam' ||
            toolExecution.policyDecision === 'write_blocked' ||
            toolExecution.policyDecision === 'approval_required' ||
            toolExecution.policyDecision === 'unsafe_unknown'
              ? toolExecution.policyDecision
              : payload.policyDecision === 'allowed' ||
                payload.policyDecision === 'read_roam' ||
                payload.policyDecision === 'write_blocked' ||
                payload.policyDecision === 'approval_required' ||
                payload.policyDecision === 'unsafe_unknown'
                ? payload.policyDecision
                : null,
          policySummary: toolExecution.policySummary ? String(toolExecution.policySummary) : payload.policySummary ? String(payload.policySummary) : null,
          preview: normalizeToolResultPreview((toolExecution as Record<string, unknown>).preview ?? payload.preview),
          effect: normalizeToolEffect(toolExecution.effect ?? payload.effect),
          at: typeof payload.at === 'string' ? payload.at : new Date().toISOString(),
        });
      }
    }
  }
  return parts.length > 0 ? parts : null;
}
