import pytest
from pydantic import ValidationError


def test_settings():
    from agent_penny.settings import settings

    assert settings


def test_invalid_settings(monkeypatch: pytest.MonkeyPatch):
    from agent_penny.settings import Settings

    monkeypatch.setenv("THINKING", "super")

    with pytest.raises(ValidationError):
        Settings()

        pytest.fail("Exception wasn't raised")
