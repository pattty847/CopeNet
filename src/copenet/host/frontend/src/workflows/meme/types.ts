// Contracts for the Meme Lab workflow.
// Backend endpoint: POST /api/v1/memes/ideate (stateless ideation).
// These types are frontend-normalized; the wire format is unwrapped in memeClient.ts.

export type MemeFormat =
  | 'one-liner'
  | 'two-panel'
  | 'drake'
  | 'expanding-brain'
  | 'chad'
  | 'image-macro'
  | 'screenshot-overlay'
  | 'slide-carousel'
  | 'unknown';

export interface MemeCandidate {
  id: string;                         // client-assigned for ranking persistence
  direction: string;                  // the "angle" / core premise
  format: MemeFormat | string;        // canonical format hint (free-form from model)
  text: string;                       // the meme text itself (display hero)
  optionalCaption: string | null;     // IG caption under the image
  needsVisualContext: boolean;        // signals that the idea needs a real image to land
  notes: string | null;               // creative-direction notes from the model
  warnings: string[];                 // safety / dedupe / tone warnings
}

export interface MemeBrief {
  topic: string;
  trendSummary: string;
  imageSpringboard: string;           // textual description of a reference image / source
  toneHints: string[];                // chips: "edgy", "wholesome", "absurdist"…
  count: number;                      // requested candidate count
  provider: string | null;            // provider override or inherit app default
  model: string | null;               // override or inherit app default
  preset: string | null;              // named ideation preset if server supports
  attachedMedia: MemeAttachedMedia | null;
}

export interface MemeGeneration {
  id: string;                         // client-assigned
  generatedAt: string;                // ISO
  brief: MemeBrief;
  candidates: MemeCandidate[];
  model: string | null;               // resolved from server
  preset: string | null;
  schemaVersion: string | null;
  promptVersion: string | null;
  knowledgePackVersion: string | null;
  artifactShell: string | null;
  mutationNotes: string[];
  judgeWarnings: string[];
  warnings: string[];                 // envelope-level warnings
  latencyMs: number | null;
  source: 'server' | 'mock';          // fallback when endpoint is unavailable
  sourceAsset: MemeAttachedMedia | null;
}

export interface MediaTranscriptPack {
  summary: string | null;
  keyLines: string[];
  notableQuotes: string[];
  transcriptSource: string | null;
  transcriptExcerpt: string | null;
  toneCues: string[];
}

export interface MemeAttachedMedia {
  assetId: string;
  title: string;
  sourceUrl: string | null;
  transcriptSource: string | null;
  transcriptExcerpt: string;
  transcriptPack: MediaTranscriptPack;
}

export interface MemeRefinementMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
}

export interface MemeRefinementResult {
  assistantReply: string;
  suggestedCandidates: MemeCandidate[];
  warnings: string[];
  judgeWarnings: string[];
  mutationNotes: string[];
  artifactShell: string | null;
}

export type MemeVerdict = 'winner' | 'loser' | 'tie' | null;

export interface MemeRanking {
  candidateId: string;
  score: number;                       // -3..+3, integer
  pinned: boolean;                     // "keeper" board
  verdict: MemeVerdict;                // arena verdict
  note: string | null;                 // one-line critique
  updatedAt: string;
}

export type MemeViewMode = 'stream' | 'gallery' | 'arena';

export interface ArenaState {
  leftId: string | null;
  rightId: string | null;
  lastVerdict: { leftId: string; rightId: string; winner: string | 'tie' } | null;
}

// Preset tone chips — used by the composer and echoed to the server.
export const TONE_PRESETS: Array<{ id: string; label: string; hint: string }> = [
  { id: 'edgy',       label: 'Edgy',        hint: 'sharp, punch-up, self-aware' },
  { id: 'wholesome',  label: 'Wholesome',   hint: 'earnest absurd, warm-coded'  },
  { id: 'absurd',     label: 'Absurdist',   hint: 'non-sequitur, surreal'       },
  { id: 'copecore',   label: 'Copecore',    hint: 'brand-voice, in-universe'    },
  { id: 'dry',        label: 'Dry',         hint: 'deadpan, low-affect'         },
  { id: 'ironic',     label: 'Ironic',      hint: 'layered, meta'               },
  { id: 'raw',        label: 'Raw',         hint: 'no filter, unpolished'       },
  { id: 'melancholy', label: 'Melancholy',  hint: 'dusk-coded, sad-funny'       },
];

// Ideation presets — these are hints to the server; local mock honors them too.
export const IDEATION_PRESETS: Array<{ id: string; label: string; description: string }> = [
  { id: 'shotgun',       label: 'Shotgun',         description: '12 fast divergent angles, low fidelity'    },
  { id: 'sharpshooter',  label: 'Sharpshooter',    description: '4 tightly-focused candidates, refined'     },
  { id: 'remix',         label: 'Remix Mode',      description: 'Riff on an existing trend or image prompt' },
  { id: 'cold-open',     label: 'Cold Open',       description: 'Starts from zero, no trend context'        },
];
