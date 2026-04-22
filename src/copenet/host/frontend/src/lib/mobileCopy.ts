import type { AppSection } from '../store/useAppStore';

export interface ClampResponsiveTextOptions {
  isMobile: boolean;
  mobileLimit: number;
  desktopLimit: number;
}

export function clampResponsiveText(value: string | undefined | null, options: ClampResponsiveTextOptions): string {
  if (!value) return '';
  const limit = options.isMobile ? options.mobileLimit : options.desktopLimit;
  if (value.length <= limit) return value;
  return `${value.slice(0, Math.max(0, limit - 1)).trimEnd()}…`;
}

export function clampMediaAssetTitle(value: string | undefined | null, isMobile: boolean): string {
  return clampResponsiveText(value, {
    isMobile,
    mobileLimit: 50,
    desktopLimit: 120,
  });
}

export function getMediaAssetCardBadgeLabel(isMobile: boolean): string | null {
  return isMobile ? null : 'Open';
}

export function shouldShowMobileSectionHeader(section: AppSection): boolean {
  return section === 'home';
}

const MOBILE_SECTION_SUMMARY: Record<AppSection, string> = {
  home: 'Workspace pulse and quick starts.',
  agents: 'Sessions, composer, and runtime controls.',
  workflows: 'Playbooks, Meme Lab, and repeatable flows.',
  'data-tools': 'Imports, source assets, and utility flows.',
  observability: 'Runs, traces, and live runtime signal.',
  experiments: 'Comparisons, matrices, and probe surfaces.',
};

export function getMobileSectionSummary(section: AppSection): string {
  return MOBILE_SECTION_SUMMARY[section];
}
