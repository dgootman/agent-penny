import json
import os
from pathlib import Path
from typing import NotRequired, TypedDict

import chainlit as cl
from slugify.slugify import slugify

data_dir = Path(os.environ.get("DATA_DIR", "~/.local/share/agent-penny")).expanduser()


def get_user() -> cl.User:
    user: cl.User | None = cl.user_session.get("user")
    assert user
    return user


def path(file_name: str) -> Path:
    user_data_dir = data_dir / slugify(get_user().identifier)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    return user_data_dir / file_name


def load(file_name: str, default: str = "") -> str:
    file_path = path(file_name)
    return file_path.read_text() if file_path.exists() else default


def save(file_name: str, content: str) -> None:
    path(file_name).write_text(content)


class UserSettings(TypedDict):
    model: NotRequired[str]
    thinking: NotRequired[bool]


def load_settings() -> UserSettings:
    return json.loads(load("chat_settings.json", "{}"))


def save_settings(settings: UserSettings) -> None:
    save("chat_settings.json", json.dumps(settings))
