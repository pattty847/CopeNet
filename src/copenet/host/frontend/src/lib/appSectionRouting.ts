import type { AppSection } from '../store/useAppStore';

export const APP_SECTION_PATHS: Record<AppSection, string> = {
  home: '/',
  agents: '/agents',
  market: '/market',
  workflows: '/workflows',
  'data-tools': '/data-tools',
  observability: '/observability',
  experiments: '/experiments',
};

const APP_SECTION_BY_PATH = new Map(
  Object.entries(APP_SECTION_PATHS).map(([section, path]) => [path, section as AppSection]),
);

function normalizePathname(pathname: string): string {
  if (!pathname || pathname === '/') return '/';
  return pathname.replace(/\/+$/, '') || '/';
}

export function appSectionFromPathname(pathname: string): AppSection {
  return APP_SECTION_BY_PATH.get(normalizePathname(pathname)) || 'home';
}

export function pushAppSectionPath(
  section: AppSection,
  currentPathname: string,
  pushState: (path: string) => void,
): boolean {
  const nextPath = APP_SECTION_PATHS[section];
  if (normalizePathname(currentPathname) === nextPath) return false;
  pushState(nextPath);
  return true;
}
