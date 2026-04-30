from __future__ import annotations

import pytest

from copenet.providers.codex_cli import CodexCliProvider


class DummyRunner:
    async def run(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        if False:
            yield None


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> CodexCliProvider:
    monkeypatch.setattr("shutil.which", lambda name: "/opt/homebrew/bin/codex" if name == "codex" else None)
    return CodexCliProvider(runner=DummyRunner())


@pytest.mark.asyncio
async def test_codex_cli_list_models_exposes_supported_models(provider: CodexCliProvider) -> None:
    models = await provider.list_models()

    assert [model.id for model in models] == ["gpt-5.4", "gpt-5.5"]
    assert models[0].capabilities["toolCalls"] is False
    assert models[0].capabilities["promptedToolUse"] is False


@pytest.mark.asyncio
async def test_codex_cli_describe_reports_opaque_chat_capabilities(provider: CodexCliProvider) -> None:
    description = await provider.describe()

    assert description["supportsModelSelection"] is True
    assert description["capabilities"]["toolCalls"] is False
    assert description["capabilities"]["promptedToolUse"] is False


def test_codex_cli_build_args_defaults_to_gpt_5_4(provider: CodexCliProvider) -> None:
    args = provider._build_args(prompt="hello", provider_session_id=None, model=None)

    assert args[:6] == [
        "/opt/homebrew/bin/codex",
        "exec",
        "--json",
        "--full-auto",
        "--skip-git-repo-check",
        "-m",
    ]
    assert args[6] == "gpt-5.4"
    assert args[-1] == "hello"


def test_codex_cli_build_args_accepts_gpt_5_5(provider: CodexCliProvider) -> None:
    args = provider._build_args(prompt="hello", provider_session_id=None, model="gpt-5.5")

    assert "-m" in args
    assert args[args.index("-m") + 1] == "gpt-5.5"


def test_codex_cli_build_args_rejects_unsupported_model(provider: CodexCliProvider) -> None:
    with pytest.raises(ValueError, match="unsupported codex model"):
        provider._build_args(prompt="hello", provider_session_id=None, model="gpt-5.1-codex-mini")
