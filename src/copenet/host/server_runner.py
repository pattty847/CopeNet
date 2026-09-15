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
        try:
            uvicorn.Server(config).run(sockets=[server_socket])
        except KeyboardInterrupt:
            # Python 3.13 can let the runner's cancellation escape after Uvicorn
            # has already completed its graceful shutdown. Ctrl-C is a normal
            # operator action, not an application failure or a useful traceback.
            pass
    finally:
        server_socket.close()
