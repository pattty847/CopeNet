import type {
  AlertRule,
  AlertsState,
  IndicatorOption,
  NotificationsState,
  ScanDefinition,
  ScanPreview,
  ScanRun,
  ScansState,
} from '../sections/market/monitoring/types';

type Request = <T extends Record<string, unknown>>(method: string, params: Record<string, unknown>) => Promise<T>;

/** One typed boundary for scan configuration, rule evaluation and delivery operations. */
export function createMarketMonitoringApi(request: Request) {
  const call = async <T>(method: string, params: Record<string, unknown> = {}) => (await request(method, params)) as unknown as T;
  return {
    scans: () => call<ScansState>('market.scans.get'),
    saveScan: (scan: ScanDefinition) => call<ScansState>('market.scans.save', { scan }),
    archiveScan: (id: string) => call<ScansState>('market.scans.archive', { id }),
    previewScan: (scan: ScanDefinition) => call<ScanPreview>('market.scans.preview', { scan }),
    runScan: (id: string, scopeToken: string) => call<Record<string, unknown>>('market.scans.run', { id, scopeToken }),
    scanRun: (id: string) => call<{ run: ScanRun }>('market.scans.run.get', { id }),
    alerts: () => call<AlertsState>('market.alerts.state'),
    catalogue: () => call<{ indicators: IndicatorOption[]; available: boolean; error?: string }>('market.alerts.catalogue'),
    saveAlert: (rule: AlertRule) => call<AlertsState>('market.alerts.save', { rule }),
    cancelAlert: (alertId: string) => call<AlertsState>('market.alerts.cancel', { alertId }),
    notifications: () => call<NotificationsState>('market.notifications.get'),
    testDestination: (destinationId: string) => call<NotificationsState>('market.notifications.test', { destinationId }),
    deliveryAction: (deliveryId: string, action: 'approve' | 'retry' | 'cancel', acknowledgeDuplicateRisk = false) =>
      call<NotificationsState>('market.notifications.action', { deliveryId, action, acknowledgeDuplicateRisk }),
  };
}
