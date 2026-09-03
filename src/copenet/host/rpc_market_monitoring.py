"""Explicit dispatch table for the Market monitoring control plane."""
from .rpc_market_alerts import (
    handle_market_alerts_list, handle_market_alerts_create, handle_market_alerts_save,
    handle_market_alerts_cancel, handle_market_alerts_state, handle_market_alerts_catalogue,
)
from .rpc_market_scans import (
    handle_market_scans_get, handle_market_scans_save, handle_market_scans_archive,
    handle_market_scans_preview, handle_market_scans_run, handle_market_scans_run_get,
)
from .rpc_market_notifications import (
    handle_market_notifications_get, handle_market_notifications_test,
    handle_market_notifications_action,
)

MARKET_MONITORING_HANDLERS = {
    'market.scans.get': handle_market_scans_get,
    'market.scans.save': handle_market_scans_save,
    'market.scans.archive': handle_market_scans_archive,
    'market.scans.preview': handle_market_scans_preview,
    'market.scans.run': handle_market_scans_run,
    'market.scans.run.get': handle_market_scans_run_get,
    'market.alerts.list': handle_market_alerts_list,
    'market.alerts.create': handle_market_alerts_create,
    'market.alerts.save': handle_market_alerts_save,
    'market.alerts.cancel': handle_market_alerts_cancel,
    'market.alerts.state': handle_market_alerts_state,
    'market.alerts.catalogue': handle_market_alerts_catalogue,
    'market.notifications.get': handle_market_notifications_get,
    'market.notifications.test': handle_market_notifications_test,
    'market.notifications.action': handle_market_notifications_action,
}
