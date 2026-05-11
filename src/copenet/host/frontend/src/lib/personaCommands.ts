import type { DraftSettings, PersonaPrivacyTier, Session } from '../types/backend';

export const DRAFT_TRANSCRIPT_SESSION_KEY = '__draft__';

export type PersonaSlashCommand =
  | { kind: 'summary' }
  | { kind: 'files' }
  | { kind: 'privacy'; privacyTier: PersonaPrivacyTier }
  | { kind: 'onboard' }
  | { kind: 'help' };

export interface PersonaRuntimeSelection {
  provider: string;
  model: string | null;
  personaId: string;
  personaFlavorId: string;
  personaPrivacyTier: PersonaPrivacyTier;
}

function safeSegment(value: string): string {
  return value.trim().replace(/[^a-zA-Z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '') || 'default';
}

export function parsePersonaSlashCommand(input: string): PersonaSlashCommand | null {
  const trimmed = input.trim();
  if (!trimmed.startsWith('/persona')) return null;

  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return { kind: 'summary' };
  if (parts[1] === 'files' && parts.length === 2) return { kind: 'files' };
  if (parts[1] === 'onboard' && (parts.length === 2 || trimmed === '/persona onboard this model')) {
    return { kind: 'onboard' };
  }
  if (parts[1] === 'privacy' && parts.length === 3) {
    const tier = parts[2];
    if (tier === 'private' || tier === 'safe' || tier === 'off') {
      return { kind: 'privacy', privacyTier: tier };
    }
  }
  return { kind: 'help' };
}

export function buildPersonaCommandHelpText(): string {
  return [
    '## Persona Home commands',
    '',
    '- `/persona` — show the active persona summary',
    '- `/persona files` — list the files loaded for this runtime',
    '- `/persona privacy safe` — set the default privacy tier (also supports `private` and `off`)',
    '- `/persona onboard this model` — draft a model flavor for review',
  ].join('\n');
}

export function resolvePersonaRuntime(activeSession: Session | null, draftSettings: DraftSettings): PersonaRuntimeSelection {
  if (activeSession) {
    return {
      provider: activeSession.provider,
      model: activeSession.model,
      personaId: activeSession.personaId || 'default',
      personaFlavorId: activeSession.personaFlavorId || '',
      personaPrivacyTier: activeSession.personaPrivacyTier || 'private',
    };
  }
  return {
    provider: draftSettings.provider,
    model: draftSettings.model || null,
    personaId: draftSettings.personaId || 'default',
    personaFlavorId: draftSettings.personaFlavorId || '',
    personaPrivacyTier: draftSettings.personaPrivacyTier || 'private',
  };
}

export function buildPersonaModelKey(provider: string, model: string | null | undefined): string {
  return `${provider}:${model || 'default'}`;
}

export function buildPersonaFlavorId(provider: string, model: string | null | undefined): string {
  return `${safeSegment(provider)}/${safeSegment(model || 'default')}`;
}
