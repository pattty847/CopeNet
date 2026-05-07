from __future__ import annotations

from pathlib import Path

from copenet.core.messaging import TelegramSessionRouteRecord, TelegramSessionRouteStore


def test_telegram_route_store_defaults_empty(tmp_path: Path) -> None:
    store = TelegramSessionRouteStore(tmp_path / "telegram-routes.json")

    assert store.list_routes() == []


def test_telegram_route_store_upserts_and_deletes_routes(tmp_path: Path) -> None:
    store = TelegramSessionRouteStore(tmp_path / "telegram-routes.json")

    created = store.upsert_route(
        TelegramSessionRouteRecord(
            id="",
            platform="telegram",
            chat_id="-1001234567890",
            thread_id="42",
            session_key="alpha",
            title_override="Ops Thread",
        )
    )
    assert len(created) == 1
    route = created[0]
    assert route.id
    assert route.session_key == "alpha"
    assert route.thread_id == "42"

    updated = store.upsert_route(
        TelegramSessionRouteRecord(
            id=route.id,
            platform="telegram",
            chat_id="-1001234567890",
            thread_id="42",
            session_key="beta",
            title_override="Renamed Thread",
        )
    )
    assert len(updated) == 1
    assert updated[0].session_key == "beta"
    assert updated[0].title_override == "Renamed Thread"

    after_delete = store.delete_route(route.id)
    assert after_delete == []
