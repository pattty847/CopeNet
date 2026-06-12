"""Tier 3: connection registry + broadcast + approval recovery."""

from __future__ import annotations

import asyncio

import pytest

from copenet.core.orchestrator import Orchestrator
from copenet.host.ws_server import CopeNetWsServer


def test_list_pending_approvals_returns_full_payload(tmp_path) -> None:
    orch = Orchestrator(sessions_dir=tmp_path)
    assert orch.list_pending_approvals() == {"approvals": []}

    approval = {"approvalId": "appr-1", "runId": "r1", "sessionKey": "s1", "status": "pending"}
    orch._pending_approvals["appr-1"] = {
        "event": asyncio.Event(),
        "decision": None,
        "note": None,
        "approval": approval,
    }
    assert orch.list_pending_approvals() == {"approvals": [approval]}


@pytest.mark.asyncio
async def test_broadcast_fans_out_and_skips_dead_connections(tmp_path) -> None:
    server = CopeNetWsServer(orchestrator=Orchestrator(sessions_dir=tmp_path))
    received_a: list[dict] = []
    received_c: list[dict] = []

    async def conn_a(payload: dict) -> None:
        received_a.append(payload)

    async def conn_b(payload: dict) -> None:
        raise RuntimeError("dead socket")

    async def conn_c(payload: dict) -> None:
        received_c.append(payload)

    server._connections.update({conn_a, conn_b, conn_c})
    await server.broadcast({"hello": "world"})

    # Every live connection receives the event; the dead one is skipped, not fatal.
    assert received_a == [{"hello": "world"}]
    assert received_c == [{"hello": "world"}]


@pytest.mark.asyncio
async def test_broadcast_with_no_connections_is_noop(tmp_path) -> None:
    server = CopeNetWsServer(orchestrator=Orchestrator(sessions_dir=tmp_path))
    await server.broadcast({"hello": "world"})  # must not raise
