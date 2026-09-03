from pathlib import Path

import pytest

from copenet.core.sessions import SessionStore, TranscriptStore


@pytest.fixture(autouse=True)
def isolated_market_background(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A host lifespan in an unrelated test must never reach operator market state."""
    from copenet.core.market import runtime
    monkeypatch.setattr(runtime, 'default_market_dir', lambda: tmp_path / 'market')
    monkeypatch.setenv('COPNET_MARKET_SENTINEL', '0')
    monkeypatch.delenv('COPNET_TELEGRAM_BOT_TOKEN', raising=False)


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def session_store(tmp_path: Path) -> SessionStore:
    return SessionStore(path=tmp_path / "index.json")


@pytest.fixture
def transcript_store(tmp_path: Path) -> TranscriptStore:
    return TranscriptStore(root_dir=tmp_path)
