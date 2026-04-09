from pathlib import Path

import pytest

from copenet.core.sessions import SessionStore, TranscriptStore


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def session_store(tmp_path: Path) -> SessionStore:
    return SessionStore(path=tmp_path / "index.json")


@pytest.fixture
def transcript_store(tmp_path: Path) -> TranscriptStore:
    return TranscriptStore(root_dir=tmp_path)
