import { useAppStore } from '../store/useAppStore';
import type {
  MemoryItem,
  PersonaContextPayload,
  PersonaFlavorDraft,
  PersonaHomeSummary,
  PersonaListItem,
  PersonaSettings,
  UserNoteProposal,
} from '../types/backend';
import {
  normalizeMemoryItem,
  normalizePersonaContext,
  normalizePersonaFlavorDraft,
  normalizePersonaHome,
  normalizePersonaSettings,
  normalizeUserNote,
} from './wsNormalizers';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

export async function upsertMemoryRpc(
  request: WsRpcRequest,
  input: {
    id?: string | null;
    category: MemoryItem['category'];
    title: string;
    summary: string;
    detail?: string | null;
    tags?: string[];
  },
): Promise<MemoryItem | null> {
  const payload = await request<{ memoryItem?: unknown | null }>('memory.upsert', {
    id: input.id || undefined,
    category: input.category,
    title: input.title,
    summary: input.summary,
    detail: input.detail || undefined,
    tags: input.tags || [],
  });
  return normalizeMemoryItem(payload.memoryItem);
}

export async function archiveMemoryRpc(request: WsRpcRequest, id: string, archived = true): Promise<MemoryItem | null> {
  const payload = await request<{ memoryItem?: unknown | null }>('memory.archive', {
    id,
    archived,
  });
  return normalizeMemoryItem(payload.memoryItem);
}

export async function approveMemoryRpc(
  request: WsRpcRequest,
  id: string,
  edits?: { category?: MemoryItem['category']; title?: string; summary?: string; detail?: string | null },
): Promise<MemoryItem | null> {
  const payload = await request<{ memoryItem?: unknown | null }>('memory.approve', {
    id,
    category: edits?.category,
    title: edits?.title,
    summary: edits?.summary,
    detail: edits?.detail ?? undefined,
  });
  return normalizeMemoryItem(payload.memoryItem);
}

export async function discardMemoryRpc(request: WsRpcRequest, id: string): Promise<boolean> {
  const payload = await request<{ discarded?: unknown }>('memory.discard', { id });
  return Boolean(payload.discarded);
}

export async function refreshMemoryDraftsRpc(request: WsRpcRequest): Promise<void> {
  try {
    const payload = await request<{ items?: unknown[] }>('memory.list', { status: 'draft', limit: 24 });
    const drafts = Array.isArray(payload.items)
      ? payload.items.map(normalizeMemoryItem).filter((item): item is MemoryItem => item != null)
      : [];
    useAppStore.getState().setMemoryDrafts(drafts);
  } catch {
    /* non-fatal: drafts surface refreshes on the next trigger */
  }
}

export async function approveUserNoteRpc(
  request: WsRpcRequest,
  id: string,
  edits?: { targetSection?: string; summary?: string; body?: string },
): Promise<UserNoteProposal | null> {
  const payload = await request<{ userNote?: unknown | null }>('userNotes.approve', {
    id,
    targetSection: edits?.targetSection,
    summary: edits?.summary,
    body: edits?.body,
  });
  return normalizeUserNote(payload.userNote);
}

export async function discardUserNoteRpc(request: WsRpcRequest, id: string): Promise<boolean> {
  const payload = await request<{ discarded?: unknown }>('userNotes.discard', { id });
  return Boolean(payload.discarded);
}

export async function refreshUserNoteDraftsRpc(request: WsRpcRequest): Promise<void> {
  try {
    const payload = await request<{ items?: unknown[] }>('userNotes.list', { status: 'draft' });
    const drafts = Array.isArray(payload.items)
      ? payload.items.map(normalizeUserNote).filter((item): item is UserNoteProposal => item != null)
      : [];
    useAppStore.getState().setUserNoteDrafts(drafts);
  } catch {
    /* non-fatal: drafts surface refreshes on the next trigger */
  }
}

export async function updatePersonaSettingsRpc(
  request: WsRpcRequest,
  settings: PersonaSettings,
): Promise<PersonaSettings | null> {
  const payload = await request<{ settings?: unknown | null }>('persona.settings.update', { ...settings });
  const normalized = normalizePersonaSettings(payload.settings);
  useAppStore.getState().setPersonaSettings(normalized);
  return normalized;
}

export async function listPersonasRpc(
  request: WsRpcRequest,
  runtime?: { provider?: string | null; model?: string | null },
): Promise<PersonaListItem[]> {
  const payload = await request<{ personas?: PersonaListItem[] }>('persona.list', {
    provider: runtime?.provider || undefined,
    model: runtime?.model || undefined,
  });
  return Array.isArray(payload.personas) ? payload.personas : [];
}

export async function createPersonaRpc(
  request: WsRpcRequest,
  personaId: string,
  displayName?: string,
): Promise<PersonaListItem | null> {
  const payload = await request<{ persona?: PersonaListItem | null }>('persona.create', { personaId, displayName });
  return payload.persona ?? null;
}

export async function selectPersonaRpc(
  request: WsRpcRequest,
  personaId: string,
  runtime?: { provider?: string | null; model?: string | null },
): Promise<PersonaSettings | null> {
  const payload = await request<{ settings?: unknown | null }>('persona.select', {
    personaId,
    provider: runtime?.provider || undefined,
    model: runtime?.model || undefined,
  });
  const normalized = normalizePersonaSettings(payload.settings);
  useAppStore.getState().setPersonaSettings(normalized);
  return normalized;
}

export async function getPersonaSummaryRpc(
  request: WsRpcRequest,
  options?: {
    provider?: string | null;
    model?: string | null;
    privacyTier?: string | null;
  },
): Promise<PersonaHomeSummary | null> {
  const payload = await request<{ persona?: unknown | null }>('persona.get', {
    provider: options?.provider || undefined,
    model: options?.model || undefined,
    privacyTier: options?.privacyTier || undefined,
  });
  const normalized = normalizePersonaHome(payload.persona);
  useAppStore.getState().setPersonaHome(normalized);
  return normalized;
}

export async function getPersonaContextRpc(
  request: WsRpcRequest,
  options?: {
    provider?: string | null;
    model?: string | null;
    privacyTier?: string | null;
    query?: string | null;
  },
): Promise<PersonaContextPayload | null> {
  const payload = await request<{ personaContext?: unknown | null }>('persona.context', {
    provider: options?.provider || undefined,
    model: options?.model || undefined,
    privacyTier: options?.privacyTier || undefined,
    query: options?.query || undefined,
  });
  const normalized = normalizePersonaContext(payload.personaContext);
  useAppStore.getState().setPersonaContext(normalized);
  return normalized;
}

export async function draftPersonaFlavorRpc(
  request: WsRpcRequest,
  options: {
    provider: string;
    model?: string | null;
  },
): Promise<PersonaFlavorDraft | null> {
  const payload = await request<{ draft?: unknown | null }>('persona.flavor.draft', {
    provider: options.provider,
    model: options.model || undefined,
  });
  const normalized = normalizePersonaFlavorDraft(payload.draft);
  const store = useAppStore.getState();
  store.setPersonaFlavorDraft(normalized);
  store.setPersonaFlavorReviewOpen(Boolean(normalized));
  return normalized;
}

export async function savePersonaFlavorRpc(
  request: WsRpcRequest,
  options: { provider: string; model?: string; draft: Record<string, unknown> },
): Promise<PersonaHomeSummary | null> {
  await request('persona.flavor.save', {
    provider: options.provider,
    model: options.model || undefined,
    draft: options.draft,
  });
  const payload = await request<{ persona?: unknown | null }>('persona.get', {
    provider: options.provider,
    model: options.model || undefined,
  });
  const normalized = normalizePersonaHome(payload.persona);
  useAppStore.getState().setPersonaHome(normalized);
  return normalized;
}
