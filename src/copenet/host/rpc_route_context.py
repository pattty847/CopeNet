"""Explicit call conventions for RPC handlers and connection-owned resources."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, TYPE_CHECKING
from copenet.core.market.live_quote import LiveQuoteSubscription
from .rpc_schema import RequestFrame
from .rpc_runtime import handle_runtime_context_get, handle_runtime_context_resolve

if TYPE_CHECKING:
    from copenet.core.orchestrator import Orchestrator

SendJson = Callable[[dict[str, Any]], Awaitable[None]]
Handler = Callable[..., Awaitable[None]]
CallStyle = Literal["standard", "without_params", "catalog", "chat", "fleet", "broadcast", "quote", "context"]


@dataclass(frozen=True)
class RpcContext:
    request: RequestFrame
    send_json: SendJson
    orchestrator: Orchestrator
    tasks: set
    broadcast: SendJson
    quote_subscription: LiveQuoteSubscription | None = None


async def call_standard(handler: Handler, ctx: RpcContext):
    await handler(ctx.request.id, ctx.request.params, ctx.send_json, ctx.orchestrator)


async def call_without_params(handler: Handler, ctx: RpcContext):
    await handler(ctx.request.id, ctx.send_json, ctx.orchestrator)


async def call_catalog(handler: Handler, ctx: RpcContext):
    await handler(ctx.request.id, ctx.send_json)


async def call_chat(handler: Handler, ctx: RpcContext):
    await handler(
        ctx.request.id,
        ctx.request.params,
        ctx.send_json,
        ctx.tasks,
        ctx.orchestrator,
        broadcast=ctx.broadcast,
    )


async def call_fleet(handler: Handler, ctx: RpcContext):
    await handler(
        ctx.request.id, ctx.request.params, ctx.send_json, ctx.tasks, ctx.orchestrator, ctx.broadcast
    )


async def call_broadcast(handler: Handler, ctx: RpcContext):
    await handler(
        ctx.request.id, ctx.request.params, ctx.send_json, ctx.orchestrator, broadcast=ctx.broadcast
    )


async def call_quote(handler: Handler, ctx: RpcContext):
    await handler(ctx.request, ctx.send_json, ctx.quote_subscription)


async def call_context(handler: Handler, ctx: RpcContext):
    await handler(ctx)


async def handle_runtime_context(ctx: RpcContext):
    if ctx.request.params:
        await handle_runtime_context_resolve(
            ctx.request.id, ctx.request.params, ctx.send_json, ctx.orchestrator
        )
    else:
        await handle_runtime_context_get(ctx.request.id, ctx.send_json, ctx.orchestrator)


_INVOKERS = {
    "standard": call_standard,
    "without_params": call_without_params,
    "catalog": call_catalog,
    "chat": call_chat,
    "fleet": call_fleet,
    "broadcast": call_broadcast,
    "quote": call_quote,
    "context": call_context,
}


@dataclass(frozen=True)
class RpcRoute:
    handler: Handler
    style: CallStyle

    async def invoke(self, context: RpcContext):
        await _INVOKERS[self.style](self.handler, context)


def build_routes(entries: list[tuple[str, RpcRoute]]) -> dict[str, RpcRoute]:
    routes = {}
    for method, route in entries:
        if method in routes:
            raise ValueError(f"duplicate RPC method: {method}")
        routes[method] = route
    return routes
