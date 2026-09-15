from __future__ import annotations

from copenet.host import server_runner


def test_host_reserves_socket_before_server_loads_application(monkeypatch) -> None:
    events: list[object] = []

    class Socket:
        def close(self) -> None:
            events.append("socket_closed")

    class Config:
        def __init__(self, app, **kwargs) -> None:
            events.append(("config", app, kwargs))

        def bind_socket(self):
            events.append("socket_bound")
            return Socket()

    class Server:
        def __init__(self, config) -> None:
            events.append("server_created")

        def run(self, *, sockets) -> None:
            events.append(("server_run", len(sockets)))

    monkeypatch.setattr(server_runner.uvicorn, "Config", Config)
    monkeypatch.setattr(server_runner.uvicorn, "Server", Server)

    server_runner.run_host_app(host="127.0.0.1", port=17123)

    assert events == [
        (
            "config",
            "copenet.host.api:create_host_app",
            {"factory": True, "host": "127.0.0.1", "port": 17123, "log_level": "info"},
        ),
        "socket_bound",
        "server_created",
        ("server_run", 1),
        "socket_closed",
    ]


def test_keyboard_interrupt_is_a_clean_shutdown(monkeypatch) -> None:
    closed = False

    class Socket:
        def close(self) -> None:
            nonlocal closed
            closed = True

    class Config:
        def __init__(self, app, **kwargs) -> None:
            pass

        def bind_socket(self):
            return Socket()

    class Server:
        def __init__(self, config) -> None:
            pass

        def run(self, *, sockets) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(server_runner.uvicorn, "Config", Config)
    monkeypatch.setattr(server_runner.uvicorn, "Server", Server)

    server_runner.run_host_app(host="127.0.0.1", port=17123)

    assert closed is True
