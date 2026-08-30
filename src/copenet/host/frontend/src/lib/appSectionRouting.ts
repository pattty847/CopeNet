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
  const normalized = normalizePathname(pathname);
  if (normalized.startsWith('/market/')) return 'market';
  return APP_SECTION_BY_PATH.get(normalized) || 'home';
}

export function marketTickerFromPathname(pathname: string): string | null {
  const normalized = normalizePathname(pathname);
  const match = normalized.match(/^\/market\/([^/]+)$/);
  if (!match) return null;
  try {
    const symbol = decodeURIComponent(match[1]).trim().toUpperCase();
    return symbol && symbol !== 'FORMULA' ? symbol : null;
  } catch {
    return null;
  }
}

export function marketFormulaFromLocation(pathname: string, search: string): string | null {
  if (normalizePathname(pathname) !== '/market/formula') return null;
  const expression = new URLSearchParams(search).get('expression')?.trim() ?? '';
  return expression || null;
}

export function marketFormulaPath(expression: string): string {
  const params = new URLSearchParams({ expression: expression.trim() });
  return `/market/formula?${params.toString()}`;
}

export function marketTickerPath(symbol: string | null): string {
  const normalized = symbol?.trim().toUpperCase();
  return normalized ? `/market/${encodeURIComponent(normalized)}` : '/market';
}

export function marketTickerNavigationPath(symbol: string | null, currentPathname: string, currentSearch: string): string {
  const preserveTickerState = symbol != null && marketTickerFromPathname(currentPathname) != null;
  return `${marketTickerPath(symbol)}${preserveTickerState ? currentSearch : ''}`;
}

export function marketResultNavigationPath(
  result: { type: 'symbol' | 'formula'; symbol: string },
  currentPathname: string,
  currentSearch: string,
): string {
  return result.type === 'formula'
    ? marketFormulaPath(result.symbol)
    : marketTickerNavigationPath(result.symbol, currentPathname, currentSearch);
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
