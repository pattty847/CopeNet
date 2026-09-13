"""Reserve the host socket before constructing stateful application services."""

from __future__ import annotations

import uvicorn


def run_host_app(*, host: str, port: int) -> None:
    """Run CopeNet after the process proves that it owns the requested socket."""
    config = uvicorn.Config(
        "copenet.host.api:create_host_app",
        factory=True,
        host=host,
        port=port,
        log_level="info",
    )
    server_socket = config.bind_socket()
    try:
        uvicorn.Server(config).run(sockets=[server_socket])
    finally:
        server_socket.close()
