import type { AlertOperand, AlertRule, ScanDefinition } from './types';

export function newScan(): ScanDefinition {
  return {
    id: '',
    revision: 0,
    name: '',
    enabled: true,
    includeUniverse: false,
    symbols: [],
    watchlists: [],
    excludeSymbols: [],
    sources: ['prices'],
    times: ['09:45'],
    days: [0, 1, 2, 3, 4],
    timezone: 'America/New_York',
    publishBrief: false,
    interpret: false,
  };
}
export function newAlert(symbol = ''): AlertRule {
  return {
    alertId: '',
    revision: 0,
    symbol,
    timeframe: 'daily',
    scanId: '',
    enabled: true,
    oneShot: true,
    direction: 'above',
    left: { kind: 'indicator', indicatorId: 'rsi', config: { period: 14, source: 'close' }, output: 'rsi' },
    right: { kind: 'constant', value: 70 },
    destinationIds: [],
    telegramAuthorized: false,
    status: 'active',
  };
}
export function symbolsFromText(text: string) {
  return [
    ...new Set(
      text
        .toUpperCase()
        .split(/[\s,;]+/)
        .filter(Boolean),
    ),
  ];
}
export function toggleValue<T>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}
export function timeLabel(value?: string | null, timezone?: string): string {
  if (!value) return 'Not scheduled';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: timezone,
    timeZoneName: 'short',
  }).format(date);
}
export function operandLabel(operand: AlertOperand): string {
  if (operand.kind === 'price') return 'Close';
  if (operand.kind === 'constant') return String(operand.value ?? '—');
  return `${operand.indicatorId?.toUpperCase()}${operand.config?.period ? ` (${operand.config.period})` : ''} · ${operand.output}`;
}
export function conditionLabel(rule: AlertRule): string {
  return `${operandLabel(rule.left)} crosses ${rule.direction} ${operandLabel(rule.right)}`;
}
