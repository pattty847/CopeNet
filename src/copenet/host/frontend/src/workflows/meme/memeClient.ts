// Meme ideation client. Targets POST /api/v1/memes/ideate with bearer auth.
// Accepts two wire shapes (envelope or bare array) and normalizes to MemeGeneration.
// Falls back to local mock ideation when the endpoint is absent (404 / network fail)
// so the UI is fully exercisable before the backend ships.

import type {
  MemeBrief,
  MemeCandidate,
  MemeGeneration,
  MemeRefinementMessage,
  MemeRefinementResult,
} from './types';

const DEFAULT_DEV_TOKEN = 'dev-token';

function getHttpBaseUrl(): string {
  const envUrl = import.meta.env.VITE_COPNET_API_URL?.trim();
  if (envUrl) return envUrl.replace(/\/$/, '');
  return window.location.origin;
}

function getAuthToken(): string {
  const envToken = import.meta.env.VITE_COPNET_TOKEN?.trim() || '';
  const fromWindow = typeof window.COPNET_TOKEN === 'string' ? window.COPNET_TOKEN.trim() : '';
  const fromStorage = window.localStorage.getItem('copnet.token') || '';
  const fromMeta = document.querySelector('meta[name="copnet-token"]')?.getAttribute('content')?.trim() || '';
  return envToken || fromWindow || fromStorage || fromMeta || DEFAULT_DEV_TOKEN;
}

function clientId(prefix: string): string {
  const rand = Math.random().toString(36).slice(2, 8);
  return `${prefix}-${Date.now().toString(36)}-${rand}`;
}

function coerceString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (value == null) return fallback;
  return String(value);
}

function coerceBool(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') return value;
  if (value == null) return fallback;
  if (typeof value === 'string') return ['true', '1', 'yes'].includes(value.toLowerCase());
  return Boolean(value);
}

function coerceStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((v) => coerceString(v)).filter((v) => v.length > 0);
  }
  return [];
}

function normalizeCandidate(raw: unknown, idx: number): MemeCandidate {
  const r = (raw ?? {}) as Record<string, unknown>;
  return {
    id: clientId(`cand-${idx}`),
    direction: coerceString(r.direction ?? r.angle, '(no direction)'),
    format: coerceString(r.format ?? r.template ?? 'unknown', 'unknown'),
    text: coerceString(r.text ?? r.meme_text ?? r.caption_text, ''),
    optionalCaption: (() => {
      const v = r.optional_caption ?? r.optionalCaption ?? r.caption;
      if (v == null || v === '') return null;
      return coerceString(v);
    })(),
    needsVisualContext: coerceBool(r.needs_visual_context ?? r.needsVisualContext, false),
    notes: (() => {
      const v = r.notes ?? r.note;
      if (v == null || v === '') return null;
      return coerceString(v);
    })(),
    warnings: coerceStringArray(r.warnings),
  };
}

interface IdeateWireEnvelope {
  candidates?: unknown;
  ideas?: unknown;       // alternate key
  results?: unknown;     // alternate key
  model?: unknown;
  preset?: unknown;
  schema_version?: unknown;
  schemaVersion?: unknown;
  prompt_version?: unknown;
  promptVersion?: unknown;
  knowledge_pack_version?: unknown;
  knowledgePackVersion?: unknown;
  artifact_shell?: unknown;
  artifactShell?: unknown;
  mutation_notes?: unknown;
  mutationNotes?: unknown;
  judge_warnings?: unknown;
  judgeWarnings?: unknown;
  warnings?: unknown;
  latency_ms?: unknown;
  latencyMs?: unknown;
}

interface RefineWireEnvelope {
  assistantReply?: unknown;
  suggestedCandidates?: unknown;
  warnings?: unknown;
  judgeWarnings?: unknown;
  mutationNotes?: unknown;
  artifactShell?: unknown;
}

function extractCandidateList(raw: unknown): unknown[] {
  if (Array.isArray(raw)) return raw;
  const env = (raw ?? {}) as IdeateWireEnvelope;
  if (Array.isArray(env.candidates)) return env.candidates;
  if (Array.isArray(env.ideas)) return env.ideas;
  if (Array.isArray(env.results)) return env.results;
  return [];
}

function normalizeGeneration(raw: unknown, brief: MemeBrief, source: 'server' | 'mock'): MemeGeneration {
  const env = (raw ?? {}) as IdeateWireEnvelope;
  const list = extractCandidateList(raw);
  const candidates = list.map((c, i) => normalizeCandidate(c, i));
  return {
    id: clientId('gen'),
    generatedAt: new Date().toISOString(),
    brief,
    candidates,
    model: coerceString(env.model, '') || null,
    preset: coerceString(env.preset, '') || brief.preset || null,
    schemaVersion: coerceString(env.schemaVersion ?? env.schema_version, '') || null,
    promptVersion: coerceString(env.promptVersion ?? env.prompt_version, '') || null,
    knowledgePackVersion: coerceString(env.knowledgePackVersion ?? env.knowledge_pack_version, '') || null,
    artifactShell: coerceString(env.artifactShell ?? env.artifact_shell, '') || null,
    mutationNotes: coerceStringArray(env.mutationNotes ?? env.mutation_notes),
    judgeWarnings: coerceStringArray(env.judgeWarnings ?? env.judge_warnings),
    warnings: coerceStringArray(env.warnings),
    latencyMs: (() => {
      const v = env.latencyMs ?? env.latency_ms;
      if (typeof v === 'number') return v;
      if (typeof v === 'string' && v.length > 0) return Number(v);
      return null;
    })(),
    source,
    sourceAsset: brief.attachedMedia,
  };
}

function normalizeRefinementResult(raw: unknown): MemeRefinementResult {
  const env = (raw ?? {}) as RefineWireEnvelope;
  const list = Array.isArray(env.suggestedCandidates) ? env.suggestedCandidates : [];
  return {
    assistantReply: coerceString(env.assistantReply, 'Refinement ready.'),
    suggestedCandidates: list.map((candidate, idx) => normalizeCandidate(candidate, idx)),
    warnings: coerceStringArray(env.warnings),
    judgeWarnings: coerceStringArray(env.judgeWarnings),
    mutationNotes: coerceStringArray(env.mutationNotes),
    artifactShell: coerceString(env.artifactShell, '') || null,
  };
}

// ---------------- Mock fallback ----------------

const MOCK_FORMATS: string[] = [
  'two-panel', 'drake', 'expanding-brain', 'chad',
  'image-macro', 'screenshot-overlay', 'one-liner', 'slide-carousel',
];

const MOCK_ANGLES: string[] = [
  'the part nobody admits',
  'what the trend is really saying',
  'an oddly specific observation',
  'a sideways read on the cliché',
  'a tiny betrayal of the genre',
  'the character arc nobody asked for',
  'an aggressively local take',
  'an earnest reading of an ironic trend',
  'the lore implication',
  'the timeline-warping sequel',
];

function mockCandidate(brief: MemeBrief, i: number): MemeCandidate {
  const tone = brief.toneHints[i % Math.max(1, brief.toneHints.length)] || 'deadpan';
  const angle = MOCK_ANGLES[i % MOCK_ANGLES.length];
  const format = MOCK_FORMATS[i % MOCK_FORMATS.length];
  const needsImage = i % 3 === 0;
  const topicShort = brief.topic.trim().split(/\s+/).slice(0, 6).join(' ') || 'the thing';
  return {
    id: clientId(`cand-${i}`),
    direction: `${angle} about ${topicShort}`,
    format,
    text:
      i % 2 === 0
        ? `[${tone}] when ${topicShort.toLowerCase()} finally makes sense / it doesn't`
        : `POV: you told them ${topicShort.toLowerCase()} was fine — it was not`,
    optionalCaption:
      i % 4 === 0
        ? null
        : `caption draft · ${tone} · about ${topicShort.toLowerCase()}`,
    needsVisualContext: needsImage,
    notes:
      i % 3 === 0
        ? 'Works best with a neutral stock photo — model should not force a character.'
        : null,
    warnings: i === 0 && brief.trendSummary.length < 8 ? ['low trend context — treat as cold-open'] : [],
  };
}

function mockGeneration(brief: MemeBrief): MemeGeneration {
  const candidates = Array.from({ length: brief.count }, (_, i) => mockCandidate(brief, i));
  return {
    id: clientId('gen'),
    generatedAt: new Date().toISOString(),
    brief,
    candidates,
    model: brief.model || 'local-mock',
    preset: brief.preset,
    schemaVersion: 'mock-1',
    promptVersion: 'mock-1',
    knowledgePackVersion: null,
    artifactShell: null,
    mutationNotes: [],
    judgeWarnings: [],
    warnings: ['server endpoint unavailable — using local mock generator'],
    latencyMs: 180 + Math.floor(Math.random() * 240),
    source: 'mock',
    sourceAsset: brief.attachedMedia,
  };
}

// ---------------- Public API ----------------

export class MemeIdeationError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export interface IdeateOptions {
  /** Opt-in local mock fallback (dev only). Defaults FALSE: the /memes/ideate
   *  endpoint is live, so a 404/network/5xx is a real failure to surface, not a
   *  reason to fake a successful generation. */
  allowMock?: boolean;
  signal?: AbortSignal;
}

export async function ideateMemes(brief: MemeBrief, options: IdeateOptions = {}): Promise<MemeGeneration> {
  const allowMock = options.allowMock ?? false;
  const body = {
    topic: brief.topic,
    trendSummary: brief.trendSummary,
    imageSpringboard: brief.imageSpringboard,
    toneHints: brief.toneHints,
    requestedCount: brief.count,
    provider: brief.provider || null,
    model: brief.model || null,
    preset: brief.preset || null,
    mediaAssetId: brief.attachedMedia?.assetId || null,
    mediaTitle: brief.attachedMedia?.title || null,
    mediaSourceUrl: brief.attachedMedia?.sourceUrl || null,
    mediaTranscriptPack: brief.attachedMedia?.transcriptPack || null,
  };

  const t0 = performance.now();
  let response: Response;
  try {
    response = await fetch(`${getHttpBaseUrl()}/api/v1/memes/ideate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getAuthToken()}`,
      },
      body: JSON.stringify(body),
      signal: options.signal,
    });
  } catch (err) {
    if (allowMock) {
      return { ...mockGeneration(brief), warnings: [`network error: ${String((err as Error).message || err)}`] };
    }
    throw err;
  }

  if (response.status === 404 && allowMock) {
    return mockGeneration(brief);
  }

  const text = await response.text();
  let payload: unknown = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      if (allowMock) return mockGeneration(brief);
      throw new MemeIdeationError(`invalid json from /memes/ideate`, response.status);
    }
  }

  if (!response.ok) {
    const detail = (payload as { detail?: string; message?: string }).detail ||
      (payload as { detail?: string; message?: string }).message ||
      `Request failed (${response.status})`;
    if (allowMock && response.status >= 500) {
      return { ...mockGeneration(brief), warnings: [`server ${response.status} — showing local mock`, detail] };
    }
    throw new MemeIdeationError(detail, response.status);
  }

  const gen = normalizeGeneration(payload, brief, 'server');
  // If the server didn't include latency, measure it locally.
  return {
    ...gen,
    latencyMs: gen.latencyMs ?? Math.round(performance.now() - t0),
  };
}

export async function refineMemes(
  args: {
    brief: MemeBrief;
    generation: MemeGeneration;
    history: MemeRefinementMessage[];
    message: string;
  },
  options: IdeateOptions = {},
): Promise<MemeRefinementResult> {
  const body = {
    topic: args.brief.topic,
    trendSummary: args.brief.trendSummary,
    imageSpringboard: args.brief.imageSpringboard,
    toneHints: args.brief.toneHints,
    requestedCount: args.generation.candidates.length || args.brief.count,
    provider: args.brief.provider || null,
    model: args.brief.model || null,
    preset: args.brief.preset || null,
    mediaAssetId: args.brief.attachedMedia?.assetId || null,
    mediaTitle: args.brief.attachedMedia?.title || null,
    mediaSourceUrl: args.brief.attachedMedia?.sourceUrl || null,
    mediaTranscriptPack: args.brief.attachedMedia?.transcriptPack || null,
    currentGenerationSummary: args.generation.candidates
      .slice(0, 4)
      .map((candidate) => `${candidate.direction}: ${candidate.text}`)
      .join(' | '),
    currentCandidates: args.generation.candidates.map((candidate) => ({
      direction: candidate.direction,
      format: candidate.format,
      text: candidate.text,
      optionalCaption: candidate.optionalCaption,
      needsVisualContext: candidate.needsVisualContext,
      notes: candidate.notes,
    })),
    history: args.history.map((message) => ({ role: message.role, content: message.content })),
    message: args.message,
  };

  const response = await fetch(`${getHttpBaseUrl()}/api/v1/memes/refine`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getAuthToken()}`,
    },
    body: JSON.stringify(body),
    signal: options.signal,
  });

  const text = await response.text();
  let payload: unknown = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      throw new MemeIdeationError(`invalid json from /memes/refine`, response.status);
    }
  }
  if (!response.ok) {
    const detail = (payload as { detail?: string; message?: string }).detail ||
      (payload as { detail?: string; message?: string }).message ||
      `Request failed (${response.status})`;
    throw new MemeIdeationError(detail, response.status);
  }
  return normalizeRefinementResult(payload);
}
