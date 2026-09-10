"""Authenticated RPC dispatch and the shared error boundary."""

from .rpc_errors import respond_rpc_errors
from .rpc_route_context import RpcContext, SendJson
from .rpc_routes import RPC_ROUTES
from .rpc_schema import RequestFrame, ResponseFrame, RpcError, make_response_frame


async def dispatch_rpc(
    req: RequestFrame,
    send_json: SendJson,
    orchestrator,
    tasks: set,
    broadcast: SendJson | None = None,
    *,
    quote_subscription=None,
) -> None:
    context = RpcContext(req, send_json, orchestrator, tasks, broadcast or send_json, quote_subscription)
    await respond_rpc_errors(req.id, send_json, _route_rpc(context))


async def _route_rpc(context: RpcContext) -> None:
    route = RPC_ROUTES.get(context.request.method)
    if route is None:
        await context.send_json(
            make_response_frame(
                ResponseFrame(
                    id=context.request.id,
                    ok=False,
                    error=RpcError(
                        code="METHOD_NOT_FOUND", message=f"unknown method: {context.request.method}"
                    ),
                )
            )
        )
        return
    await route.invoke(context)
