export type PersonalStarterIntentId =
  | 'think_through_something'
  | 'plan_my_next_steps'
  | 'reflect_and_organize';

export interface PersonalStarterPreset {
  id: PersonalStarterIntentId;
  label: string;
  cue: string;
  seed: string;
}

export const PERSONAL_STARTER_PRESETS: PersonalStarterPreset[] = [
  {
    id: 'think_through_something',
    label: 'Think Through Something',
    cue: 'Surface tradeoffs, unknowns, and the next best questions.',
    seed: 'Help me think through this carefully. Surface the tradeoffs, unknowns, and the best next questions: ',
  },
  {
    id: 'plan_my_next_steps',
    label: 'Plan My Next Steps',
    cue: 'Turn the mess into a concrete, ordered plan.',
    seed: 'Help me turn this into a practical next-step plan with priorities, checkpoints, and a realistic first move: ',
  },
  {
    id: 'reflect_and_organize',
    label: 'Reflect + Organize',
    cue: 'Untangle what matters and organize it clearly.',
    seed: 'Help me reflect on this, organize the important threads, and turn it into something clear and actionable: ',
  },
];

const STARTER_LABELS: Record<PersonalStarterIntentId, string> = {
  think_through_something: 'thinking',
  plan_my_next_steps: 'planning',
  reflect_and_organize: 'reflection',
};

function compact(text: string | null | undefined, limit = 70) {
  const value = String(text || '').replace(/\s+/g, ' ').trim();
  if (!value) return '';
  if (value.length <= limit) return value;
  return `${value.slice(0, limit - 1).trimEnd()}…`;
}

export function describeSessionReturnCue(input: {
  providerLabel: string;
  modelLabel: string;
  taskSummary: string | null;
  starterIntent: string | null;
  topicalTags: string[];
}): { kind: 'personal' | 'runtime'; primary: string } {
  const normalizedIntent = (input.starterIntent || '').trim() as PersonalStarterIntentId | '';
  const taskSummary = compact(input.taskSummary, 56);
  if (taskSummary && (normalizedIntent || input.topicalTags.length > 0)) {
    const label = normalizedIntent ? STARTER_LABELS[normalizedIntent] : compact(input.topicalTags[0], 18).toLowerCase();
    return {
      kind: 'personal',
      primary: label ? `${label} · ${taskSummary}` : taskSummary,
    };
  }
  const runtimeLabel = [compact(input.providerLabel, 18), compact(input.modelLabel, 18)].filter(Boolean).join(' · ');
  return { kind: 'runtime', primary: runtimeLabel || 'Session ready' };
}

export function shouldRenderResumeSnapshot(input: {
  taskSummary: string | null;
  unresolvedQuestions: string[];
  priorDecisions: string[];
  starterIntent: string | null;
}): boolean {
  return Boolean(
    compact(input.taskSummary) ||
      input.unresolvedQuestions.length > 0 ||
      input.priorDecisions.length > 0 ||
      (input.starterIntent || '').trim(),
  );
}
