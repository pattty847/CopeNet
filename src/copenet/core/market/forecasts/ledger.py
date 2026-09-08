"""Compose forward forecast cohorts without changing historical ledger endpoints."""
from datetime import date

from .report import forecast_report
from .tracking import all_forecasts, evaluate_cached


def ledger_forecasts(service, params):
    provider = params.get('forecastProvider')
    model = params.get('forecastModel')
    for value in (provider, model):
        if value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 160):
            raise ValueError('Forecast provider/model filters must be nonempty strings')
    dates = [date.fromisoformat(params[key]) if params.get(key) else None
             for key in ('forecastFrom', 'forecastTo')]
    if all(dates) and dates[0] > dates[1]:
        raise ValueError('Forecast date range must be ordered')
    records = list(all_forecasts(service.store))
    cohorts = {'providers': sorted({r['provider'] for r in records}),
               'models': sorted({r['model'] for r in records if provider is None or r['provider'] == provider})}
    selected = []
    for record in records:
        day = date.fromisoformat((record.get('publishedAt') or record['requestedAt'])[:10])
        if ((provider is not None and record['provider'] != provider)
                or (model is not None and record['model'] != model)
                or (dates[0] and day < dates[0]) or (dates[1] and day > dates[1])):
            continue
        selected.append(record)
    return {**forecast_report(evaluate_cached(service.store, service.runtime, selected)), 'cohorts': cohorts}
