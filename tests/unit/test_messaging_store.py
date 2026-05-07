from __future__ import annotations

from pathlib import Path

from copenet.core.messaging import (
    MessageDestinationRecord,
    MessagingApprovalPolicyRecord,
    MessagingConfigRecord,
    MessagingConfigStore,
    TelegramBotConfigRecord,
)


def test_messaging_store_defaults_to_unconfigured_state(tmp_path: Path) -> None:
    store = MessagingConfigStore(tmp_path / "messaging.json")

    record = store.load()

    assert record.telegram is None
    assert record.destinations == []
    assert record.approval_policy.require_approval_by_default is True
    assert record.approval_policy.hardline_blocklist == []


def test_messaging_store_roundtrips_config_and_destinations(tmp_path: Path) -> None:
    store = MessagingConfigStore(tmp_path / "messaging.json")
    record = MessagingConfigRecord(
        telegram=TelegramBotConfigRecord(
            bot_username="@CopeNetBot",
            token_masked="tg:1234...abcd",
            connection_status="connected",
            last_verified_at="2026-05-07T10:00:00Z",
            error_message=None,
        ),
        destinations=[
            MessageDestinationRecord(
                id="tg-ops",
                platform="telegram",
                target="telegram:@copenet_ops",
                display_name="@copenet_ops",
                is_default=True,
                requires_approval=True,
                status="configured",
            )
        ],
        approval_policy=MessagingApprovalPolicyRecord(
            require_approval_by_default=False,
            hardline_blocklist=["telegram:@blocked"],
        ),
    )

    saved = store.save(record)
    loaded = store.load()

    assert saved.telegram is not None
    assert loaded.telegram is not None
    assert loaded.telegram.bot_username == "@CopeNetBot"
    assert loaded.telegram.connection_status == "connected"
    assert loaded.destinations[0].target == "telegram:@copenet_ops"
    assert loaded.destinations[0].is_default is True
    assert loaded.approval_policy.require_approval_by_default is False
    assert loaded.approval_policy.hardline_blocklist == ["telegram:@blocked"]


def test_messaging_store_updates_approval_policy_without_clobbering_destinations(tmp_path: Path) -> None:
    store = MessagingConfigStore(tmp_path / "messaging.json")
    store.save(
        MessagingConfigRecord(
            telegram=None,
            destinations=[
                MessageDestinationRecord(
                    id="tg-ops",
                    platform="telegram",
                    target="telegram:@copenet_ops",
                    display_name="@copenet_ops",
                    is_default=True,
                    requires_approval=True,
                )
            ],
            approval_policy=MessagingApprovalPolicyRecord(),
        )
    )

    updated = store.update_approval_policy(
        require_approval_by_default=False,
        hardline_blocklist=["telegram:@blocked", "telegram:@also-blocked"],
    )

    assert updated.approval_policy.require_approval_by_default is False
    assert updated.approval_policy.hardline_blocklist == ["telegram:@blocked", "telegram:@also-blocked"]
    assert updated.destinations[0].target == "telegram:@copenet_ops"


def test_messaging_store_upserts_and_deletes_destinations(tmp_path: Path) -> None:
    store = MessagingConfigStore(tmp_path / "messaging.json")
    store.save(MessagingConfigRecord())

    created = store.upsert_destination(
        MessageDestinationRecord(
            id="",
            platform="telegram",
            target="telegram:@new-dest",
            display_name="New Dest",
            is_default=True,
            requires_approval=False,
        )
    )
    assert len(created.destinations) == 1
    created_dest = created.destinations[0]
    assert created_dest.id
    assert created_dest.is_default is True
    assert created_dest.requires_approval is False

    updated = store.upsert_destination(
        MessageDestinationRecord(
            id=created_dest.id,
            platform="telegram",
            target="telegram:@new-dest",
            display_name="Renamed Dest",
            is_default=False,
            requires_approval=True,
        )
    )
    assert updated.destinations[0].display_name == "Renamed Dest"
    assert updated.destinations[0].is_default is False
    assert updated.destinations[0].requires_approval is True

    after_delete = store.delete_destination(created_dest.id)
    assert after_delete.destinations == []
