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
