import argparse

import pytest

from copenet.host import main as host_main


def test_chat_send_parser_defaults_to_named_probe_session() -> None:
    parser = host_main._build_parser()
    args = parser.parse_args(["chat", "send", "hello"])

    assert args.command == "chat"
    assert args.chat_command == "send"
    assert args.session == "69696469"
    assert args.provider == "openai-codex"
    assert args.message == ["hello"]


def test_read_cli_message_joins_arguments() -> None:
    args = argparse.Namespace(message=["hello", "there"])

    assert host_main._read_cli_message(args) == "hello there"


@pytest.mark.asyncio
async def test_chat_send_uses_real_orchestrator_session(monkeypatch, capsys) -> None:
    calls = []

    class FakeOrchestrator:
        async def send_chat(self, request, emit):
            calls.append(request)
            await emit(
                {
                    "state": "delta",
                    "message": {"content": f"session={request.session_key}; message={request.message}"},
                }
            )
            await emit({"state": "final"})
            return {"status": "ok", "runId": "run-1"}

    monkeypatch.setattr(host_main, "Orchestrator", FakeOrchestrator)
    args = argparse.Namespace(
        json=False,
        session="69696469",
        message=["first", "probe"],
        provider="openai-codex",
        model="gpt-5.5",
        system_prompt_id=None,
        task_prompt_id=None,
        persona_id=None,
        persona_flavor_id=None,
        persona_privacy_tier=None,
        workspace_root=None,
        no_tools=False,
    )

    await host_main._run_chat_send(args)

    out = capsys.readouterr().out
    assert "[session] 69696469 (openai-codex / gpt-5.5)" in out
    assert "session=69696469; message=first probe" in out
    assert calls[0].session_key == "69696469"
    assert calls[0].provider == "openai-codex"
    assert calls[0].model == "gpt-5.5"
