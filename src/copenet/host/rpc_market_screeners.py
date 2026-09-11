"""Strict RPC boundary for manual discovery and saved result handoffs."""
from pydantic import BaseModel, ConfigDict, Field

from copenet.core.market.scans.screeners.models import ScreenerConfig
from copenet.core.market.scans.screeners.service import ScreenerService
from copenet.core.market.runtime import default_market_dir
from copenet.host.rpc_market_watchlist import watchlist_store
from copenet.host.rpc_schema import ResponseFrame, make_response_frame


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    config: ScreenerConfig
    scopeToken: str = Field(pattern=r"^[a-f0-9]{32}$")


class HandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    runId: str = Field(pattern=r"^[a-f0-9]{32}$")
    symbols: list[str] = Field(min_length=1, max_length=500)
    name: str = Field(min_length=1, max_length=30)


class RunIdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    runId: str = Field(pattern=r"^[a-f0-9]{32}$")


def service(orchestrator):
    current = getattr(orchestrator, "_market_screeners", None)
    if current is None:
        market = getattr(orchestrator, "market_store", None)
        current = ScreenerService(market.root_dir if market is not None else default_market_dir(), watchlist_store(orchestrator))
        orchestrator._market_screeners = current
    return current


async def reply(request_id, send_json, payload):
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


async def handle_market_screeners_get(request_id, params, send_json, orchestrator):
    await reply(request_id, send_json, service(orchestrator).state())


async def handle_market_screeners_preview(request_id, params, send_json, orchestrator):
    config = ScreenerConfig.model_validate(params)
    await reply(request_id, send_json, service(orchestrator).preview(config))


async def handle_market_screeners_run(request_id, params, send_json, orchestrator):
    request = RunRequest.model_validate(params)
    await reply(request_id, send_json, service(orchestrator).start(request.config, request.scopeToken))


async def handle_market_screeners_run_get(request_id, params, send_json, orchestrator):
    request = RunIdRequest.model_validate(params)
    await reply(request_id, send_json, {"run": service(orchestrator).get_run(request.runId)})


async def handle_market_screeners_handoff(request_id, params, send_json, orchestrator):
    request = HandoffRequest.model_validate(params)
    await reply(request_id, send_json, service(orchestrator).handoff(request.runId, request.symbols, request.name))
