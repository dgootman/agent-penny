from pathlib import Path

import pytest


@pytest.fixture
def tmp_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from agent_penny import user_data

    users_dir = tmp_path / "users"
    users_dir.mkdir()

    monkeypatch.setattr(user_data, "data_dir", tmp_path)
    monkeypatch.setattr(user_data, "users_dir", users_dir)

    return tmp_path
