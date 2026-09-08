"""Forecast actions require server-owned admission, not authority from tool arguments."""
from __future__ import annotations

from copenet.core.market.chart_workspace.models import Contract
from copenet.core.market.forecasts.models import Submission
from copenet.core.market.forecasts.store import ForecastStore
from copenet.core.tools.contracts import ToolBlockedError, ToolDescriptor, ToolExecutionResult
from .market_chart import _bound, _schema, _EMPTY


class SubmitRequest(Contract):
    result: Submission


def _forecast(context):
    charts, binding = _bound(context)
    if not binding.forecast_id or not binding.forecast_lane:
        raise ToolBlockedError('Use Forecast this chart to admit a forecast before submitting')
    return ForecastStore(charts), binding


async def submit_forecast(request, context):
    store, binding = _forecast(context)
    try:
        args = SubmitRequest.model_validate(request.arguments)
    except ValueError as exc:
        store.record_rejection(binding.forecast_id, binding.forecast_lane, binding.session_key,
                               binding.run_id, str(exc))
        raise
    record = store.submit(binding.forecast_id, binding.forecast_lane, binding.session_key,
                          binding.run_id, args.result.model_dump(by_alias=True))
    # Do not expose the paired lane's answer through a tool result.
    output = {'forecastId': record['forecastId'], 'status': 'submitted',
              'member': record['members'][binding.forecast_lane]}
    return ToolExecutionResult(tool_id=request.tool_id, ok=True,
                               summary='Forecast submitted; publication and display confirmation pending', output=output)


async def read_forecast(request, context):
    store, binding = _forecast(context)
    if request.arguments:
        raise ValueError('market.forecast.read takes no arguments')
    record = store.get(binding.forecast_id, binding.session_key)
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary='This admitted forecast lane',
                               output={'forecastId': record['forecastId'], 'status': record['status'],
                                       'member': record['members'][binding.forecast_lane]})


DESCRIPTORS = [
    ToolDescriptor(id='market.forecast.submit', name='Submit Chart Forecast', category='chart-write',
                   description='Submit the explicitly admitted forecast once. TA lane: setup with entry kind/price, protective stop, ordered profit targets with original-unit fractions totaling 1, thesis and captured evidence; or no_setup. Directional lane: directional result. Submission is immutable; authority and attribution come from the bound run. No brokerage order is placed.',
                   input_schema=_schema(SubmitRequest), side_effect='write', evidence_role='mutation'),
    ToolDescriptor(id='market.forecast.read', name='Read Admitted Forecast', category='context',
                   description='Read only your own admitted lane and its saved submission. Peer results stay hidden.',
                   input_schema=_EMPTY, side_effect='read', evidence_role='grounding'),
]
HANDLERS = {'market.forecast.submit': submit_forecast, 'market.forecast.read': read_forecast}
