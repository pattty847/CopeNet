import { useAppStore } from '../store/useAppStore';
import {
  ChatEventPayload,
  EventFrame,
  IncomingFrame,
  IdentityContextPayload,
  IdentityContextRuntime,
  LiveToolCall,
  MemoryItem,
  MessageDestination,
  Message,
  MessagePart,
  MessagingConfig,
  Model,
  PatProfile,
  PersonaContextPayload,
  PersonaFlavorDraft,
  PersonaHomeSummary,
  PersonaSettings,
  PromptOptimizationResult,
  PromptOptimizationVariant,
  PulseRecord,
  ProfileChangelogItem,
  Provider,
  ProviderAuthStatus,
  PublicMessagePayload,
  RuntimeContext,
  ReturnBriefingPayload,
  ResponseFrame,
  Session,
  SessionMergeState,
  SessionExportPayload,
  SessionArtifactRecord,
  SessionStateRecord,
  SessionRunRecord,
  TextPart,
  TelegramSessionRoute,
  ToolDescriptor,
  ToolExecution,
  ToolResultPreview,
  TurnStateSnapshot,
} from '../types/backend';
import { DRAFT_TRANSCRIPT_SESSION_KEY } from './personaCommands';

type PendingRequest = {
  resolve: (payload: Record<string, unknown>) => void;
  reject: (error: Error) => void;
};

const RECONNECT_DELAY_MS = 3000;
const DEFAULT_DEV_TOKEN = 'dev-token';
const PROVIDER_PRIORITY = ['lm-studio', 'ollama', 'codex-cli'];

function getEnvString(name: 'VITE_COPNET_WS_URL' | 'VITE_COPNET_TOKEN'): string {
  const meta = typeof import.meta !== 'undefined' ? (import.meta as ImportMeta & { env?: Record<string, unknown> }) : undefined;
  const value = meta?.env?.[name];
  return typeof value === 'string' ? value.trim() : '';
}

function getWsUrl(): string {
  const envUrl = getEnvString('VITE_COPNET_WS_URL');
  if (envUrl) return envUrl;
  if (typeof window === 'undefined') return 'ws://127.0.0.1:17123/ws';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}

function getAuthToken(): string {
  const envToken = getEnvString('VITE_COPNET_TOKEN');
  const fromWindow = typeof window !== 'undefined' && typeof window.COPNET_TOKEN === 'string' ? window.COPNET_TOKEN.trim() : '';
  const fromStorage = typeof window !== 'undefined' ? window.localStorage.getItem('copnet.token') || '' : '';
  const fromMeta = typeof document !== 'undefined' ? document.querySelector('meta[name="copnet-token"]')?.getAttribute('content')?.trim() || '' : '';
  return envToken || fromWindow || fromStorage || fromMeta || DEFAULT_DEV_TOKEN;
}

function pickPreferredProvider(providers: Provider[]): string {
  for (const id of PROVIDER_PRIORITY) {
    if (providers.some((provider) => provider.id === id && provider.available !== false)) return id;
  }
  return providers.find((provider) => provider.available !== false)?.id || providers[0]?.id || 'codex-cli';
}

function makeLocalId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

function normalizeToolExecution(raw: unknown): ToolExecution | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const toolId = String(payload.toolId || '').trim();
  if (!toolId) return null;
  return {
    toolId,
    ok: Boolean(payload.ok),
    summary: String(payload.summary || '').trim(),
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
  };
}

function normalizeToolResultPreview(raw: unknown): ToolResultPreview | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const type = String(payload.type || '');
  if (type === 'file_read') {
    return {
      type: 'file_read',
      path: String(payload.path || ''),
      lines: Array.isArray(payload.lines) ? payload.lines.slice(0, 20).map(String) : [],
      totalLines: payload.totalLines != null ? Number(payload.totalLines) : null,
    };
  }
  if (type === 'repo_search') {
    const rawMatches = Array.isArray(payload.matches) ? payload.matches.slice(0, 8) : [];
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
  if (typeof payload.path === 'string' && typeof payload.content === 'string') {
    const lines = String(payload.content).split('\n').slice(0, 20);
    return {
      type: 'file_read',
      path: String(payload.path),
      lines,
      totalLines: String(payload.content).split('\n').length,
    };
  }
  if (Array.isArray(payload.matches)) {
    return {
      type: 'repo_search',
      query: typeof payload.query === 'string' ? payload.query : '',
      matches: payload.matches.slice(0, 8).map((m: unknown) => {
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
    return { type: 'raw', text: String(payload.preview).slice(0, 500) };
  }
  // Fall back to raw text preview
  const text = payload.text ? String(payload.text) : JSON.stringify(payload);
  return { type: 'raw', text: text.slice(0, 500) };
}

function buildBatchLabel(toolId: string, count: number): string {
  if (toolId.includes('read') || toolId === 'files.read') return `Read ${count} files`;
  if (toolId.includes('search') || toolId.includes('rg')) return `Search ${count} paths`;
  return `${count} tool calls`;
}

function normalizeSession(raw: unknown): Session {
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
  };
}

function normalizeProvider(raw: unknown): Provider {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    displayName: String(payload.displayName || payload.id || ''),
    available: payload.available !== false,
    error: payload.error ? String(payload.error) : '',
    capabilities: (payload.capabilities as Record<string, boolean> | undefined) || {},
  };
}

function normalizeModel(raw: unknown): Model {
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

function normalizeTool(raw: unknown): ToolDescriptor {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    name: String(payload.name || payload.id || ''),
    description: String(payload.description || ''),
    category: String(payload.category || ''),
    inputSchema: (payload.inputSchema as Record<string, unknown> | undefined) || {},
    safetyLevel: String(payload.safetyLevel || ''),
    capabilities: Array.isArray(payload.capabilities) ? payload.capabilities.map(String) : [],
  };
}

function normalizePatProfile(raw: unknown): PatProfile | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  return {
    profileId: String(payload.profileId || ''),
    displayName: String(payload.displayName || 'Operator'),
    active: Boolean(payload.active),
    source: String(payload.source || 'template') as PatProfile['source'],
    priorities: Array.isArray(payload.priorities)
      ? payload.priorities.map((item: unknown) => {
          const priority = (item || {}) as Record<string, unknown>;
          return {
            id: String(priority.id || ''),
            label: String(priority.label || ''),
            weight: Number(priority.weight || 0),
          };
        })
      : [],
    goals: Array.isArray(payload.goals)
      ? payload.goals.map((item: unknown) => {
          const goal = (item || {}) as Record<string, unknown>;
          return {
            id: String(goal.id || ''),
            text: String(goal.text || ''),
            source: String(goal.source || 'template') as PatProfile['source'],
            updatedAt: String(goal.updatedAt || new Date().toISOString()),
          };
        })
      : [],
    tonePreference: {
      directness: String((payload.tonePreference as Record<string, unknown> | undefined)?.directness || 'balanced') as PatProfile['tonePreference']['directness'],
      formality: String((payload.tonePreference as Record<string, unknown> | undefined)?.formality || 'casual') as PatProfile['tonePreference']['formality'],
      preferBullets: Boolean((payload.tonePreference as Record<string, unknown> | undefined)?.preferBullets),
    },
    noiseFilters: Array.isArray(payload.noiseFilters) ? payload.noiseFilters.map(String) : [],
    lastUpdatedAt: String(payload.lastUpdatedAt || new Date().toISOString()),
    changelogCount: Number(payload.changelogCount || 0),
  };
}

function normalizeIdentityContext(raw: unknown): IdentityContextPayload | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  return {
    stableIdentity: payload.stableIdentity ? String(payload.stableIdentity) : null,
    situationalBriefing: payload.situationalBriefing ? String(payload.situationalBriefing) : null,
  };
}

function normalizePersonaHome(raw: unknown): PersonaHomeSummary | null {
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

function normalizePersonaSettings(raw: unknown): PersonaSettings | null {
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

function normalizePersonaContext(raw: unknown): PersonaContextPayload | null {
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

function normalizePersonaFlavorDraft(raw: unknown): PersonaFlavorDraft | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  return {
    displayName: String(payload.displayName || payload.name || 'Model Flavor'),
    identityMarkdown: String(payload.identityMarkdown || payload.identity || ''),
    soulMarkdown: String(payload.soulMarkdown || payload.soul || ''),
    notesMarkdown: String(payload.notesMarkdown || payload.notes || ''),
  };
}

function normalizeMemoryItem(raw: unknown): MemoryItem | null {
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

function normalizeIdentityContextRuntime(raw: unknown): IdentityContextRuntime | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  return {
    profileActive: Boolean(payload.profileActive),
    memoryCount: Number(payload.memoryCount || 0),
    memoryItemIds: Array.isArray(payload.memoryItemIds) ? payload.memoryItemIds.map((value) => String(value)).filter(Boolean) : [],
    personaActive: Boolean(payload.personaActive),
    personaId: payload.personaId ? String(payload.personaId) : null,
    personaFlavorId: payload.personaFlavorId ? String(payload.personaFlavorId) : null,
    personaPrivacyTier: payload.personaPrivacyTier ? String(payload.personaPrivacyTier) as IdentityContextRuntime['personaPrivacyTier'] : null,
  };
}

function normalizeProfileChangelogItem(raw: unknown): ProfileChangelogItem | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    kind: String(payload.kind || 'constraint_updated') as ProfileChangelogItem['kind'],
    summary: String(payload.summary || ''),
    detail: payload.detail ? String(payload.detail) : null,
    source: String(payload.source || 'template') as ProfileChangelogItem['source'],
    rationale: payload.rationale ? String(payload.rationale) : null,
    triggeredBySessionKey: payload.triggeredBySessionKey ? String(payload.triggeredBySessionKey) : null,
    changedAt: String(payload.changedAt || new Date().toISOString()),
  };
}

function normalizeReturnBriefing(raw: unknown): ReturnBriefingPayload | null {
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

function normalizePulse(raw: unknown): PulseRecord | null {
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

function normalizeDestination(raw: unknown): MessageDestination | null {
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

function normalizeTelegramRoute(raw: unknown): TelegramSessionRoute | null {
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

function normalizeMessagingConfig(raw: unknown): MessagingConfig | null {
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

function normalizePrompt(raw: unknown) {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    name: String(payload.name || payload.id || ''),
  };
}

function normalizeRuntimeContext(raw: unknown): RuntimeContext | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const workspaceRoot = String(payload.workspaceRoot || '').trim();
  if (!workspaceRoot) return null;
  return {
    workspaceRoot,
    fileToolScope: 'workspace_home_visible_roaming',
    shellToolScope: 'cwd_default',
    shellAllowlist: Array.isArray(payload.shellAllowlist) ? payload.shellAllowlist.map(String) : [],
    note: String(payload.note || '').trim(),
  };
}

function normalizeMergeState(raw: unknown): SessionMergeState | null {
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

function normalizeMessage(
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
  };
}

function extractFinalCandidateText(raw: string): string | null {
  function unwrapCandidatePayload(parsed: Record<string, unknown>): Record<string, unknown> | null {
    const finalType = parsed.state ?? parsed.type;
    if (finalType === 'FINAL_CANDIDATE') return parsed;
    const nested = parsed.FINAL_CANDIDATE;
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      return { state: 'FINAL_CANDIDATE', ...(nested as Record<string, unknown>) };
    }
    return null;
  }

  const candidate = raw.trim();
  if (!candidate || (!candidate.startsWith('{') && !candidate.startsWith('```'))) return null;
  let text = candidate;
  if (text.startsWith('```')) {
    const lines = text.split('\n');
    if (lines.length >= 3 && lines[lines.length - 1]?.trim().startsWith('```')) {
      text = lines.slice(1, -1).join('\n').trim();
    }
  }
  try {
    const parsed = JSON.parse(text) as Record<string, unknown>;
    const payload = unwrapCandidatePayload(parsed);
    if (!payload) return null;
    const answer = payload.answer ?? payload.content ?? payload.message ?? payload.response;
    return typeof answer === 'string' && answer.trim() ? answer : null;
  } catch {
    return null;
  }
}

export function normalizeAssistantDisplayText(raw: string): string {
  return extractFinalCandidateText(raw) ?? raw;
}

function normalizeMessageParts(raw: unknown): MessagePart[] | null {
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
    if (kind === 'tool_call') {
      const toolCall = payload.toolCall && typeof payload.toolCall === 'object' ? payload.toolCall as Record<string, unknown> : payload;
      parts.push({
        kind: 'tool_call',
        callId: String(toolCall.callId ?? payload.callId ?? ''),
        toolId: String(toolCall.toolId ?? payload.toolId ?? ''),
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
          at: typeof payload.at === 'string' ? payload.at : new Date().toISOString(),
        });
      }
    }
  }
  return parts.length > 0 ? parts : null;
}

class WsClient {
  private ws: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private connectPromise: Promise<void> | null = null;
  private connectResolve: (() => void) | null = null;
  private connectReject: ((error: Error) => void) | null = null;
  private connectRequestId: string | null = null;
  private requestCounter = 0;
  private pendingRequests = new Map<string, PendingRequest>();
  private modelLoads = new Map<string, Promise<Model[]>>();

  async connect(): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN && useAppStore.getState().wsStatus === 'connected') {
      return;
    }
    if (this.connectPromise) {
      return this.connectPromise;
    }

    const store = useAppStore.getState();
    store.setWsStatus('connecting');
    store.setAuthError(null);
    store.clearAppError();

    this.connectPromise = new Promise<void>((resolve, reject) => {
      this.connectResolve = resolve;
      this.connectReject = reject;
    });

    this.ws = new WebSocket(getWsUrl());
    this.ws.onmessage = (event) => {
      void this.handleSocketMessage(String(event.data));
    };
    this.ws.onerror = () => {
      if (useAppStore.getState().wsStatus !== 'auth_failed') {
        useAppStore.getState().setAppError('WebSocket connection error.');
      }
    };
    this.ws.onclose = () => {
      const store = useAppStore.getState();
      if (store.wsStatus !== 'auth_failed') {
        store.setWsStatus('disconnected');
      }
      this.rejectAllPending(new Error('connection closed'));
      // Mark any in-flight assistant messages as aborted so the UI doesn't show a stuck spinner.
      const pending = store.pendingAssistants;
      for (const runId of Object.keys(pending)) {
        const target = pending[runId];
        store.updateMessage(target.sessionKey, target.localId, {
          state: 'aborted',
          errorMessage: 'Connection lost.',
          optimistic: false,
        });
        store.clearPendingAssistant(runId);
      }
      if (store.activeRunId) {
        store.setActiveRunId(null);
      }
      this.connectPromise = null;
      this.connectResolve = null;
      this.connectReject = null;
      this.connectRequestId = null;
      if (store.wsStatus !== 'auth_failed') {
        this.scheduleReconnect();
      }
    };

    return this.connectPromise;
  }

  private scheduleReconnect() {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
    }
    this.reconnectTimer = window.setTimeout(() => {
      void this.connect();
    }, RECONNECT_DELAY_MS);
  }

  private nextRequestId(method: string): string {
    this.requestCounter += 1;
    return `${method}-${this.requestCounter}`;
  }

  private sendFrame(frame: Record<string, unknown>) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not connected');
    }
    this.ws.send(JSON.stringify(frame));
  }

  private async request<T extends Record<string, unknown>>(method: string, params: Record<string, unknown>): Promise<T> {
    await this.connect();
    const requestId = this.nextRequestId(method);
    return await new Promise<T>((resolve, reject) => {
      this.pendingRequests.set(requestId, {
        resolve: (payload) => resolve(payload as T),
        reject,
      });
      try {
        this.sendFrame({
          type: 'req',
          id: requestId,
          method,
          params,
        });
      } catch (error) {
        this.pendingRequests.delete(requestId);
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  private async handleSocketMessage(raw: string) {
    let frame: IncomingFrame;
    try {
      frame = JSON.parse(raw) as IncomingFrame;
    } catch (error) {
      console.error('Failed to parse WS message', error);
      return;
    }

    if (frame.type === 'event') {
      await this.handleEventFrame(frame);
      return;
    }
    this.handleResponseFrame(frame);
  }

  private async handleEventFrame(frame: EventFrame) {
    if (frame.event === 'connect.challenge') {
      const requestId = this.nextRequestId('connect');
      this.connectRequestId = requestId;
      this.sendFrame({
        type: 'req',
        id: requestId,
        method: 'connect',
        params: { auth: { token: getAuthToken() } },
      });
      return;
    }

    if (frame.event === 'chat') {
      this.handleChatEvent(frame.payload as unknown as ChatEventPayload);
      return;
    }

    if (frame.event === 'profile.changed') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      const profile = normalizePatProfile(payload.profile);
      const change = normalizeProfileChangelogItem(payload.change);
      if (profile) {
        useAppStore.getState().setPatProfile(profile);
      }
      if (change) {
        useAppStore.getState().prependProfileChangelogItem(change);
      }
      return;
    }

    if (frame.event === 'memory.changed') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      const item = normalizeMemoryItem(payload.item);
      if (item) {
        const store = useAppStore.getState();
        store.upsertMemoryItem(item);
        store.setLastMemoryChange({
          item,
          reason: payload.reason ? String(payload.reason) : 'upsert',
          sessionKey: payload.sessionKey ? String(payload.sessionKey) : null,
          runId: payload.runId ? String(payload.runId) : null,
        });
      }
      return;
    }

    if (frame.event === 'briefing.ready') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      useAppStore.getState().setReturnBriefing(normalizeReturnBriefing(payload.briefing));
      return;
    }

    if (frame.event === 'sessions.merge.updated') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      const sessionKey = payload.sessionKey ? String(payload.sessionKey) : '';
      const mergeState = normalizeMergeState(payload.mergeState);
      if (sessionKey && mergeState) {
        useAppStore.getState().setMergeState(sessionKey, mergeState);
      }
      if (sessionKey && payload.message) {
        const message = normalizeMessage(
          payload.message as PublicMessagePayload,
          sessionKey,
          `merge-brief-${sessionKey}-${(payload.message as PublicMessagePayload).runId || 'final'}`,
          'assistant',
          'final',
          false,
        );
        useAppStore.getState().addMessage(sessionKey, message);
      }
      return;
    }

    if (frame.event === 'pulse.updated') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      const pulse = normalizePulse(payload.pulse);
      if (pulse) {
        useAppStore.getState().upsertPulse(pulse);
      }
      return;
    }

    if (frame.event === 'messaging.updated') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      const config = normalizeMessagingConfig(payload.config);
      const store = useAppStore.getState();
      if (config) {
        store.setMessagingConfig(config);
        store.setDestinations(config.destinations);
        return;
      }
      if (Array.isArray(payload.routes)) {
        const current = store.messagingConfig;
        if (current) {
          store.setMessagingConfig({
            ...current,
            routes: payload.routes.map(normalizeTelegramRoute).filter((item): item is TelegramSessionRoute => item != null),
          });
        }
      }
    }
  }

  private handleResponseFrame(frame: ResponseFrame) {
    if (frame.id === this.connectRequestId) {
      if (frame.ok) {
        if (this.reconnectTimer !== null) {
          window.clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
        useAppStore.getState().setWsStatus('connected');
        this.connectResolve?.();
        this.connectPromise = null;
        this.connectResolve = null;
        this.connectReject = null;
        this.connectRequestId = null;
        void this.bootstrap();
      } else {
        const message = frame.error?.message || 'Authentication failed.';
        const store = useAppStore.getState();
        store.setWsStatus('auth_failed');
        store.setAuthError(message);
        this.connectReject?.(new Error(message));
        this.connectPromise = null;
        this.connectResolve = null;
        this.connectReject = null;
        this.connectRequestId = null;
        this.ws?.close();
      }
      return;
    }

    const pending = this.pendingRequests.get(frame.id);
    if (!pending) return;
    this.pendingRequests.delete(frame.id);
    if (!frame.ok) {
      pending.reject(new Error(frame.error?.message || 'Request failed'));
      return;
    }
    pending.resolve((frame.payload as Record<string, unknown> | undefined) || {});
  }

  private rejectAllPending(error: Error) {
    for (const [, pending] of this.pendingRequests) {
      pending.reject(error);
    }
    this.pendingRequests.clear();
  }

  private ensureDraftDefaults() {
    const store = useAppStore.getState();
    const preferredProvider = pickPreferredProvider(store.providers);
    const defaultProfile = store.profiles.find((item) => item.id === 'default')?.id || store.profiles[0]?.id || '';
    const defaultTaskMode = store.taskModes.find((item) => item.id === 'none')?.id || store.taskModes[0]?.id || '';
    const current = store.draftSettings;
    const nextProvider = store.providers.some((provider) => provider.id === current.provider && provider.available !== false)
      ? current.provider
      : preferredProvider;
    const knownModels = store.loadedModelProviders[nextProvider] ? store.modelsByProvider[nextProvider] || [] : [];
    const nextModel = nextProvider === current.provider
      ? (!knownModels.length || knownModels.some((item) => item.id === current.model) ? current.model : '')
      : '';
    const personaSettings = store.personaSettings;
    store.replaceDraftSettings({
      provider: nextProvider,
      model: nextModel,
      systemPromptId: store.profiles.some((item) => item.id === current.systemPromptId) ? current.systemPromptId : defaultProfile,
      taskPromptId: store.taskModes.some((item) => item.id === current.taskPromptId) ? current.taskPromptId : defaultTaskMode,
      personaId: current.personaId || personaSettings?.defaultPersonaId || 'default',
      personaFlavorId: current.personaFlavorId || '',
      personaPrivacyTier: current.personaPrivacyTier || personaSettings?.defaultPrivacyTier || 'private',
      workspaceRoot: current.workspaceRoot || store.runtimeContext?.workspaceRoot || '',
    });
  }

  private async bootstrap() {
    try {
      const [providersPayload, toolsPayload, promptsPayload, sessionsPayload, profilePayload, personaPayload, personaSettingsPayload, identityPayload, memoryPayload, changelogPayload, briefingPayload, runtimeContextPayload, pulsePayload, messagingPayload] = await Promise.all([
        this.request<{ providers: unknown[] }>('providers.list', {}),
        this.request<{ tools: unknown[] }>('tools.list', {}),
        this.request<{ profiles?: unknown[]; taskModes?: unknown[] }>('prompts.list', {}),
        this.request<{ sessions: unknown[] }>('sessions.list', { includeArchived: useAppStore.getState().showArchived }),
        this.request<{ profile?: unknown | null }>('profile.get', {}),
        this.request<{ persona?: unknown | null }>('persona.get', {}),
        this.request<{ settings?: unknown | null }>('persona.settings.get', {}),
        this.request<{ identityContext?: unknown | null }>('identity.context', {}),
        this.request<{ items?: unknown[] }>('memory.list', { limit: 24 }),
        this.request<{ changelog?: unknown[] }>('profile.changelog', { limit: 20 }),
        this.request<{ briefing?: unknown | null }>('briefing.get', {}),
        this.request<{ runtimeContext?: unknown | null }>('runtime.context', {}),
        this.request<{ pulses?: unknown[] }>('pulse.list', {}),
        this.request<{ config?: unknown | null }>('messaging.config.get', {}),
      ]);

      const store = useAppStore.getState();
      const providers = (providersPayload.providers || []).map(normalizeProvider);
      const sessions = (sessionsPayload.sessions || []).map(normalizeSession);
      store.setProviders(providers);
      store.setTools((toolsPayload.tools || []).map(normalizeTool));
      store.setPromptCatalog(
        (promptsPayload.profiles || []).map(normalizePrompt),
        (promptsPayload.taskModes || []).map(normalizePrompt),
      );
      store.setSessions(sessions);
      store.setPatProfile(normalizePatProfile(profilePayload.profile));
      store.setPersonaHome(normalizePersonaHome(personaPayload.persona));
      store.setPersonaSettings(normalizePersonaSettings(personaSettingsPayload.settings));
      store.setIdentityContext(normalizeIdentityContext(identityPayload.identityContext));
      store.setMemoryItems(
        Array.isArray(memoryPayload.items)
          ? memoryPayload.items.map(normalizeMemoryItem).filter((item): item is MemoryItem => item != null)
          : [],
      );
      store.setProfileChangelog(
        Array.isArray(changelogPayload.changelog)
          ? changelogPayload.changelog
              .map(normalizeProfileChangelogItem)
              .filter((item): item is ProfileChangelogItem => item != null)
          : [],
      );
      store.setReturnBriefing(normalizeReturnBriefing(briefingPayload.briefing));
      store.setRuntimeContext(normalizeRuntimeContext(runtimeContextPayload.runtimeContext));
      store.setPulses(Array.isArray(pulsePayload.pulses) ? pulsePayload.pulses.map(normalizePulse).filter((item): item is PulseRecord => item != null) : []);
      const messagingConfig = normalizeMessagingConfig(messagingPayload.config);
      if (messagingConfig) {
        store.setMessagingConfig(messagingConfig);
        store.setDestinations(messagingConfig.destinations);
      }
      this.ensureDraftDefaults();

      const currentKey = store.activeSessionKey;
      const hasCurrent = currentKey && sessions.some((session) => session.key === currentKey);
      const nextKey = hasCurrent ? currentKey : store.draftOpen ? null : sessions[0]?.key || null;
      store.setActiveSessionKey(nextKey);
      if (nextKey) {
        store.setDraftOpen(false);
        await this.loadHistory(nextKey);
      }
    } catch (error) {
      useAppStore.getState().setAppError(error instanceof Error ? error.message : 'Bootstrap failed.');
    }
  }

  async refreshSessions() {
    const payload = await this.request<{ sessions: unknown[] }>('sessions.list', {
      includeArchived: useAppStore.getState().showArchived,
    });
    useAppStore.getState().setSessions((payload.sessions || []).map(normalizeSession));
  }

  async loadModels(providerId: string): Promise<Model[]> {
    const store = useAppStore.getState();
    if (store.loadedModelProviders[providerId]) {
      return store.modelsByProvider[providerId] || [];
    }

    const inFlight = this.modelLoads.get(providerId);
    if (inFlight) return inFlight;

    const promise = this.request<{ models: unknown[] }>('models.list', { provider: providerId, kind: 'chat' })
      .then((payload) => {
        const models = (payload.models || []).map(normalizeModel);
        useAppStore.getState().setModelsForProvider(providerId, models);
        this.ensureDraftDefaults();
        this.modelLoads.delete(providerId);
        return models;
      })
      .catch((error) => {
        useAppStore.getState().setModelsForProvider(providerId, []);
        this.modelLoads.delete(providerId);
        throw error;
      });

    this.modelLoads.set(providerId, promise);
    return promise;
  }

  async loadHistory(sessionKey: string) {
    const payload = await this.request<{ sessionKey: string; messages: PublicMessagePayload[] }>('chat.history', {
      sessionKey,
      limit: 200,
    });
    const normalized = (payload.messages || []).map((message, index) =>
      normalizeMessage(
        message,
        sessionKey,
        `history-${sessionKey}-${index}-${message.timestamp || index}`,
        (message.role as Message['role']) || 'assistant',
        (message.state as Message['state']) || 'final',
      ),
    );
    useAppStore.getState().setMessages(sessionKey, normalized);
  }

  async browseWorkspaceRoot(): Promise<{ workspaceRoot: string | null; runtimeContext: RuntimeContext | null }> {
    const payload = await this.request<{ workspaceRoot?: string | null; runtimeContext?: unknown | null }>('runtime.workspace.browse', {});
    return {
      workspaceRoot: payload.workspaceRoot ? String(payload.workspaceRoot) : null,
      runtimeContext: normalizeRuntimeContext(payload.runtimeContext),
    };
  }

  async setWorkspaceRoot(workspaceRoot: string): Promise<RuntimeContext> {
    const payload = await this.request<{ workspaceRoot?: string | null; runtimeContext?: unknown | null }>('runtime.workspace.set', {
      workspaceRoot,
    });
    const runtimeContext = normalizeRuntimeContext(payload.runtimeContext);
    if (!runtimeContext) {
      throw new Error('Workspace root update returned no runtime context.');
    }
    return runtimeContext;
  }

  beginDraft() {
    const store = useAppStore.getState();
    store.setActiveSessionKey(null);
    store.setDraftOpen(true);
    store.setDraftStarterIntent(null);
    store.setMessages(DRAFT_TRANSCRIPT_SESSION_KEY, []);
    store.setSessionDrawerOpen(false);
    store.setAgentWorkspaceTab('messages');
    store.setInspectorTarget(null);
    store.clearAppError();
    this.ensureDraftDefaults();
  }

  async renameSession(key: string, title: string) {
    const payload = await this.request<{ session: unknown }>('sessions.rename', { key, title: title || undefined });
    if (payload.session) {
      useAppStore.getState().upsertSession(normalizeSession(payload.session));
    }
  }

  async archiveSession(key: string, archived: boolean) {
    const payload = await this.request<{ session: unknown }>('sessions.archive', { key, archived });
    if (payload.session) {
      useAppStore.getState().upsertSession(normalizeSession(payload.session));
    }
    const store = useAppStore.getState();
    if (!archived) {
      // Restoring: switch to active view and re-select the session so it's immediately visible.
      store.setShowArchived(false);
      store.setActiveSessionKey(key);
      store.setDraftOpen(false);
    } else if (store.activeSessionKey === key) {
      // Archiving the currently active session — deselect it.
      store.setActiveSessionKey(null);
    }
    await this.refreshSessions();
  }

  async debugCopySession(key: string): Promise<Session> {
    const payload = await this.request<{ session: unknown }>('sessions.debugCopy', { key });
    const session = normalizeSession(payload.session);
    const store = useAppStore.getState();
    store.upsertSession(session);
    store.setShowArchived(false);
    store.setActiveSessionKey(session.key);
    store.setDraftOpen(false);
    await this.refreshSessions();
    await this.loadHistory(session.key);
    return session;
  }

  async createMergedSession(params: {
    sourceSessionKeys: string[];
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
    workspaceRoot: string;
    title?: string;
  }): Promise<{ session: Session; mergeState: SessionMergeState | null }> {
    const payload = await this.request<{ session: unknown; mergeState?: unknown | null }>('sessions.merge.create', {
      sourceSessionKeys: params.sourceSessionKeys,
      provider: params.provider,
      model: params.model || undefined,
      systemPromptId: params.systemPromptId || undefined,
      taskPromptId: params.taskPromptId || undefined,
      workspaceRoot: params.workspaceRoot || undefined,
      title: params.title || undefined,
    });
    return {
      session: normalizeSession(payload.session),
      mergeState: normalizeMergeState(payload.mergeState),
    };
  }

  async listPulses(): Promise<PulseRecord[]> {
    const payload = await this.request<{ pulses?: unknown[] }>('pulse.list', {});
    return Array.isArray(payload.pulses)
      ? payload.pulses.map(normalizePulse).filter((item): item is PulseRecord => item != null)
      : [];
  }

  async getMessagingConfig(): Promise<MessagingConfig | null> {
    const payload = await this.request<{ config?: unknown | null }>('messaging.config.get', {});
    return normalizeMessagingConfig(payload.config);
  }

  async listMessagingDestinations(): Promise<MessageDestination[]> {
    const payload = await this.request<{ destinations?: unknown[] }>('messaging.destinations.list', {});
    return Array.isArray(payload.destinations)
      ? payload.destinations.map(normalizeDestination).filter((item): item is MessageDestination => item != null)
      : [];
  }

  async listMessagingRoutes(): Promise<TelegramSessionRoute[]> {
    const payload = await this.request<{ routes?: unknown[] }>('messaging.routes.list', {});
    return Array.isArray(payload.routes)
      ? payload.routes.map(normalizeTelegramRoute).filter((item): item is TelegramSessionRoute => item != null)
      : [];
  }

  async updateMessagingApprovalPolicy(params: {
    requireApprovalByDefault: boolean;
    hardlineBlocklist?: string[];
  }): Promise<MessagingConfig | null> {
    const payload = await this.request<{ config?: unknown | null }>('messaging.config.update', {
      approvalPolicy: {
        requireApprovalByDefault: params.requireApprovalByDefault,
        hardlineBlocklist: params.hardlineBlocklist || [],
      },
    });
    return normalizeMessagingConfig(payload.config);
  }

  async updateTelegramRuntimeDefaults(params: {
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
  }): Promise<MessagingConfig | null> {
    const payload = await this.request<{ config?: unknown | null }>('messaging.config.update', {
      telegramDefaults: {
        provider: params.provider || undefined,
        model: params.model || undefined,
        systemPromptId: params.systemPromptId || undefined,
        taskPromptId: params.taskPromptId || undefined,
      },
    });
    return normalizeMessagingConfig(payload.config);
  }

  async testMessagingPlatform(platform = 'telegram'): Promise<{
    config: MessagingConfig | null;
    result: {
      ok: boolean;
      connectionStatus: 'connected' | 'disconnected' | 'error' | 'unconfigured';
      message: string;
      verifiedAt: string | null;
    };
  }> {
    const payload = await this.request<{
      config?: unknown | null;
      result?: Record<string, unknown>;
    }>('messaging.test', { platform });
    return {
      config: normalizeMessagingConfig(payload.config),
      result: {
        ok: Boolean(payload.result?.ok),
        connectionStatus:
          payload.result?.connectionStatus === 'connected' ||
          payload.result?.connectionStatus === 'disconnected' ||
          payload.result?.connectionStatus === 'error' ||
          payload.result?.connectionStatus === 'unconfigured'
            ? payload.result.connectionStatus
            : 'unconfigured',
        message: payload.result?.message ? String(payload.result.message) : '',
        verifiedAt: payload.result?.verifiedAt ? String(payload.result.verifiedAt) : null,
      },
    };
  }

  async upsertMessagingDestination(destination: {
    id?: string;
    platform: string;
    target: string;
    displayName: string;
    threadLabel?: string | null;
    isDefault: boolean;
    requiresApproval: boolean;
    status?: 'configured' | 'unconfigured' | 'error';
  }): Promise<{ destination: MessageDestination | null; config: MessagingConfig | null }> {
    const payload = await this.request<{ destination?: unknown | null; config?: unknown | null }>(
      'messaging.destinations.upsert',
      { destination },
    );
    return {
      destination: normalizeDestination(payload.destination),
      config: normalizeMessagingConfig(payload.config),
    };
  }

  async deleteMessagingDestination(destinationId: string): Promise<{ deleted: boolean; config: MessagingConfig | null }> {
    const payload = await this.request<{ deleted?: unknown; config?: unknown | null }>('messaging.destinations.delete', {
      destinationId,
    });
    return {
      deleted: Boolean(payload.deleted),
      config: normalizeMessagingConfig(payload.config),
    };
  }

  async upsertMessagingRoute(route: {
    id?: string;
    platform: string;
    chatId: string;
    threadId?: string | null;
    sessionKey: string;
    titleOverride?: string | null;
  }): Promise<{ route: TelegramSessionRoute | null; routes: TelegramSessionRoute[] }> {
    const payload = await this.request<{ route?: unknown | null; routes?: unknown[] }>('messaging.routes.upsert', {
      route,
    });
    return {
      route: normalizeTelegramRoute(payload.route),
      routes: Array.isArray(payload.routes)
        ? payload.routes.map(normalizeTelegramRoute).filter((item): item is TelegramSessionRoute => item != null)
        : [],
    };
  }

  async deleteMessagingRoute(routeId: string): Promise<{ deleted: boolean; routes: TelegramSessionRoute[] }> {
    const payload = await this.request<{ deleted?: unknown; routes?: unknown[] }>('messaging.routes.delete', {
      routeId,
    });
    return {
      deleted: Boolean(payload.deleted),
      routes: Array.isArray(payload.routes)
        ? payload.routes.map(normalizeTelegramRoute).filter((item): item is TelegramSessionRoute => item != null)
        : [],
    };
  }

  async createPulseFromSession(params: {
    sessionKey: string;
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
  }): Promise<PulseRecord> {
    const payload = await this.request<{ pulse: unknown }>('pulse.create_from_session', {
      sessionKey: params.sessionKey,
      provider: params.provider,
      model: params.model || undefined,
      systemPromptId: params.systemPromptId || undefined,
      taskPromptId: params.taskPromptId || undefined,
    });
    const pulse = normalizePulse(payload.pulse);
    if (!pulse) throw new Error('Pulse creation returned no pulse.');
    return pulse;
  }

  async dismissPulse(pulseId: string): Promise<PulseRecord> {
    const payload = await this.request<{ pulse: unknown }>('pulse.dismiss', { pulseId });
    const pulse = normalizePulse(payload.pulse);
    if (!pulse) throw new Error('Pulse dismiss returned no pulse.');
    return pulse;
  }

  async savePulses(params: {
    pulseIds: string[];
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
    workspaceRoot: string;
  }): Promise<{ session: Session; mergeState: SessionMergeState | null }> {
    const payload = await this.request<{ session: unknown; mergeState?: unknown | null }>('pulse.save', {
      pulseIds: params.pulseIds,
      provider: params.provider,
      model: params.model || undefined,
      systemPromptId: params.systemPromptId || undefined,
      taskPromptId: params.taskPromptId || undefined,
      workspaceRoot: params.workspaceRoot || undefined,
    });
    return {
      session: normalizeSession(payload.session),
      mergeState: normalizeMergeState(payload.mergeState),
    };
  }

  async exportSession(key: string): Promise<SessionExportPayload> {
    const payload = await this.request<{
      session: unknown;
      messages: PublicMessagePayload[];
      markdown: string;
    }>('sessions.export', { key });
    return {
      session: normalizeSession(payload.session),
      messages: (payload.messages || []).map((message) => message),
      markdown: String(payload.markdown || ''),
    };
  }

  async listSessionRuns(key: string, limit = 20): Promise<SessionRunRecord[]> {
    const payload = await this.request<{ runs?: SessionRunRecord[] }>('sessions.runs', { key, limit });
    return Array.isArray(payload.runs) ? payload.runs : [];
  }

  async upsertMemory(input: {
    id?: string | null;
    category: MemoryItem['category'];
    title: string;
    summary: string;
    detail?: string | null;
    tags?: string[];
  }): Promise<MemoryItem | null> {
    const payload = await this.request<{ memoryItem?: unknown | null }>('memory.upsert', {
      id: input.id || undefined,
      category: input.category,
      title: input.title,
      summary: input.summary,
      detail: input.detail || undefined,
      tags: input.tags || [],
    });
    return normalizeMemoryItem(payload.memoryItem);
  }

  async archiveMemory(id: string, archived = true): Promise<MemoryItem | null> {
    const payload = await this.request<{ memoryItem?: unknown | null }>('memory.archive', {
      id,
      archived,
    });
    return normalizeMemoryItem(payload.memoryItem);
  }

  async updatePersonaSettings(settings: PersonaSettings): Promise<PersonaSettings | null> {
    const payload = await this.request<{ settings?: unknown | null }>('persona.settings.update', { ...settings });
    const normalized = normalizePersonaSettings(payload.settings);
    useAppStore.getState().setPersonaSettings(normalized);
    return normalized;
  }

  async getPersonaSummary(options?: {
    provider?: string | null;
    model?: string | null;
    privacyTier?: string | null;
  }): Promise<PersonaHomeSummary | null> {
    const payload = await this.request<{ persona?: unknown | null }>('persona.get', {
      provider: options?.provider || undefined,
      model: options?.model || undefined,
      privacyTier: options?.privacyTier || undefined,
    });
    const normalized = normalizePersonaHome(payload.persona);
    useAppStore.getState().setPersonaHome(normalized);
    return normalized;
  }

  async getPersonaContext(options?: {
    provider?: string | null;
    model?: string | null;
    privacyTier?: string | null;
    query?: string | null;
  }): Promise<PersonaContextPayload | null> {
    const payload = await this.request<{ personaContext?: unknown | null }>('persona.context', {
      provider: options?.provider || undefined,
      model: options?.model || undefined,
      privacyTier: options?.privacyTier || undefined,
      query: options?.query || undefined,
    });
    const normalized = normalizePersonaContext(payload.personaContext);
    useAppStore.getState().setPersonaContext(normalized);
    return normalized;
  }

  async draftPersonaFlavor(options: {
    provider: string;
    model?: string | null;
  }): Promise<PersonaFlavorDraft | null> {
    const payload = await this.request<{ draft?: unknown | null }>('persona.flavor.draft', {
      provider: options.provider,
      model: options.model || undefined,
    });
    const normalized = normalizePersonaFlavorDraft(payload.draft);
    const store = useAppStore.getState();
    store.setPersonaFlavorDraft(normalized);
    store.setPersonaFlavorReviewOpen(Boolean(normalized));
    return normalized;
  }

  async savePersonaFlavor(options: { provider: string; model?: string; draft: Record<string, unknown> }): Promise<PersonaHomeSummary | null> {
    await this.request('persona.flavor.save', {
      provider: options.provider,
      model: options.model || undefined,
      draft: options.draft,
    });
    const payload = await this.request<{ persona?: unknown | null }>('persona.get', {
      provider: options.provider,
      model: options.model || undefined,
    });
    const normalized = normalizePersonaHome(payload.persona);
    useAppStore.getState().setPersonaHome(normalized);
    return normalized;
  }

  async listSessionArtifacts(key: string, limit = 50): Promise<SessionArtifactRecord[]> {
    const payload = await this.request<{ artifacts?: SessionArtifactRecord[] }>('sessions.artifacts', { key, limit });
    return Array.isArray(payload.artifacts) ? payload.artifacts : [];
  }

  async resolveSessionRun(key: string, runId: string): Promise<SessionRunRecord | null> {
    const payload = await this.request<{ run?: SessionRunRecord | null }>('sessions.run', { key, runId });
    return payload.run ?? null;
  }

  async resolveSessionState(key: string): Promise<SessionStateRecord | null> {
    const payload = await this.request<{ state?: SessionStateRecord | null }>('sessions.state', { key });
    return payload.state ?? null;
  }

  async resolveMergeState(key: string): Promise<SessionMergeState | null> {
    const payload = await this.request<{ mergeState?: unknown | null }>('sessions.merge.state', { key });
    return normalizeMergeState(payload.mergeState);
  }

  async optimizePrompt(options: {
    prompt: string;
    provider?: string;
    model?: string;
    customTransform?: string;
  }): Promise<PromptOptimizationResult> {
    const payload = await this.request<{
      variants?: PromptOptimizationVariant[];
      provider?: string;
      model?: string | null;
    }>('prompts.optimize', {
      prompt: options.prompt,
      provider: options.provider || undefined,
      model: options.model || undefined,
      customTransform: options.customTransform || undefined,
    });
    return {
      variants: Array.isArray(payload.variants) ? payload.variants.map((variant) => ({
        id: String(variant.id || ''),
        label: String(variant.label || ''),
        prompt: String(variant.prompt || ''),
        rationale: String(variant.rationale || ''),
      })).filter((variant) => variant.id && variant.prompt) : [],
      provider: String(payload.provider || options.provider || ''),
      model: payload.model == null ? null : String(payload.model),
    };
  }

  async sendMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed) return;

    const store = useAppStore.getState();
    store.clearAppError();

    let session = store.sessions.find((item) => item.key === store.activeSessionKey) || null;
    if (!session) {
      const draft = store.draftSettings;
      const createPayload = await this.request<{ session: unknown }>('sessions.create', {
        provider: draft.provider,
        model: draft.model || undefined,
        systemPromptId: draft.systemPromptId || undefined,
        taskPromptId: draft.taskPromptId || undefined,
        personaId: draft.personaId || undefined,
        personaFlavorId: draft.personaFlavorId || undefined,
        personaPrivacyTier: draft.personaPrivacyTier || undefined,
        workspaceRoot: draft.workspaceRoot || undefined,
        starterIntentId: store.draftStarterIntent?.id || undefined,
      });
      session = normalizeSession(createPayload.session);
      store.upsertSession(session);
      store.setActiveSessionKey(session.key);
      store.setDraftOpen(false);
      store.setDraftStarterIntent(null);
    }

    const userMessage: Message = {
      localId: makeLocalId('user'),
      sessionKey: session.key,
      runId: null,
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString(),
      provider: session.provider,
      model: session.model,
      providerSessionId: session.providerSessionId,
      state: 'final',
      toolExecution: null,
      errorMessage: null,
      optimistic: true,
    };
    store.addMessage(session.key, userMessage);

    try {
      const payload = await this.request<{ runId?: string; status?: string }>('chat.send', {
        sessionKey: session.key,
        message: trimmed,
        provider: session.provider,
        model: session.model || undefined,
        systemPromptId: session.systemPromptId || undefined,
        taskPromptId: session.taskPromptId || undefined,
        personaId: session.personaId || undefined,
        personaFlavorId: session.personaFlavorId || undefined,
        personaPrivacyTier: session.personaPrivacyTier || undefined,
      });
      const runId = payload.runId ? String(payload.runId) : null;
      const status = payload.status ? String(payload.status) : '';

      if (status === 'in_flight') {
        throw new Error('This session already has a reply in progress.');
      }

      if (runId) {
        // Clear live tool calls and turn state from the previous run.
        store.clearLiveToolCalls();
        store.setLastTurnState(null);

        const assistantMessage: Message = {
          localId: makeLocalId('assistant'),
          sessionKey: session.key,
          runId,
          role: 'assistant',
          content: '',
          timestamp: new Date().toISOString(),
          provider: session.provider,
          model: session.model,
          providerSessionId: session.providerSessionId,
          state: 'delta',
          toolExecution: null,
          errorMessage: null,
          optimistic: true,
        };
        store.addMessage(session.key, assistantMessage);
        store.registerPendingAssistant(runId, session.key, assistantMessage.localId);
        store.setActiveRunId(runId);
      }
    } catch (error) {
      store.setAppError(error instanceof Error ? error.message : 'Unable to send message.');
      store.addMessage(session.key, {
        localId: makeLocalId('system'),
        sessionKey: session.key,
        runId: null,
        role: 'system',
        content: error instanceof Error ? error.message : 'Unable to send message.',
        timestamp: new Date().toISOString(),
        provider: null,
        model: null,
        providerSessionId: null,
        state: 'error',
        toolExecution: null,
        errorMessage: error instanceof Error ? error.message : 'Unable to send message.',
        optimistic: false,
      });
      throw error;
    }
  }

  async abortActiveRun() {
    const store = useAppStore.getState();
    if (!store.activeRunId && !store.activeSessionKey) return;
    await this.request('chat.abort', {
      sessionKey: store.activeSessionKey || undefined,
      runId: store.activeRunId || undefined,
    });
  }

  // ---------------------------------------------------------------------------
  // Provider auth RPCs
  // ---------------------------------------------------------------------------

  async providerAuthStatus(providerId: string): Promise<ProviderAuthStatus> {
    const payload = await this.request<{ status: ProviderAuthStatus }>('providerAuth.status', { provider: providerId });
    return payload.status;
  }

  async providerAuthBeginLogin(providerId: string, redirectUri?: string): Promise<{ loginId: string; authorizeUrl: string; redirectUri: string; state: string }> {
    const payload = await this.request<{ login: { loginId: string; authorizeUrl: string; redirectUri: string; state: string } }>(
      'providerAuth.beginLogin',
      { provider: providerId, redirectUri: redirectUri ?? undefined },
    );
    return payload.login;
  }

  async providerAuthLogout(providerId: string): Promise<ProviderAuthStatus> {
    const payload = await this.request<{ status: ProviderAuthStatus }>('providerAuth.logout', { provider: providerId });
    return payload.status;
  }

  private handleChatEvent(payload: ChatEventPayload) {
    const store = useAppStore.getState();
    const runId = payload.runId ? String(payload.runId) : null;
    const sessionKey = payload.sessionKey;
    const toolExecution = normalizeToolExecution(payload.toolExecution);

    if (payload.state === 'tool_called') {
      const rawToolCall = payload.toolCall as Record<string, unknown> | null | undefined;
      if (rawToolCall && runId) {
        const toolId = String(rawToolCall.toolId ?? rawToolCall.tool_id ?? 'tool');
        const liveId = String(rawToolCall.callId ?? rawToolCall.call_id ?? `${runId}:${rawToolCall.step ?? store.liveToolCalls.length}:${toolId}`);
        store.pushLiveToolCall({
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
          const callId = String(rawToolCall.callId ?? rawToolCall.call_id ?? `${runId}:${rawToolCall.step ?? store.liveToolCalls.length}:${rawToolCall.toolId ?? rawToolCall.tool_id ?? 'tool'}`);
          const hint = rawToolCall.hint
            ? String(rawToolCall.hint)
            : rawToolCall.arguments && typeof rawToolCall.arguments === 'object'
              ? JSON.stringify(rawToolCall.arguments)
              : null;
          store.appendMessagePart(target.sessionKey, target.localId, {
            kind: 'tool_call',
            callId,
            toolId,
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
        const existingMatch = [...store.liveToolCalls]
          .reverse()
          .find((call) => call.state === 'running' && call.toolId === toolExecution.toolId);
        store.pushLiveToolCall({
          id: existingMatch?.id || toolExecution.callId || `${runId}:${toolExecution.toolId}:${store.liveToolCalls.length}`,
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

      if (runId && store.activeRunId === runId) {
        store.setActiveRunId(null);
      }

      // Capture turnState snapshot from final event before clearing live calls.
      if (payload.state === 'final') {
        const ts = (payload as unknown as Record<string, unknown>).turnState;
        if (ts && typeof ts === 'object') {
          const t = ts as Record<string, unknown>;
          const snapshot: TurnStateSnapshot = {
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
          store.setLastTurnState(snapshot);
        }
        const identityContext = normalizeIdentityContextRuntime((payload as unknown as Record<string, unknown>).identityContext);
        if (identityContext) {
          store.setSessionIdentityUsage(sessionKey, identityContext);
        }
        // Don't clear liveToolCalls immediately — RunActivityPanel takes over after
        // a short delay when the activity data reloads.  Components that display
        // live calls should switch to the run record once it's available.
      }

      // Only close the draft if the completed run belongs to the currently active session.
      // Closing unconditionally would destroy a new draft the user opened while a prior run finished.
      if (sessionKey && store.activeSessionKey === sessionKey) {
        store.setDraftOpen(false);
      }
      void this.refreshSessions();
    }
  }
}

export const wsClient = new WsClient();
