import os

from copenet._env import load_project_env


def test_project_env_loads_ignored_local_feature_credentials_without_overriding_environment(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("BASE_SETTING=base\nSHARED_SETTING=base\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("LOCAL_SETTING=local\nSHARED_SETTING=local\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BASE_SETTING", raising=False)
    monkeypatch.delenv("LOCAL_SETTING", raising=False)
    monkeypatch.setenv("SHARED_SETTING", "process")

    load_project_env()

    assert os.environ["BASE_SETTING"] == "base"
    assert os.environ["LOCAL_SETTING"] == "local"
    assert os.environ["SHARED_SETTING"] == "process"
