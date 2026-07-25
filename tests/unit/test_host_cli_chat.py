import argparse
import json

import pytest

from copenet.host import main as host_main


def test_chat_send_parser_defaults_to_named_probe_session(monkeypatch) -> None:
    monkeypatch.delenv("COPNET_CLI_PROVIDER", raising=False)
    parser = host_main._build_parser()
    args = parser.parse_args(["chat", "send", "hello"])

    assert args.command == "chat"
    assert args.chat_command == "send"
    assert args.session == "69696469"
    assert args.provider is None
    assert args.message == ["hello"]


def test_nasa_wallpaper_parser_accepts_apply_install_status_and_uninstall() -> None:
    parser = host_main._build_parser()

    apply_args = parser.parse_args(["nasa", "wallpaper", "apply", "--date", "2026-06-29", "--refresh", "--json"])
    assert apply_args.command == "nasa"
    assert apply_args.nasa_command == "wallpaper"
    assert apply_args.wallpaper_command == "apply"
    assert apply_args.date == "2026-06-29"
    assert apply_args.refresh is True
    assert apply_args.json is True

    assert parser.parse_args(["nasa", "wallpaper", "install-agent"]).wallpaper_command == "install-agent"
    assert parser.parse_args(["nasa", "wallpaper", "uninstall-agent"]).wallpaper_command == "uninstall-agent"
    assert parser.parse_args(["nasa", "wallpaper", "status"]).wallpaper_command == "status"


def test_movies_parser_exposes_bootstrap_review_and_recommendation_workflows() -> None:
    parser = host_main._build_parser()

    bootstrap = parser.parse_args(["movies", "bootstrap", "--source", "/tmp/watched.xlsx", "--limit", "5"])
    assert bootstrap.command == "movies"
    assert bootstrap.movies_command == "bootstrap"
    assert bootstrap.source == "/tmp/watched.xlsx"
    assert bootstrap.limit == 5

    assert parser.parse_args(["movies", "review"]).movies_command == "review"
    recommend = parser.parse_args(["movies", "recommend", "--limit", "12", "--explore", "0.4"])
    assert recommend.limit == 12
    assert recommend.explore == 0.4


def test_read_cli_message_joins_arguments() -> None:
    args = argparse.Namespace(message=["hello", "there"])

    assert host_main._read_cli_message(args) == "hello there"


@pytest.mark.asyncio
async def test_chat_send_uses_real_orchestrator_session(monkeypatch, capsys) -> None:
    calls = []

    class FakeOrchestrator:
        def resolve_session(self, session_key):
            return None

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


@pytest.mark.asyncio
async def test_chat_send_inherits_existing_locked_session_runtime(monkeypatch) -> None:
    calls = []

    class FakeOrchestrator:
        def resolve_session(self, session_key):
            assert session_key == "claude-room"
            return {
                "provider": "claude-cli",
                "model": "claude-opus-4-1",
                "systemPromptId": "default",
                "taskPromptId": "none",
                "personaId": "default",
                "personaFlavorId": None,
                "personaPrivacyTier": "private",
                "workspaceRoot": "/tmp/project",
            }

        async def send_chat(self, request, emit):
            calls.append(request)
            await emit({"state": "final"})
            return {"status": "ok", "runId": "run-2"}

    monkeypatch.setattr(host_main, "Orchestrator", FakeOrchestrator)
    args = argparse.Namespace(
        json=True,
        session="claude-room",
        message=["continue"],
        provider=None,
        model=None,
        system_prompt_id=None,
        task_prompt_id=None,
        persona_id=None,
        persona_flavor_id=None,
        persona_privacy_tier=None,
        workspace_root=None,
        no_tools=False,
    )

    await host_main._run_chat_send(args)

    request = calls[0]
    assert request.provider == "claude-cli"
    assert request.model == "claude-opus-4-1"
    assert request.system_prompt_id == "default"
    assert request.task_prompt_id == "none"
    assert request.workspace_root == "/tmp/project"


def test_nasa_wallpaper_apply_json_prints_structured_result(monkeypatch, capsys) -> None:
    class FakeResult:
        ok = True
        status = "applied"
        date = "2026-06-29"
        title = "Today image"
        image_path = "/tmp/space.jpg"
        reason = None
        error = None

        def to_json(self):
            return {
                "ok": self.ok,
                "status": self.status,
                "date": self.date,
                "title": self.title,
                "imagePath": self.image_path,
                "reason": self.reason,
                "error": self.error,
            }

    calls = []
    monkeypatch.setattr(host_main, "apply_apod_wallpaper", lambda **kwargs: calls.append(kwargs) or FakeResult())

    args = argparse.Namespace(wallpaper_command="apply", date="2026-06-29", refresh=True, json=True)
    host_main._run_nasa_wallpaper_command(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "applied"
    assert payload["imagePath"] == "/tmp/space.jpg"
    assert calls == [{"date": "2026-06-29", "refresh": True}]
